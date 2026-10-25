"use client";
import { useEffect, useRef, useState } from "react";
import { createGuestClosetRepository } from "../closet/repository";
import { readPreviews, savePreview, storePreview } from "./previewMedia";
import { deletePhotoPreview } from "./photoMedia";
import type { Asset } from "./types";
import styles from "./spatial.module.css";
type Capability = {
  enabled: boolean;
  provider: string;
  model: string;
  region: string;
  retention: string;
  appRetention: string;
  unavailable: string;
};
type Job = { id: string; state: string; image?: string; message?: string };
const endpoint = "/try/photo/api";
export function PhotoPreview({ asset }: { asset: Asset }) {
  const [cap, setCap] = useState<Capability>();
  const [source, setSource] = useState("");
  const [consent, setConsent] = useState(false);
  const [action, setAction] = useState(false);
  const actionLock = useRef(false);
  const [job, setJob] = useState<Job>();
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const generation = useRef(0),
    running = useRef(false),
    jobId = useRef<string | undefined>(undefined),
    mediaId = useRef<string | undefined>(undefined),
    operation = useRef<string | undefined>(undefined);
  useEffect(() => {
    let live = true;
    void fetch(endpoint)
      .then((r) => (r.ok ? r.json() : null))
      .then((c) => {
        if (live)
          setCap(
            c ?? { enabled: false, unavailable: "Provider not connected." },
          );
      })
      .catch(() => {
        if (live)
          setCap({
            enabled: false,
            unavailable: "Provider not connected.",
          } as Capability);
      });
    return () => {
      live = false;
      generation.current++;
      if (jobId.current)
        void fetch(`${endpoint}?id=${jobId.current}`, {
          method: "DELETE",
          keepalive: true,
        }).catch(() => undefined);
    };
  }, []);
  useEffect(() => {
    if (job?.state !== "running") return;
    let live = true;
    let checking = false;
    const timer = setInterval(() => {
      if (checking) return;
      checking = true;
      void fetch(`${endpoint}?id=${job.id}`)
        .then(async (r) => {
          if (!r.ok) throw Error("Job status unavailable");
          return r.json();
        })
        .then((j) => {
          if (live && j.id === jobId.current) {
            setJob(j);
            if (j.state !== "running") {
              setBusy(false);
              running.current = false;
              setMessage(j.message ?? "Preview ready. Compare before saving.");
            }
          }
        })
        .catch(() => {
          if (!live) return;
          setJob({ id: job.id, state: "unknown" });
          setBusy(false);
          running.current = false;
          setMessage(
            "Job status could not be confirmed. No new request was sent. Delete this app preview before starting another attempt.",
          );
        })
        .finally(() => {
          checking = false;
        });
    }, 700);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, [job?.id, job?.state]);
  async function pick(file?: File) {
    if (!file) return;
    const current = ++generation.current;
    setMessage("");
    setSource("");
    setConsent(false);
    operation.current = undefined;
    if (file.type !== "image/png" || file.size > 6 * 1024 * 1024) {
      setMessage("Use the supplied synthetic PNG test image under 6 MB.");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      if (current === generation.current) setSource(String(reader.result));
    };
    reader.readAsDataURL(file);
  }
  async function send() {
    if (running.current || !source || !consent) return;
    running.current = true;
    setBusy(true);
    setSaved(false);
    setMessage("Sending the reviewed test image…");
    const current = generation.current;
    operation.current ??= crypto.randomUUID();
    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          personBase64: source.split(",")[1],
          productSlug: asset.slug,
          consent: true,
          testOnly: true,
          operationId: operation.current,
        }),
      });
      const result = await response.json();
      if (!response.ok) throw Error(result.error);
      if (current !== generation.current) {
        void fetch(`${endpoint}?id=${result.id}`, { method: "DELETE" }).catch(
          () => undefined,
        );
        return;
      }
      jobId.current = result.id;
      setJob(result);
      setSource("");
      setBusy(result.state === "running");
      running.current = result.state === "running";
      setMessage(
        result.message ??
          (result.state === "running"
            ? "Processing your test preview…"
            : "Preview ready."),
      );
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Request failed.");
      setBusy(false);
      running.current = false;
    }
  }
  async function ensureMedia() {
    if (!job?.image) throw Error("Preview unavailable.");
    if (!mediaId.current)
      mediaId.current = await storePreview(
        await (await fetch(job.image)).blob(),
      );
    return mediaId.current;
  }
  async function localAction(fn: () => Promise<void>) {
    if (actionLock.current) return;
    actionLock.current = true;
    setAction(true);
    try {
      await fn();
    } catch (e) {
      setMessage(
        e instanceof Error
          ? e.message
          : "The change could not be saved. Retry.",
      );
    } finally {
      actionLock.current = false;
      setAction(false);
    }
  }
  async function discard() {
    await localAction(async () => {
      generation.current++;
      if (jobId.current) {
        const response = await fetch(`${endpoint}?id=${jobId.current}`, {
          method: "DELETE",
        });
        if (!response.ok && ![401, 404].includes(response.status))
          throw Error("Could not confirm server deletion. Retry.");
      }
      if (mediaId.current) await deletePhotoPreview(mediaId.current);
      jobId.current = undefined;
      mediaId.current = undefined;
      operation.current = undefined;
      setJob(undefined);
      setSource("");
      setConsent(false);
      setBusy(false);
      running.current = false;
      setSaved(false);
      setMessage(
        "App preview and linked closet references deleted. Provider-side deletion is not guaranteed.",
      );
    });
  }
  async function keep() {
    await localAction(async () => {
      await savePreview(await ensureMedia());
      setSaved(true);
      setMessage("Saved on this browser. You can delete it here.");
    });
  }
  async function add() {
    await localAction(async () => {
      const id = await ensureMedia();
      await savePreview(id);
      const repo = createGuestClosetRepository();
      const s = await repo.read();
      await repo.commit(
        {
          type: "add",
          input: {
            previewMediaId: id,
            productId: null,
            title: `Preview · ${asset.title}`,
            category: asset.category,
            status: "want",
            posterUrl: job!.image!,
            assetSlug: null,
            group: "unplaced",
            slot: 0,
          },
        },
        s.version,
        `photo-${job!.id}`,
      );
      setSaved(true);
      setMessage(
        "Added as a photo reference in your Unplaced tray. Deleting the preview also deletes this reference. No ownership or fit claim.",
      );
    });
  }
  const supported = ["overshirt", "tee", "knit", "jacket"].includes(asset.slug);
  return (
    <div className={styles.card}>
      <h2>A preview, never a promise of fit.</h2>
      <p>
        Photo try-on sends one reviewed person image and the chosen garment to
        an image-generation provider with separate consent.
      </p>
      {!cap?.enabled ? (
        <>
          <p>{cap?.unavailable ?? "Checking provider connection…"}</p>
          <button disabled>Photo preview unavailable</button>
        </>
      ) : (
        <>
          <p className={styles.notice}>
            Development only · synthetic test images. {cap.provider} /{" "}
            {cap.model} · {cap.region}.
          </p>
          <p>{cap.retention}</p>
          <p>{cap.appRetention}</p>
          {!supported ? (
            <p>
              This development flow supports the original upper-body garments
              only.
            </p>
          ) : (
            <>
              <a href="/demo/test-person/synthetic-adult.png" download>
                Download synthetic test image
              </a>
              <label>
                Review a test photo
                <input
                  type="file"
                  accept="image/png"
                  disabled={busy || !!job}
                  onChange={(e) => void pick(e.target.files?.[0])}
                />
              </label>
              {source && (
                <img
                  src={source}
                  alt="Reviewed synthetic input"
                  style={{ maxHeight: 300, maxWidth: "100%" }}
                />
              )}
              <label className={styles.checkbox}>
                <input
                  type="checkbox"
                  checked={consent}
                  disabled={busy || !!job}
                  onChange={(e) => setConsent(e.target.checked)}
                />
                I authorize sending this synthetic test image and garment to the
                named provider under the disclosed terms.
              </label>
              <button
                disabled={!source || !consent || busy || !!job}
                onClick={() => void send()}
              >
                Send test photo
              </button>
            </>
          )}
          {job && (
            <>
              <p>Preview status: {job.state}</p>
              {job.image && (
                <>
                  <p>Compare the synthetic input with the generated result.</p>
                  <div className={styles.photoComparison}>
                    <img
                      src="/demo/test-person/synthetic-adult.png"
                      alt="Original synthetic test input"
                      style={{ maxHeight: 400, maxWidth: "100%" }}
                    />
                    <img
                      src={job.image}
                      alt="Generated visual preview, not a fit estimate"
                      style={{ maxHeight: 400, maxWidth: "100%" }}
                    />
                  </div>
                  <p className={styles.fidelity}>
                    Generative visual preview · no fit or authenticity claim
                  </p>
                  <button
                    onClick={() => void keep()}
                    disabled={saved || action}
                  >
                    {saved ? "Saved on this browser" : "Save preview"}
                  </button>
                  <button disabled={action} onClick={() => void add()}>
                    Add photo reference to closet
                  </button>
                </>
              )}
              <button disabled={action} onClick={() => void discard()}>
                {busy ? "Cancel processing" : "Delete preview"}
              </button>
            </>
          )}
        </>
      )}
      <p role="status">{message}</p>
      <SavedPreviews />
    </div>
  );
}
function SavedPreviews() {
  const [items, setItems] = useState<Awaited<ReturnType<typeof readPreviews>>>(
    [],
  );
  const [show, setShow] = useState(false);
  const [error, setError] = useState("");
  const [deleting, setDeleting] = useState(false);
  async function refresh() {
    try {
      setItems(await readPreviews());
      setError("");
    } catch {
      setError("Saved previews could not be read. Close and reopen to retry.");
    }
  }
  async function remove(id: string) {
    if (deleting) return;
    setDeleting(true);
    try {
      await deletePhotoPreview(id);
      await refresh();
    } catch {
      setError(
        "Deletion could not finish. Retry to remove the remaining references and image.",
      );
    } finally {
      setDeleting(false);
    }
  }
  return (
    <details
      onToggle={(e) => {
        setShow(e.currentTarget.open);
        if (e.currentTarget.open) void refresh();
      }}
    >
      <summary>Saved previews on this browser</summary>
      {error && <p role="status">{error}</p>}
      {show &&
        items.map((item) => (
          <div key={item.id}>
            <span>
              {item.saved ? "Saved preview" : "Unsaved preview"} ·{" "}
              {new Date(item.createdAt).toLocaleString()}
            </span>
            <button disabled={deleting} onClick={() => void remove(item.id)}>
              Delete saved preview
            </button>
          </div>
        ))}
    </details>
  );
}
