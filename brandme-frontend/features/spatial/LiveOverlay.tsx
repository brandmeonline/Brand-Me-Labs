"use client";
import { useEffect, useRef, useState } from "react";
import {
  CameraSession,
  type CameraState,
  type OverlayAnchor,
} from "./cameraSession";
import type { Asset } from "./types";
import styles from "./spatial.module.css";
export function LiveOverlay({
  asset,
  model,
}: {
  asset: Asset;
  model?: { modelUrl: string; wasmRoot: string };
}) {
  const supported = ["overshirt", "tee", "knit", "jacket"].includes(asset.slug);
  const video = useRef<HTMLVideoElement>(null),
    session = useRef<CameraSession | undefined>(undefined),
    [state, setState] = useState<CameraState>("not_started"),
    [message, setMessage] = useState(""),
    [localModel, setLocalModel] = useState(model),
    [aspect, setAspect] = useState(4 / 3),
    [anchor, setAnchor] = useState<OverlayAnchor | null>(null);
  useEffect(() => {
    const abort = new AbortController();
    if (!model && process.env.NODE_ENV !== "production")
      void fetch("/demo/vision/manifest.json", { signal: abort.signal })
        .then((r) => (r.ok ? r.json() : null))
        .then((m) => {
          if (
            m?.developmentOnly === true &&
            m.runtime === "0.10.35" &&
            !abort.signal.aborted
          )
            setLocalModel({
              modelUrl: "/demo/vision/pose-lite-v1.task",
              wasmRoot: "/demo/vision/0.10.35/wasm",
            });
        })
        .catch(() => {});
    return () => abort.abort();
  }, [model]);
  useEffect(() => {
    if (!video.current) return;
    const camera = new CameraSession(
      video.current,
      (next, error) => {
        setState(next);
        setMessage(error ?? "");
      },
      setAnchor,
    );
    session.current = camera;
    return () => camera.stop();
  }, []);
  return (
    <div className={styles.stack}>
      <div
        className={`${styles.preview} ${styles.liveFrame}`}
        style={{ aspectRatio: aspect, width: `min(100%, ${aspect * 60}vh)` }}
      >
        <video
          ref={video}
          onLoadedMetadata={() => {
            if (video.current?.videoWidth)
              setAspect(video.current.videoWidth / video.current.videoHeight);
          }}
          muted
          playsInline
          aria-label="Local camera preview"
        />
        {anchor && (
          <img
            className={styles.cameraOverlay}
            src={`/demo/overlays/${asset.slug}.png`}
            alt="Approximate visual overlay"
            style={{
              left: `${(anchor.x - anchor.width / 2) * 100}%`,
              top: `${anchor.y * 100}%`,
              width: `${anchor.width * 100}%`,
              height: `${anchor.height * 100}%`,
              transform: `rotate(${anchor.angle}rad)`,
            }}
          />
        )}
      </div>
      <p className={styles.fidelity}>
        Approximate image overlay · no fit estimate · no arm occlusion
      </p>
      <p className={styles.muted}>
        Camera frames and pose landmarks stay on this device. Tracking fades
        when confidence is low. Leaving this view or backgrounding the page
        stops the camera.
      </p>
      <div className={styles.row}>
        <button
          disabled={
            !supported ||
            !localModel ||
            !["not_started", "stopped", "unsupported"].includes(state)
          }
          onClick={() => localModel && void session.current?.start(localModel)}
        >
          Start local camera
        </button>
        <button onClick={() => session.current?.stop()}>Stop camera</button>
      </div>
      <p role="status">{message || state.replaceAll("_", " ")}</p>
      {!supported && (
        <p className={styles.notice}>
          This development overlay supports the original upper-body garments
          only. Use 3D inspection for this item.
        </p>
      )}
      {localModel && (
        <p className={styles.notice}>
          Development preview · local MediaPipe model. Device and population
          accuracy validation is pending.
        </p>
      )}
      {!localModel && (
        <p className={styles.notice}>
          Live preview is unavailable: local model files have not been prepared
          for this development build. No camera access is requested.
        </p>
      )}
    </div>
  );
}
