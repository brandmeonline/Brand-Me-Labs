/** Garment dimensional-error reporting. Even physical inputs do not validate drape or fit. */
export type GarmentEvidencePoint = {
  fixtureId: string;
  garmentRef: string;
  dimension: "chest" | "waist" | "hip";
  referenceCm: number;
  referenceUncertaintyCm: number;
  estimateCm: number;
};
export type GarmentEvidenceDataset = {
  schemaVersion: "garment-dimension-evidence-v1";
  kind: "synthetic-arithmetic" | "physical-garment";
  protocol: {
    referenceMethod: string;
    estimateMethod: string;
    revision: string;
    evidenceRef: string;
  };
  points: GarmentEvidencePoint[];
};

function record(value: unknown, keys: readonly string[], label: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value) || Object.keys(value).some((k) => !keys.includes(k)) || keys.some((k) => !Object.hasOwn(value, k))) throw Error(`${label} has missing or unsupported fields.`);
  return value as Record<string, unknown>;
}
function reference(value: unknown): string {
  if (typeof value !== "string" || !/^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,127}$/.test(value)) throw Error("Evidence references must be opaque IDs.");
  return value;
}
function numberInRange(value: unknown, min: number, max: number): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < min || value > max) throw Error("Evidence values must be finite and within the supported range.");
  return value;
}

export function parseGarmentEvidence(value: unknown): GarmentEvidenceDataset {
  const input = record(value, ["schemaVersion", "kind", "protocol", "points"], "Evidence dataset");
  if (input.schemaVersion !== "garment-dimension-evidence-v1" || !["synthetic-arithmetic", "physical-garment"].includes(input.kind as string)) throw Error("Unsupported evidence schema or kind.");
  const protocol = record(input.protocol, ["referenceMethod", "estimateMethod", "revision", "evidenceRef"], "Evidence protocol");
  if (!Array.isArray(input.points) || input.points.length < 1 || input.points.length > 10_000) throw Error("Evidence needs between 1 and 10,000 points.");
  const points: GarmentEvidencePoint[] = Array.from(input.points).map((value) => {
    const p = record(value, ["fixtureId", "garmentRef", "dimension", "referenceCm", "referenceUncertaintyCm", "estimateCm"], "Evidence point");
    if (!["chest", "waist", "hip"].includes(p.dimension as string)) throw Error("Unsupported garment dimension.");
    return {
      fixtureId: reference(p.fixtureId), garmentRef: reference(p.garmentRef), dimension: p.dimension as GarmentEvidencePoint["dimension"],
      referenceCm: numberInRange(p.referenceCm, 20, 300), referenceUncertaintyCm: numberInRange(p.referenceUncertaintyCm, 0, 20), estimateCm: numberInRange(p.estimateCm, 20, 300),
    };
  });
  if (new Set(points.map((p) => p.fixtureId)).size !== points.length) throw Error("Duplicate evidence fixture IDs would inflate the sample count.");
  if (new Set(points.map((p) => `${p.garmentRef}:${p.dimension}`)).size !== points.length) throw Error("Repeated garment dimensions must be combined before reporting independent points.");
  return {
    schemaVersion: "garment-dimension-evidence-v1", kind: input.kind as GarmentEvidenceDataset["kind"],
    protocol: { referenceMethod: reference(protocol.referenceMethod), estimateMethod: reference(protocol.estimateMethod), revision: reference(protocol.revision), evidenceRef: reference(protocol.evidenceRef) }, points,
  };
}

export function evaluateGarmentEvidence(value: unknown) {
  const dataset = parseGarmentEvidence(value);
  const errors = dataset.points.map((point) => point.estimateCm - point.referenceCm);
  const count = errors.length;
  const round = (n: number) => Math.round(n * 1_000_000) / 1_000_000;
  const mean = (numbers: number[]) => numbers.reduce((total, n) => total + n, 0) / numbers.length;
  const synthetic = dataset.kind === "synthetic-arithmetic";
  return {
    schemaVersion: dataset.schemaVersion,
    kind: dataset.kind,
    method: {
      ...dataset.protocol, errorDefinition: "estimateCm - referenceCm", aggregation: "unweighted per distinct garment/dimension; no population extrapolation",
      referenceUncertainty: "reported separately; not subtracted from error or treated as a statistical confidence interval",
    },
    fixtureCount: count,
    garmentCount: new Set(dataset.points.map((point) => point.garmentRef)).size,
    dimensionCount: new Set(dataset.points.map((point) => point.dimension)).size,
    metrics: {
      unit: "cm", meanSignedErrorCm: round(mean(errors)), meanAbsoluteErrorCm: round(mean(errors.map(Math.abs))),
      rootMeanSquareErrorCm: round(Math.sqrt(mean(errors.map((error) => error * error)))), maxAbsoluteErrorCm: round(Math.max(...errors.map(Math.abs))),
      meanReferenceUncertaintyCm: round(mean(dataset.points.map((point) => point.referenceUncertaintyCm))),
    },
    physicalBenchmark: {
      status: synthetic ? "NOT_RUN" : "INPUTS_RECORDED_UNVERIFIED",
      physicalGarmentCount: synthetic ? 0 : new Set(dataset.points.map((point) => point.garmentRef)).size,
      physicalMeasurementCount: synthetic ? 0 : count,
    },
    calibratedFitAvailable: false,
    limits: synthetic
      ? "Synthetic arithmetic verification only. No physical garment was measured; these numbers do not establish measurement accuracy, sizing, comfort, drape or fit."
      : "Metrics describe supplied physical-measurement records. Their authority and protocol are not independently verified here; dimensional error alone does not establish sizing, comfort, drape or fit.",
  };
}
