/** Tape-measure preparation and interval arithmetic. This is not a drape/fit solver. */
import { parseBodyMeasurement, utcTimestamp, type MeasurementProvenance } from "./measurementProvenance";
export const measurementDefinitions = {
  height: {
    label: "Height",
    min: 100,
    max: 230,
    help: "Barefoot against a wall; measure crown to floor.",
  },
  chest: {
    label: "Chest circumference",
    min: 50,
    max: 200,
    help: "Tape level around the fullest chest; breathe normally, do not compress.",
  },
  waist: {
    label: "Waist circumference",
    min: 45,
    max: 200,
    help: "Tape level at the natural waist; avoid pulling it tight.",
  },
  hip: {
    label: "Hip circumference",
    min: 55,
    max: 220,
    help: "Tape level around the fullest seat, feet together.",
  },
  shoulder: {
    label: "Shoulder width",
    min: 20,
    max: 70,
    help: "Ask a helper to measure between shoulder bone landmarks across the back.",
  },
  inseam: {
    label: "Inseam",
    min: 35,
    max: 120,
    help: "Use a well-fitting trouser, crotch seam to hem; record that method.",
  },
} as const;
export type MeasurementKey = keyof typeof measurementDefinitions;
export type MeasurementInput = Record<MeasurementKey, [number, number, number]>;
export type Calibration = {
  method: "manual-repeat-v1";
  unit: "cm";
  measurements: Record<
    MeasurementKey,
    { value: number; uncertainty: number; spread: number; provenance: MeasurementProvenance }
  >;
  valid: boolean;
  issues: string[];
};
export function calibrateMeasurements(input: MeasurementInput, capturedAt = new Date().toISOString()): Calibration {
  utcTimestamp(capturedAt, "Measurement time");
  const measurements = {} as Calibration["measurements"],
    issues: string[] = [];
  for (const key of Object.keys(measurementDefinitions) as MeasurementKey[]) {
    const def = measurementDefinitions[key],
      values = input?.[key];
    if (
      !Array.isArray(values) ||
      values.length !== 3 ||
      Array.from(values).some((n) => !Number.isFinite(n) || n < def.min || n > def.max)
    ) {
      issues.push(
        `${def.label}: enter three plausible measurements in centimeters.`,
      );
      continue;
    }
    const ordered = [...values].sort((a, b) => a - b),
      spread = ordered[2] - ordered[0];
    if (spread > 2)
      issues.push(
        `${def.label}: repeats differ by more than 2 cm; measure again.`,
      );
    // 1cm minimum is a conservative preparation default, not validated measurement error.
    measurements[key] = {
      value: Math.round(ordered[1] * 10) / 10,
      uncertainty: Math.max(1, spread / 2),
      spread,
      provenance: {
        tier: "tier-1",
        measuredEntity: key === "inseam" ? "garment-proxy" : "body",
        source: { kind: "self-reported", reference: "local-manual-preparation" },
        method: { id: key === "inseam" ? "garment-inseam-repeat" : "manual-tape-repeat", version: "v1" },
        unit: "cm", capturedAt,
        uncertainty: { plusMinusCm: Math.max(1, spread / 2), basis: "unvalidated" },
      },
    };
  }
  return {
    method: "manual-repeat-v1",
    unit: "cm",
    measurements,
    valid: !issues.length,
    issues,
  };
}
export type GarmentMeasurement = {
  circumferenceCm: number;
  uncertaintyCm: number;
  source: "measured-garment" | "supplier-spec" | "demo";
  revision: string;
};
export function compareCircumference(
  body: Calibration,
  key: "chest" | "waist" | "hip",
  garment: GarmentMeasurement,
) {
  const b = body?.measurements?.[key];
  if (
    !body?.valid || body.method !== "manual-repeat-v1" || body.unit !== "cm" ||
    !b ||
    !Number.isFinite(b.value) || !Number.isFinite(b.uncertainty) ||
    b.uncertainty < 1 || b.uncertainty > 30 || !Number.isFinite(b.spread) || b.spread < 0 || b.spread > 2 ||
    !garment || !["measured-garment", "supplier-spec", "demo"].includes(garment.source) ||
    !Number.isFinite(garment.circumferenceCm) ||
    garment.circumferenceCm < 20 ||
    garment.circumferenceCm > 300 ||
    !Number.isFinite(garment.uncertaintyCm) ||
    garment.uncertaintyCm < 0 ||
    garment.uncertaintyCm > 20 ||
    typeof garment.revision !== "string" || !/^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,127}$/.test(garment.revision)
  )
    throw Error(
      "Valid repeated body measurements and a versioned garment measurement are required.",
    );
  parseBodyMeasurement({ id: `manual-${key}`, subjectRef: "local-session", dimension: key, valueCm: b.value, provenance: b.provenance });
  if (b.provenance.tier !== "tier-1" || b.provenance.source.kind !== "self-reported" || b.provenance.uncertainty.plusMinusCm !== b.uncertainty) throw Error("Manual measurement provenance must match its uncertainty and tier.");
  const ease = garment.circumferenceCm - b.value,
    uncertainty = garment.uncertaintyCm + b.uncertainty;
  return {
    easeCm: ease,
    intervalCm: [ease - uncertainty, ease + uncertainty] as [number, number],
    calibratedFitAvailable: false,
    label: "Measurement comparison only",
    limits:
      "No validated pattern, material stretch, drape, body scan or physical fit outcome. Do not infer size or comfort from this interval.",
    source: garment.source,
    revision: garment.revision,
  };
}
