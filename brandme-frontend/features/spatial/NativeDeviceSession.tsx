"use client";
import { useCallback, useState } from "react";
import { ModelPreview } from "./ModelPreview";
import { assets } from "./catalog";
import styles from "./spatial.module.css";
export function NativeDeviceSession({
  enabled = false,
}: {
  enabled?: boolean;
}) {
  const [started, setStarted] = useState(false),
    [error, setError] = useState(""),
    [device, setDevice] = useState(""),
    [outcome, setOutcome] = useState("not_run");
  const failed = useCallback((s: string) => setError(s), []);
  if (!enabled)
    return (
      <section className={styles.root}>
        <h1>Device validation</h1>
        <p>
          Native AR is still unverified. Start the development device-test build
          described in the spatial lane status to collect evidence.
        </p>
        <a href="/try/overshirt">Return to preview</a>
      </section>
    );
  function exportReport() {
    const record = {
      schemaVersion: 1,
      recordedAt: new Date().toISOString(),
      device,
      reportedOutcome: outcome,
      userAgent: navigator.userAgent,
      secureContext: isSecureContext,
      asset: {
        id: assets[0].id,
        revision: assets[0].revision,
        glb: assets[0].glb,
        usdz: assets[0].usdz,
      },
      returnedContext: sessionStorage.getItem("brandme.ar.return"),
      approval: false,
      limitations:
        "Operator-entered result, not automatic capability approval. Attach a device recording and measurements.",
    };
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(record, null, 2)], { type: "application/json" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = "brandme-native-device-evidence.json";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return (
    <section className={styles.root}>
      <h1>Native AR device session</h1>
      <p className={styles.notice}>
        Development test only · approximate original garment. This mode collects
        evidence; it cannot approve a public capability.
      </p>
      <ol>
        <li>
          Record device model, OS/browser version and chosen Quick Look, Scene
          Viewer or WebXR path.
        </li>
        <li>
          On trusted HTTPS, load the object, find a floor, place it, cancel and
          return. Repeat after backgrounding and denied permission.
        </li>
        <li>
          Check the item context survives return and camera stops. Record a
          screen video, errors and time to first placement.
        </li>
        <li>
          Compare a known physical reference. Keep scale labeled approximate
          unless measured geometry and uncertainty are validated.
        </li>
      </ol>
      <label>
        Device, versions and AR path
        <input value={device} onChange={(e) => setDevice(e.target.value)} />
      </label>
      {!started ? (
        <button onClick={() => setStarted(true)} disabled={!device.trim()}>
          Begin device test
        </button>
      ) : (
        <ModelPreview asset={assets[0]} roomAR deviceTest onError={failed} />
      )}
      {error && <p role="alert">{error}</p>}
      <label>
        Observed outcome
        <select value={outcome} onChange={(e) => setOutcome(e.target.value)}>
          <option value="not_run">Not run</option>
          <option value="passed">Observed pass (recording required)</option>
          <option value="failed">Failed</option>
          <option value="unsupported">Unsupported</option>
        </select>
      </label>
      <button disabled={!device.trim()} onClick={exportReport}>
        Download device evidence record
      </button>
      <a href="/try/overshirt">Finish and return to item</a>
    </section>
  );
}
