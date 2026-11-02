"use client";
import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  FIT_HISTORY_KEY, FIT_HISTORY_GENERATION_KEY, FIT_HISTORY_READ_ONLY, clearFitHistory, deleteFitNote, fitAdjustments, fitCategories, fitHistoryMutationsAvailable,
  fitOutcomes, fitPreferences, inferHouseFit, readFitHistory, saveFitNote, sizeSystems,
  type FitHistory, type FitNoteInput, type FitScope,
} from "./fitHistory";
import { browserDepthEnvironment, probeDepthCapability, type DepthCapability } from "./depthCapabilities";
import styles from "./spatial.module.css";

type Draft = Record<keyof FitNoteInput, string>;
const freshDraft = (): Draft => ({ house: "", category: "tops", sizeSystem: "letter", preference: "regular",
  garment: "", size: "", outcome: "", movement: "", adjustment: "" });
const labels: Record<string, string> = {
  tops: "Tops", bottoms: "Bottoms", "one-piece": "One-piece", outerwear: "Outerwear", footwear: "Footwear",
  letter: "Letter sizes (XS, S, M…)", "house-specific": "House-specific labels", tailored: "Tailored", regular: "Regular", relaxed: "Relaxed",
  comfortable: "Comfortable", "too-snug": "Too snug", "too-loose": "Too loose", free: "Free movement", restricted: "Restricted movement",
  none: "No adjustment needed", shoulders: "Shoulders", chest: "Chest", waist: "Waist", hips: "Hips", length: "Length", feet: "Feet",
};
const scopeFields = ["house", "category", "sizeSystem", "preference"];
function messageFrom(error: unknown) {
  return error instanceof Error ? error.message : "This device could not complete the action. Please retry.";
}

export function FitLadder() {
  const [draft, setDraft] = useState<Draft>(freshDraft),
    [history, setHistory] = useState<FitHistory>({ version: 1, notes: [] }),
    [loaded, setLoaded] = useState(false),
    [canMutate, setCanMutate] = useState(false),
    [mutating, setMutating] = useState(false),
    [storageError, setStorageError] = useState(""),
    [formError, setFormError] = useState(""),
    [message, setMessage] = useState(""),
    [depth, setDepth] = useState<DepthCapability>(),
    [checking, setChecking] = useState(false);
  const probeGeneration = useRef(0);
  const mutationBusy = useRef(false);
  function loadHistory() {
    try { setHistory(readFitHistory(window.localStorage)); setStorageError(""); }
    catch (error) { setHistory({ version: 1, notes: [] }); setStorageError(messageFrom(error)); }
    finally { setLoaded(true); }
  }
  useEffect(() => {
    loadHistory();
    setCanMutate(fitHistoryMutationsAvailable());
    const changed = (event: StorageEvent) => {
      if (event.key === FIT_HISTORY_KEY || event.key === FIT_HISTORY_GENERATION_KEY || event.key === null) {
        loadHistory(); setDraft(freshDraft()); setMessage("Fit history changed in another tab."); setFormError("");
      }
    };
    window.addEventListener("storage", changed);
    return () => { window.removeEventListener("storage", changed); probeGeneration.current++; };
  }, []);

  function change(key: keyof Draft, value: string) {
    setDraft((previous) => ({ ...previous,
      ...(scopeFields.includes(key) ? { garment: "", size: "", outcome: "", movement: "", adjustment: "" } : {}),
      [key]: value }));
    setFormError(""); setMessage("");
  }
  async function save(event: FormEvent) {
    event.preventDefault();
    if (mutationBusy.current) return;
    mutationBusy.current = true; setMutating(true);
    try {
      await saveFitNote(window.localStorage, draft);
      setHistory(readFitHistory(window.localStorage));
      setMessage("Fit note saved on this device. Saving the same garment again replaces its note.");
      setFormError("");
    } catch (error) { setMessage(""); setFormError(messageFrom(error)); }
    finally { mutationBusy.current = false; setMutating(false); }
  }
  async function eraseAll() {
    if (mutationBusy.current) return;
    mutationBusy.current = true; setMutating(true);
    try {
      await clearFitHistory(window.localStorage);
      setHistory(readFitHistory(window.localStorage)); setDraft(freshDraft()); setStorageError(""); setFormError("");
      setMessage("Fit history and draft answers deleted from this browser.");
    } catch (error) { setMessage(""); setFormError(messageFrom(error)); }
    finally { mutationBusy.current = false; setMutating(false); }
  }
  async function eraseNote(id: string) {
    if (mutationBusy.current) return;
    mutationBusy.current = true; setMutating(true);
    try {
      await deleteFitNote(window.localStorage, id);
      setHistory(readFitHistory(window.localStorage));
      // Remove all private draft answers too; Review -> Delete must not leave a ready-to-save copy.
      setDraft(freshDraft());
      setMessage("Fit note and draft answers deleted from this device."); setFormError("");
    } catch (error) { setMessage(""); setFormError(messageFrom(error)); }
    finally { mutationBusy.current = false; setMutating(false); }
  }
  async function checkDepth() {
    const generation = ++probeGeneration.current;
    setChecking(true); setDepth(undefined);
    let result: DepthCapability;
    try { result = await probeDepthCapability(browserDepthEnvironment()); }
    catch { result = { state: "unknown", depthApiExposed: false, depth: "unverified", infrared: "unverified", captureEnabled: false,
      message: "The browser capability check could not complete. Depth and infrared support remain unknown; you can retry." }; }
    if (generation === probeGeneration.current) { setDepth(result); setChecking(false); }
  }
  function select(key: keyof Draft, label: string, options: readonly string[], required = false) {
    return <label>{label}<select aria-label={label} disabled={mutating} value={draft[key]} onChange={(event) => change(key, event.target.value)}>
      {required && <option value="">Choose your answer</option>}
      {options.map((option) => <option key={option} value={option}>{labels[option] ?? option}</option>)}
    </select></label>;
  }
  let reading;
  try { if (loaded && !storageError && draft.house.trim()) reading = inferHouseFit(history, draft as FitScope); }
  catch { /* Invalid/incomplete scope produces no inference; saving explains the invalid field. */ }

  return <div className={styles.stack}>
    <section className={styles.card} aria-labelledby="fit-history-heading">
      <p className={styles.eyebrow}>Tier 1 · Start with what you know</p>
      <h2 id="fit-history-heading">Your fit, house by house</h2>
      <span className={styles.fidelity}>Self-reported history · non-calibrated</span>
      <p>Tell us about garments you have worn and the silhouette you prefer. Your answers can suggest a starting size within the same house, category and size system. They do not measure your body or guarantee fit.</p>
      <p className={styles.muted}>Guest notes save only when you choose Save. They stay in this browser profile and may be visible to someone sharing it. Nothing is sent to a brand, and no body photos or measurements are collected here.</p>
      {!loaded && <p role="status">Opening your device fit history…</p>}
      {loaded && !canMutate && <p className={styles.notice} role="status">{FIT_HISTORY_READ_ONLY}</p>}
      {mutating && <p role="status">Updating fit notes on this device…</p>}
      {storageError && <div className={`${styles.notice} ${styles.error}`} role="alert"><p>{storageError}</p><button onClick={loadHistory}>Retry reading fit history</button></div>}
      <form onSubmit={save} className={styles.stack} noValidate>
        <div className={styles.formGrid}>
          <label>House or brand<input disabled={mutating} autoComplete="off" maxLength={64} value={draft.house} onChange={(event) => change("house", event.target.value)} placeholder="The label on your garment" /></label>
          {select("category", "Garment category", fitCategories)}
          {select("sizeSystem", "Size system", sizeSystems)}
          {select("preference", "How do you like this category to sit?", fitPreferences)}
        </div>
        <p className={styles.muted}>Sizes never transfer automatically between houses, categories or size systems. Changing your silhouette preference starts a separate reading.</p>
        <fieldset className={styles.intakeFields}>
          <legend>A garment you have worn</legend>
          <div className={styles.formGrid}>
            <label>Garment reference<input disabled={mutating} autoComplete="off" maxLength={80} value={draft.garment} onChange={(event) => change("garment", event.target.value)} placeholder="Model or your own short name" /></label>
            <label>Size on the label<input disabled={mutating} autoComplete="off" maxLength={20} value={draft.size} onChange={(event) => change("size", event.target.value)} placeholder="For example M or 40" /></label>
            {select("outcome", "How did it feel?", fitOutcomes, true)}
            {select("movement", "Could you move comfortably?", ["free", "restricted"], true)}
            {select("adjustment", "Where would you ask a tailor for an adjustment?", fitAdjustments, true)}
          </div>
        </fieldset>
        <p className={styles.muted}>Use the same reference to correct a garment's note. Repeating the same garment does not increase the evidence count.</p>
        <div className={styles.row}>
          <button type="submit" className={styles.primary} disabled={!loaded || !!storageError || !canMutate || mutating}>Save fit note on this device</button>
          <button type="button" disabled={mutating} onClick={() => { setDraft(freshDraft()); setFormError(""); setMessage("Draft answers cleared. Saved notes remain available below."); }}>Clear draft answers</button>
        </div>
      </form>
      {formError && <p role="alert" className={`${styles.notice} ${styles.error}`}>{formError}</p>}
      {message && <p role="status">{message}</p>}
      <div className={styles.notice} aria-live="polite" data-testid="house-fit-reading">
        <h3>Our best reading</h3>
        {reading ? <>
          <p>{reading.explanation}</p>
          <p className={styles.muted}>{reading.status === "limited-history" ? "Limited evidence: one garment." : reading.status === "repeated-history" ? "Repeated reports, still unvalidated." : reading.status === "mixed-history" ? "Mixed or unsuitable evidence." : "No evidence for this scope."} {reading.totalGarments} matching garment notes. No numerical confidence or calibrated fit claim.</p>
        </> : <p>Choose a house to review your saved experience. No reading is made from incomplete or unreadable history.</p>}
      </div>
      <h3>My saved fit notes ({history.notes.length})</h3>
      <p className={styles.muted}>Up to 100 garment notes. Deleting a note immediately removes it from the reading. Delete all fit history when using a shared device.</p>
      {history.notes.map((note) => <article className={styles.card} key={note.id} aria-label={`${note.house} ${note.garment} fit note`}>
        <p><strong>{note.house} · {note.garment} · {note.size}</strong></p>
        <p className={styles.muted}>{labels[note.category]} · {labels[note.sizeSystem] ?? note.sizeSystem} · {labels[note.preference]} · {labels[note.outcome]} · {labels[note.movement]} · {labels[note.adjustment]}</p>
        <p className={styles.muted}>Tier 1 · Self-reported · house-history-v1 · {note.recordedAt.slice(0, 10)}</p>
        <div className={styles.row}>
          <button disabled={mutating} onClick={() => { setDraft({ house: note.house, category: note.category, sizeSystem: note.sizeSystem, preference: note.preference,
            garment: note.garment, size: note.size, outcome: note.outcome, movement: note.movement, adjustment: note.adjustment }); setFormError(""); setMessage("Review or correct this note, then save."); }}>Review {note.garment}</button>
          <button disabled={!canMutate || mutating} aria-label={`Delete fit note ${note.house} ${note.garment}`} onClick={() => eraseNote(note.id)}>Delete note</button>
        </div>
      </article>)}
      <button onClick={eraseAll} disabled={!loaded || !canMutate || mutating}>Delete all fit history and reset</button>
    </section>
    <section className={styles.card} aria-labelledby="fit-geometry-heading">
      <p className={styles.eyebrow}>Tier 2 · Geometry, when evidence is ready</p>
      <h2 id="fit-geometry-heading">Photogrammetry and depth</h2>
      <span className={styles.fidelity}>Unavailable · no validated capture pipeline</span>
      <p>Photogrammetry is not connected. No images have been captured or reconstructed, so there is no geometry reading or confidence estimate to report. A generated try-on image is not measurement evidence.</p>
      <p className={styles.muted}>This tier needs an approved capture method, scale reference, image-quality checks, uncertainty and provenance, followed by comparison with physical measurements. Depth and infrared also need a verified device session. Tier 1 remains available without any scan.</p>
      <button disabled>Start photogrammetry capture · unavailable</button>
      <button onClick={checkDepth} disabled={checking}>{checking ? "Checking browser capability…" : "Check depth pathway availability"}</button>
      <p className={styles.muted}>This check reads browser capability only. It does not request camera access, open an AR session, infer a phone model or collect frames.</p>
      {depth && <div role="status" data-testid="depth-capability">
        <p>{depth.message}</p>
        <p className={styles.muted}>Depth API surface: {depth.depthApiExposed ? "exposed by browser; no frame data verified" : "not exposed in this page"}. Depth: unverified. Infrared: unverified. Capture remains disabled.</p>
      </div>}
      <button disabled>Start depth or infrared capture · unavailable</button>
      <p className={styles.notice}>Calibrated fit remains unavailable. A future Pod capture must carry its own provenance and reviewed calibration evidence; no Pod result exists in this guest flow.</p>
    </section>
  </div>;
}
