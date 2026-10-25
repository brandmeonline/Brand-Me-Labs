"use client";
import { useEffect, useState } from "react";
import {
  saveCamera,
  savedCameras,
  removeCamera,
  type CameraPose,
  type SavedCamera,
} from "./cameraPreferences";
import styles from "./spatial.module.css";
export function SavedCameraViews({
  roomId,
  getPose,
  onChoose,
}: {
  roomId: string;
  getPose: () => CameraPose | undefined;
  onChoose: (pose: CameraPose) => void;
}) {
  const [views, setViews] = useState<SavedCamera[]>([]),
    [name, setName] = useState(""),
    [message, setMessage] = useState("");
  useEffect(() => {
    setViews(savedCameras(roomId));
    setMessage("");
  }, [roomId]);
  return (
    <details className={styles.cameraSaves}>
      <summary>My saved camera views</summary>
      <p className={styles.muted}>
        Private to this browser. Orbit changes are remembered after one second
        idle.
      </p>
      <div className={styles.row}>
        <label>
          View name
          <input
            value={name}
            maxLength={48}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <button
          disabled={!name.trim()}
          onClick={() => {
            try {
              const pose = getPose();
              if (!pose)
                throw new Error("Wait for the 3D room to finish loading.");
              setViews(saveCamera(roomId, name, pose));
              setName("");
              setMessage("Camera view saved on this device.");
            } catch (error) {
              setMessage(
                error instanceof Error
                  ? error.message
                  : "Could not save this view. Device storage may be unavailable.",
              );
            }
          }}
        >
          Save camera view
        </button>
      </div>
      {views.map((view) => (
        <div className={styles.row} key={view.id}>
          <button onClick={() => onChoose(view)}>{view.name}</button>
          <button
            aria-label={`Delete camera view ${view.name}`}
            onClick={() => {
              try {
                setViews(removeCamera(roomId, view.id));
                setMessage("Saved camera view removed.");
              } catch {
                setMessage(
                  "Could not remove the view. Device storage may be unavailable.",
                );
              }
            }}
          >
            Remove
          </button>
        </div>
      ))}
      <p aria-live="polite" className={styles.muted}>
        {message}
      </p>
    </details>
  );
}
