"use client";
import { useEffect, useRef, useState } from "react";
import type { Asset } from "./types";
import styles from "./spatial.module.css";
type Viewer = HTMLElement & {
  canActivateAR: boolean;
  activateAR: () => Promise<void>;
};
export function ModelPreview({
  asset,
  roomAR = false,
  verifiedDevice = false,
  deviceTest = false,
  onError,
}: {
  asset: Asset;
  roomAR?: boolean;
  verifiedDevice?: boolean;
  deviceTest?: boolean;
  onError: (message: string) => void;
}) {
  const host = useRef<HTMLDivElement>(null),
    viewer = useRef<Viewer | undefined>(undefined),
    [ready, setReady] = useState(false),
    [capable, setCapable] = useState(false),
    [status, setStatus] = useState("");
  useEffect(() => {
    let live = true;
    let cleanup = () => {};
    setReady(false);
    setCapable(false);
    async function load() {
      if (!asset.glb) return;
      try {
        await import("@google/model-viewer");
        if (!live) return;
        const element = document.createElement("model-viewer") as Viewer;
        viewer.current = element;
        for (const [key, value] of Object.entries({
          src: asset.glb,
          "ios-src": asset.usdz ?? "",
          poster: asset.poster,
          alt: `${asset.title}. Approximate 3D. Physical scale is not calibrated.`,
          "camera-controls": "",
          "touch-action": "pan-y",
          "shadow-intensity": ".5",
          "interaction-prompt": "none",
          "ar-modes": "webxr scene-viewer quick-look",
          "ar-scale": "fixed",
          "camera-orbit": "8deg 86deg auto",
        }))
          element.setAttribute(key, value);
        if (roomAR && (verifiedDevice || deviceTest))
          element.setAttribute("ar", "");
        const loaded = () => {
          setReady(true);
          setCapable(isSecureContext && element.canActivateAR);
        };
        const error = () =>
          onError(
            "The 3D model could not load. Your item image remains available.",
          );
        const ar = (event: Event) => {
          const value = (event as CustomEvent).detail?.status;
          setStatus(
            value === "session-started"
              ? "Move slowly to find a floor. Use the viewer’s exit control to return."
              : value === "failed"
                ? "Room placement is unavailable. Return to 3D inspection."
                : value === "not-presenting"
                  ? "Returned to your item."
                  : "",
          );
        };
        element.addEventListener("load", loaded);
        element.addEventListener("error", error);
        element.addEventListener("ar-status", ar);
        host.current?.replaceChildren(element);
        cleanup = () => {
          element.removeEventListener("load", loaded);
          element.removeEventListener("error", error);
          element.removeEventListener("ar-status", ar);
          element.remove();
          viewer.current = undefined;
        };
      } catch {
        if (live)
          onError(
            "3D inspection is unavailable in this browser. Use the product image.",
          );
      }
    }
    void load();
    return () => {
      live = false;
      cleanup();
    };
  }, [asset, roomAR, verifiedDevice, deviceTest, onError]);
  async function startAR() {
    if (
      !ready ||
      !capable ||
      (!verifiedDevice && !deviceTest) ||
      !viewer.current
    )
      return;
    try {
      sessionStorage.setItem(
        "brandme.ar.return",
        JSON.stringify({
          productId: asset.id,
          assetRevision: asset.revision,
          path: location.pathname,
        }),
      );
      await viewer.current.activateAR();
    } catch {
      setStatus("Could not start the native viewer. Your item is unchanged.");
    }
  }
  return (
    <div className={styles.stack}>
      <div className={styles.preview} ref={host}>
        <img src={asset.poster} alt={asset.title} />
      </div>
      {roomAR && (
        <>
          <p className={styles.muted}>
            Room placement shows an object in your space. Scale is approximate;
            this is not body try-on.
          </p>
          <button
            disabled={!ready || !capable || (!verifiedDevice && !deviceTest)}
            onClick={() => void startAR()}
          >
            {deviceTest ? "Test native room placement" : "Place in my room"}
          </button>
          {deviceTest && (
            <p className={styles.notice}>
              Development device test. Native AR is unverified; record the
              result before any capability activation. No calibrated scale
              claim.
            </p>
          )}
          {!verifiedDevice && !deviceTest && (
            <p className={styles.notice}>
              Native room placement has not been verified for this device in
              this build. Quick Look, Scene Viewer and WebXR remain gated until
              device testing is recorded.
            </p>
          )}
        </>
      )}
      <p role="status" className={styles.muted}>
        {status}
      </p>
    </div>
  );
}
