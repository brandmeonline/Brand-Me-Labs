"use client";
import { lazy, Suspense, useCallback, useState } from "react";
import { useCloset } from "../closet/useCloset";
import { allAssets, photoOnly } from "./catalog";
import { fidelityLabels } from "./types";
import styles from "./spatial.module.css";
const ModelPreview = lazy(() =>
  import("./ModelPreview").then((m) => ({ default: m.ModelPreview })),
);
const LiveOverlay = lazy(() =>
  import("./LiveOverlay").then((m) => ({ default: m.LiveOverlay })),
);
export default function TryPage({ itemId }: { itemId: string }) {
  const { snapshot, error } = useCloset(),
    [mode, setMode] = useState("image"),
    [previewError, setPreviewError] = useState("");
  const failed = useCallback((message: string) => {
    setPreviewError(message);
    setMode("image");
  }, []);
  if (!snapshot)
    return (
      <section className={styles.root}>
        <h1>See it your way</h1>
        <p role="status">{error || "Opening your item…"}</p>
      </section>
    );
  const item = snapshot.items.find((i) => i.id === itemId),
    catalogItem = allAssets.find((a) => a.id === itemId || a.slug === itemId);
  if (!item && !catalogItem)
    return (
      <section className={styles.root}>
        <h1>Item unavailable</h1>
        <p>This item was removed or isn’t in this closet.</p>
        <a href="/closet">Return to your closet</a>
      </section>
    );
  const asset = allAssets.find((a) => a.slug === item?.assetSlug) ??
    catalogItem ?? {
      ...photoOnly,
      id: item!.id,
      title: item!.title,
      poster: item!.posterUrl,
    };
  const choices = [
    {
      id: "image",
      title: "Item image",
      detail: "No camera. The original visual reference.",
      enabled: true,
    },
    {
      id: "3d",
      title: "3D inspection",
      detail: asset.glb
        ? "Rotate the original approximate model."
        : "No 3D asset is available for this item.",
      enabled: !!asset.glb,
    },
    {
      id: "room",
      title: "Room placement",
      detail:
        "Place an object in space. Device verification is still required.",
      enabled: !!asset.glb,
    },
    {
      id: "live",
      title: "Live visual overlay",
      detail: "Local pose preview. Model and device evidence are missing.",
      enabled: true,
    },
    {
      id: "photo",
      title: "Photo try-on",
      detail: "Optional generated image. Provider not connected.",
      enabled: true,
    },
    {
      id: "fit",
      title: "Calibrated fit",
      detail: "Unavailable. No validated measurement and material pipeline.",
      enabled: false,
    },
  ];
  return (
    <section className={styles.root}>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>Preview with perspective</p>
          <h1>{asset.title}</h1>
          <p className={styles.muted}>
            Choose what you want to see before granting any permission.
          </p>
        </div>
        <a className={styles.button} href="/closet">
          Back to closet
        </a>
      </header>
      <div className={styles.modes}>
        {choices.map((c) => (
          <button
            key={c.id}
            className={`${styles.mode} ${mode === c.id ? styles.selected : ""}`}
            disabled={!c.enabled}
            aria-pressed={mode === c.id}
            onClick={() => {
              setMode(c.id);
              setPreviewError("");
            }}
          >
            <strong>{c.title}</strong>
            <span>{c.detail}</span>
          </button>
        ))}
      </div>
      <div className={styles.divider} />
      {previewError && (
        <p className={`${styles.notice} ${styles.error}`} role="alert">
          {previewError}
        </p>
      )}
      <div className={styles.workspace}>
        <div className={styles.stack}>
          {mode === "image" && (
            <div className={styles.preview}>
              <img
                src={asset.poster}
                width="600"
                height="760"
                alt={asset.title}
              />
            </div>
          )}
          {["3d", "room"].includes(mode) && (
            <Suspense fallback={<p role="status">Loading 3D inspection…</p>}>
              <ModelPreview
                asset={asset}
                roomAR={mode === "room"}
                onError={failed}
              />
            </Suspense>
          )}
          {mode === "live" && (
            <Suspense fallback={<p role="status">Opening preview controls…</p>}>
              <LiveOverlay asset={asset} />
            </Suspense>
          )}
          {mode === "photo" && (
            <div className={styles.card}>
              <h2>A preview, never a promise of fit.</h2>
              <p>
                Photo try-on would send a reviewed person photo and garment
                image to an approved image-generation provider. It requires
                separate explicit processing consent.
              </p>
              <p className={styles.muted}>
                No provider is connected. Provider region, processing terms,
                retention and deletion support must be verified before uploads
                can be enabled. No image chooser or upload request is active.
              </p>
              <p className={styles.notice}>
                When available: review your image → choose your garment → read
                the provider disclosure → explicitly send → compare, save or
                discard. Unsaved results are intended to expire after 24 hours;
                actual provider retention must be disclosed separately.
              </p>
              <button disabled>Photo preview unavailable</button>
              <button onClick={() => setMode("image")}>Use item image</button>
            </div>
          )}
          <span className={styles.fidelity}>
            {mode === "image"
              ? "Photo display"
              : mode === "photo"
                ? "Generative visual preview · unavailable"
                : mode === "live"
                  ? "Approximate visual overlay · unavailable"
                  : fidelityLabels[asset.fidelity]}
          </span>
        </div>
        <aside className={styles.inspector}>
          <p className={styles.eyebrow}>What this shows</p>
          <h2>Expression, with honest limits.</h2>
          <p className={styles.muted}>
            These are original fictional garments. The geometry is approximate;
            details, physical scale, drape, and back surfaces are authored
            interpretations.
          </p>
          <p className={styles.muted}>
            A room placement is not body try-on. A generated image is not
            calibrated fit. None of these previews verifies ownership or
            authenticity.
          </p>
          <a href="/style">Build a look with this piece ↗</a>
        </aside>
      </div>
    </section>
  );
}
