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
  const video = useRef<HTMLVideoElement>(null),
    session = useRef<CameraSession | undefined>(undefined),
    [state, setState] = useState<CameraState>("not_started"),
    [message, setMessage] = useState(""),
    [anchor, setAnchor] = useState<OverlayAnchor | null>(null);
  useEffect(() => {
    if (!video.current) return;
    const camera = new CameraSession(
      video.current,
      (next, error) => {
        setState(next);
        if (error) setMessage(error);
      },
      setAnchor,
    );
    session.current = camera;
    return () => camera.stop();
  }, []);
  return (
    <div className={styles.stack}>
      <div className={styles.preview}>
        <video
          ref={video}
          muted
          playsInline
          aria-label="Local camera preview"
        />
        {anchor && (
          <img
            className={styles.cameraOverlay}
            src={asset.poster}
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
            !model || !["not_started", "stopped", "unsupported"].includes(state)
          }
          onClick={() => model && void session.current?.start(model)}
        >
          Start local camera
        </button>
        <button onClick={() => session.current?.stop()}>Stop camera</button>
      </div>
      <p role="status">{message || state.replaceAll("_", " ")}</p>
      {!model && (
        <p className={styles.notice}>
          Live preview is unavailable: approved local pose-model assets and
          device evidence have not been supplied. No camera access is requested.
        </p>
      )}
    </div>
  );
}
