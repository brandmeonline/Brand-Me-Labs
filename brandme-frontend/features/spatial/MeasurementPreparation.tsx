"use client";
import { useState } from "react";
import {
  calibrateMeasurements,
  measurementDefinitions,
  type Calibration,
  type MeasurementInput,
  type MeasurementKey,
} from "./fitCalibration";
import styles from "./spatial.module.css";
export function MeasurementPreparation() {
  const [values, setValues] = useState<Record<string, string>>({}),
    [result, setResult] = useState<Calibration>();
  function assess() {
    const input = {} as MeasurementInput;
    for (const key of Object.keys(measurementDefinitions) as MeasurementKey[])
      input[key] = [0, 1, 2].map((i) =>
        Number(values[`${key}-${i}`] || NaN),
      ) as [number, number, number];
    setResult(calibrateMeasurements(input));
  }
  function exportRecord() {
    if (!result?.valid) return;
    const blob = new Blob(
      [
        JSON.stringify(
          {
            ...result,
            recordedAt: new Date().toISOString(),
            purpose:
              "Private measurement preparation; no calibrated fit assertion",
          },
          null,
          2,
        ),
      ],
      { type: "application/json" },
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "brandme-private-measurements.json";
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return (
    <div className={styles.card}>
      <h2>Prepare your measurements</h2>
      <p>
        Calibrated fit remains unavailable. Three independent tape measurements
        help check repeatability; they do not validate a fit simulation. Values
        stay in this view unless you download them, and clear when you leave.
      </p>
      <p>
        Use centimeters. Release and reposition the tape between repeats; have a
        helper where possible.
      </p>
      {Object.entries(measurementDefinitions).map(([key, def]) => (
        <fieldset key={key}>
          <legend>{def.label}</legend>
          <p>{def.help}</p>
          <div className={styles.row}>
            {[0, 1, 2].map((i) => (
              <label key={i}>
                Repeat {i + 1}
                <input
                  aria-label={`${def.label} repeat ${i + 1}`}
                  type="number"
                  inputMode="decimal"
                  min={def.min}
                  max={def.max}
                  step="0.1"
                  value={values[`${key}-${i}`] ?? ""}
                  onChange={(e) => {
                    setValues({ ...values, [`${key}-${i}`]: e.target.value });
                    setResult(undefined);
                  }}
                />
              </label>
            ))}
          </div>
        </fieldset>
      ))}
      <button onClick={assess}>Check measurement repeatability</button>
      <button
        onClick={() => {
          setValues({});
          setResult(undefined);
        }}
      >
        Clear measurements
      </button>
      {result && (
        <div role="status">
          {result.valid ? (
            <>
              <p>
                Repeats are consistent within the 2 cm preparation threshold.
                Physical accuracy has not been verified.
              </p>
              <button onClick={exportRecord}>
                Download private measurement record
              </button>
            </>
          ) : (
            <ul>
              {result.issues.map((x) => (
                <li key={x}>{x}</li>
              ))}
            </ul>
          )}
        </div>
      )}
      <p className={styles.notice}>
        Next validation needs a measured physical garment, pattern and material
        data, and observed fit outcomes. Approximate 3D meshes and generated
        images are not calibration inputs.
      </p>
    </div>
  );
}
