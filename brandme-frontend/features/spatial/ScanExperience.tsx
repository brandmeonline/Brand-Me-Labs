"use client";
import { useEffect, useRef, useState } from "react";
import {
  expireScanClaims, ownerScanFacets, publicScanFacets, readResolvedAsset, readScanClaims,
  scanFacetLabels, scanPhotoFixture, validateScanTag,
  type ScanClaims, type ScanConnector, type ScanFacet,
} from "./scanResolution";
import styles from "./spatial.module.css";

export interface ScanExperienceProps { connector?: ScanConnector }

/** Host injects an authenticated resolver. With no host, no recognition is claimed. */
export default function ScanExperience({ connector }: ScanExperienceProps = {}) {
  const [mode, setMode] = useState<"tag" | "photo">("tag");
  const [tag, setTag] = useState("");
  const [consent, setConsent] = useState(false);
  const [online, setOnline] = useState(true);
  const [busy, setBusy] = useState<"resolve" | "public" | "owner" | null>(null);
  const [publicResult, setPublicResult] = useState<ScanClaims | null>(null);
  const [ownerResult, setOwnerResult] = useState<ScanClaims | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const request = useRef<{ revision: number; abort?: AbortController }>({ revision: 0 });

  function cancel() {
    request.current.revision++;
    request.current.abort?.abort();
    request.current.abort = undefined;
  }
  function clear() {
    cancel(); setBusy(null); setPublicResult(null); setOwnerResult(null); setError(""); setMessage("");
  }
  useEffect(() => {
    clear(); setConsent(false);
    return cancel;
    // The host must change sessionKey when authentication/disclosure changes.
  }, [connector, connector?.sessionKey]);
  useEffect(() => {
    const update = () => {
      setOnline(navigator.onLine);
      if (!navigator.onLine) { clear(); setMessage("You are offline. Reconnect before resolving a garment."); }
    };
    const hide = () => {
      if (document.hidden) { cancel(); setBusy(null); setOwnerResult(null); setMessage("Private details closed while this page was away."); }
    };
    update();
    window.addEventListener("online", update); window.addEventListener("offline", update);
    document.addEventListener("visibilitychange", hide);
    return () => {
      cancel(); window.removeEventListener("online", update); window.removeEventListener("offline", update);
      document.removeEventListener("visibilitychange", hide);
    };
  }, []);
  useEffect(() => {
    const now = Date.now();
    const deadlines = [publicResult, ownerResult].flatMap(result => result?.claims
      .filter(claim => claim.state === "current" && claim.expiresAt !== null)
      .map(claim => Date.parse(claim.expiresAt!)) ?? []);
    if (!deadlines.length) return;
    const timer = setTimeout(() => {
      const at = Date.now();
      setPublicResult(result => result ? expireScanClaims(result, at) : null);
      if (ownerResult?.claims.some(claim => claim.expiresAt && Date.parse(claim.expiresAt) <= at)) {
        setOwnerResult(null);
        setMessage("Owner details expired and were closed. Request access again to refresh them.");
      }
    }, Math.min(2147483647, Math.max(1, Math.min(...deadlines) - now + 1)));
    return () => clearTimeout(timer);
  }, [publicResult, ownerResult]);

  async function run(owner = false) {
    if (!connector || !online) return;
    const selected = connector, assetId = publicResult?.assetId;
    if (owner && (!assetId || !selected.unfoldOwnerClaims)) return;
    cancel();
    const revision = request.current.revision, abort = new AbortController();
    request.current.abort = abort;
    const current = () => revision === request.current.revision && !abort.signal.aborted;
    setError(""); setMessage(""); setOwnerResult(null);
    if (!owner) setPublicResult(null);
    setBusy(owner ? "owner" : "resolve");
    const timer = setTimeout(() => {
      if (!current()) return;
      cancel(); setBusy(null); setError("The request timed out. No new details were opened. You can retry.");
    }, 20000);
    try {
      if (owner && assetId) {
        const response = await selected.unfoldOwnerClaims!(assetId, { signal: abort.signal });
        if (!current()) return;
        const details = readScanClaims(response, assetId, "owner");
        if (details.claims.some(claim => ownerScanFacets.includes(claim.facet as typeof ownerScanFacets[number]) && claim.state !== "current"))
          throw new Error("owner disclosure expired or revoked");
        setOwnerResult(details);
        setMessage("Owner details opened for this session. Close them when you are finished.");
      } else {
        let input;
        if (mode === "photo") {
          if (!consent || !selected.supportsFixturePhoto) throw new Error("photo unavailable");
          const response = await fetch(scanPhotoFixture, { signal: abort.signal, cache: "no-store" });
          if (!response.ok) throw new Error("fixture unavailable");
          const image = await response.blob();
          if (!image.type.startsWith("image/") || image.size > 2 * 1024 * 1024) throw new Error("fixture invalid");
          input = { kind: "photo" as const, image };
        } else input = { kind: "tag" as const, identifier: validateScanTag(tag) };
        if (!current()) return;
        const resolution = await selected.resolve(input, { signal: abort.signal });
        if (!current()) return;
        const resolved = readResolvedAsset(resolution);
        setBusy("public");
        const response = await selected.readPublicClaims(resolved, { signal: abort.signal });
        if (!current()) return;
        setPublicResult(readScanClaims(response, resolved, "public"));
        setMessage(selected.mode === "fixture" ? "Fixture record resolved. This is a simulated lookup, not garment recognition." : "Product record resolved. Identification does not prove ownership or authenticity.");
      }
    } catch {
      if (current()) setError(owner
        ? "Owner details are unavailable or access was denied. Your private details remain closed."
        : "We could not resolve this garment or read its public details. Check the identifier or connection and retry.");
    } finally {
      clearTimeout(timer);
      if (current()) { setBusy(null); request.current.abort = undefined; }
    }
  }

  function facets(result: ScanClaims, groups: readonly ScanFacet[]) {
    return groups.map(facet => {
      const claims = result.claims.filter(claim => claim.facet === facet);
      return <section key={facet} className={styles.card} aria-label={`${scanFacetLabels[facet]} details`} style={{ overflowWrap: "anywhere" }}>
        <h3>{scanFacetLabels[facet]}</h3>
        {claims.length === 0 ? <p className={styles.muted}>No details shared.</p> : claims.map(claim => <article key={claim.id} className={styles.stack}>
          <p><strong>{claim.statement}</strong> · {claim.state}</p>
          {claim.lines.length > 0 && <dl className={styles.field} style={{ margin: 0 }}>
            {claim.lines.map(line => <div key={line.label}>
              <dt className={styles.muted}>{line.label}</dt>
              <dd style={{ margin: 0 }}>{line.text}</dd>
            </div>)}
          </dl>}
          <p className={styles.muted}>Source: {claim.source}<br />Observed: <time dateTime={claim.observedAt}>{claim.observedAt}</time><br />
            {claim.environment}{claim.network ? ` · ${claim.network}` : ""}{claim.network && claim.network !== "mainnet" ? " · Test network / not deployed" : ""}
            {claim.expiresAt && <><br />Expires: <time dateTime={claim.expiresAt}>{claim.expiresAt}</time></>}
          </p>
        </article>)}
      </section>;
    });
  }

  return <section className={styles.root}>
    <header className={styles.header}>
      <div><p className={styles.eyebrow}>Discover a garment</p><h1>Every piece has a story.</h1>
        <p className={styles.muted}>Start with a tag or a photo. Product identification is separate from ownership and authenticity.</p></div>
      <a className={styles.button} href="/add">Back to Add</a>
    </header>
    {connector ? <p className={styles.notice}>{connector.mode === "fixture" ? "Contract fixture · simulated resolution · no live recognition or verification." : "Development connector · test assets only · no production verification."}</p>
      : <p role="status" className={styles.notice}>Scanning is not connected yet. A product resolver and server-authorized disclosure service are required before results can be shown.</p>}
    <div className={styles.toolbar} aria-label="Scan input">
      <button aria-pressed={mode === "tag"} onClick={() => { clear(); setMode("tag"); setConsent(false); }}>RFID / tag identifier</button>
      <button aria-pressed={mode === "photo"} onClick={() => { clear(); setMode("photo"); setConsent(false); }}>Photo</button>
    </div>
    <div className={styles.divider} />
    <div className={styles.card}>
      {mode === "tag" ? <>
        <label>Tag identifier<input value={tag} maxLength={256} autoComplete="off" autoCapitalize="off" spellCheck={false}
          onChange={event => { clear(); setTag(event.target.value); }} placeholder="Identifier supplied by your tag reader" /></label>
        <p className={styles.muted}>Paste an identifier from a compatible reader. This page does not activate RFID hardware. A copied identifier is not proof of a genuine garment.</p>
      </> : <>
        <h2>Photo resolution</h2>
        <p className={styles.muted}>This development step uses only our original garment test image. Personal uploads and camera recognition are not enabled.</p>
        {connector?.supportsFixturePhoto ? <>
          <img src={scanPhotoFixture} width={180} height={220} alt="Original overshirt test image" style={{ maxWidth: "100%", objectFit: "contain" }} />
          <label className={styles.checkbox}><input type="checkbox" checked={consent} onChange={event => { clear(); setConsent(event.target.checked); }} />
            Use this supplied test image for this resolution request.</label>
        </> : <p className={styles.notice}>Photo resolution is unavailable until a test connector is supplied.</p>}
      </>}
      <div className={styles.row}>
        <button className={styles.primary} disabled={!connector || !online || !!busy || (mode === "tag" ? !tag.trim() : !consent || !connector.supportsFixturePhoto)} onClick={() => void run()}>
          {busy === "resolve" ? "Resolving garment…" : busy === "public" ? "Loading shared details…" : "Resolve garment"}
        </button>
        {busy && <button onClick={() => { clear(); setMessage("Request cancelled. No new details were opened."); }}>Cancel request</button>}
        {(publicResult || error) && <button onClick={() => { clear(); setTag(""); setConsent(false); }}>Clear scan</button>}
      </div>
    </div>
    {!online && <p className={styles.notice}>Offline · resolution is paused.</p>}
    {error && <p role="alert" className={`${styles.notice} ${styles.error}`}>{error}</p>}
    {message && <p role="status" className={styles.notice}>{message}</p>}
    {publicResult && <div className={styles.stack} style={{ marginTop: 24 }}>
      <h2>Shared product details</h2>
      <p className={styles.muted}>Identity, house, maker and story are the public view. Only details disclosed by the record service appear here.</p>
      <div className={styles.formGrid}>{facets(publicResult, publicScanFacets)}</div>
      <section className={styles.card} aria-label="Owner disclosure">
        <h2>Your private details</h2><p className={styles.muted}>Price, ownership and logistics stay closed. The record service must authorize your current session each time you open them.</p>
        {ownerResult ? <>
          <button onClick={() => { cancel(); setOwnerResult(null); setBusy(null); setMessage("Private details closed."); }}>Close owner details</button>
          <div className={styles.formGrid}>{facets(ownerResult, ownerScanFacets)}</div>
        </> : <button disabled={!connector?.unfoldOwnerClaims || !!busy || !online} onClick={() => void run(true)}>{busy === "owner" ? "Checking owner access…" : "Open owner details"}</button>}
        {!connector?.unfoldOwnerClaims && <p className={styles.muted}>Owner access is not connected.</p>}
      </section>
    </div>}
  </section>;
}
