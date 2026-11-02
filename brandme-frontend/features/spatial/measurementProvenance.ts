/** Private, in-memory model. These records are not brand, analytics or public DTOs. */
export type MeasurementTier = "tier-1" | "tier-2" | "pod";
export type BodyDimension = "height" | "chest" | "waist" | "hip" | "shoulder" | "inseam";
export type MeasurementProvenance = {
  tier: MeasurementTier;
  measuredEntity: "body" | "garment-proxy";
  source: {
    kind: "self-reported" | "operator-measured" | "device-estimate" | "synthetic-fixture";
    reference: string;
  };
  method: { id: string; version: string };
  unit: "cm";
  capturedAt: string;
  uncertainty: {
    plusMinusCm: number;
    basis: "repeatability" | "device-estimate" | "reference-validation" | "unvalidated";
  };
};
export type BodyMeasurement = {
  id: string;
  subjectRef: string;
  dimension: BodyDimension;
  valueCm: number;
  provenance: MeasurementProvenance;
};

const bounds: Record<BodyDimension, readonly [number, number]> = {
  height: [100, 230], chest: [50, 200], waist: [45, 200],
  hip: [55, 220], shoulder: [20, 70], inseam: [35, 120],
};

/** Exact keys prevent accidental propagation of images, URLs or unrelated private data. */
export function exactRecord(value: unknown, keys: readonly string[], label: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw Error(`${label} must be an object.`);
  const record = value as Record<string, unknown>;
  if (Object.keys(record).some((key) => !keys.includes(key)) || keys.some((key) => !Object.hasOwn(record, key))) {
    throw Error(`${label} has missing or unsupported fields.`);
  }
  return record;
}
export function opaqueReference(value: unknown, label: string): string {
  if (typeof value !== "string" || !/^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,127}$/.test(value)) throw Error(`${label} must be an opaque reference.`);
  return value;
}
export function utcTimestamp(value: unknown, label: string): number {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(value)) throw Error(`${label} must be an ISO UTC timestamp.`);
  const time = Date.parse(value);
  if (!Number.isFinite(time) || new Date(time).toISOString() !== value) throw Error(`${label} is invalid.`);
  return time;
}
export function finiteNumber(value: unknown, min: number, max: number, label: string): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < min || value > max) throw Error(`${label} is outside the supported range.`);
  return value;
}
export function oneOf<T extends string>(value: unknown, allowed: readonly T[], label: string): T {
  if (typeof value !== "string" || !allowed.includes(value as T)) throw Error(`${label} is unsupported.`);
  return value as T;
}

/** Numeric plausibility is intake validation, never proof of physical accuracy. */
export function parseBodyMeasurement(value: unknown): BodyMeasurement {
  const r = exactRecord(value, ["id", "subjectRef", "dimension", "valueCm", "provenance"], "Measurement");
  const p = exactRecord(r.provenance, ["tier", "measuredEntity", "source", "method", "unit", "capturedAt", "uncertainty"], "Provenance");
  const source = exactRecord(p.source, ["kind", "reference"], "Measurement source");
  const method = exactRecord(p.method, ["id", "version"], "Measurement method");
  const uncertainty = exactRecord(p.uncertainty, ["plusMinusCm", "basis"], "Measurement uncertainty");
  const dimension = oneOf(r.dimension, Object.keys(bounds) as BodyDimension[], "Dimension");
  const tier = oneOf(p.tier, ["tier-1", "tier-2", "pod"], "Tier");
  const measuredEntity = oneOf(p.measuredEntity, ["body", "garment-proxy"], "Measured entity");
  if ((method.id === "garment-inseam-repeat" && measuredEntity !== "garment-proxy") || (tier === "pod" && measuredEntity !== "body")) throw Error("A garment proxy must not be promoted to a body measurement.");
  const kind = oneOf(source.kind, ["self-reported", "operator-measured", "device-estimate", "synthetic-fixture"], "Source kind");
  if ((tier === "pod" && kind === "self-reported") || (tier === "tier-2" && kind === "self-reported")) throw Error("A self-report cannot be promoted to a scan measurement.");
  utcTimestamp(p.capturedAt, "Measurement time");
  return {
    id: opaqueReference(r.id, "Measurement ID"), subjectRef: opaqueReference(r.subjectRef, "Subject reference"), dimension,
    valueCm: finiteNumber(r.valueCm, ...bounds[dimension], "Measurement value"),
    provenance: {
      tier, measuredEntity, source: { kind, reference: opaqueReference(source.reference, "Source reference") },
      method: { id: opaqueReference(method.id, "Method ID"), version: opaqueReference(method.version, "Method version") },
      unit: oneOf(p.unit, ["cm"], "Unit"), capturedAt: p.capturedAt as string,
      uncertainty: {
        plusMinusCm: finiteNumber(uncertainty.plusMinusCm, 0.01, 30, "Measurement uncertainty"),
        basis: oneOf(uncertainty.basis, ["repeatability", "device-estimate", "reference-validation", "unvalidated"], "Uncertainty basis"),
      },
    },
  };
}
