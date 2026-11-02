import { test, expect } from "../../scripts/assets/node_modules/@playwright/test";
import { parseBodyMeasurement, type BodyMeasurement } from "../../brandme-frontend/features/spatial/measurementProvenance";
import { linkPodCalibration, parsePodCapture, projectBrandFitOutcome, requireActivePodCapture, type PodCapture } from "../../brandme-frontend/features/spatial/podCapture";
import { evaluateGarmentEvidence, type GarmentEvidenceDataset } from "../../brandme-frontend/features/spatial/fitEvidence";
import { calibrateMeasurements, compareCircumference, type MeasurementInput } from "../../brandme-frontend/features/spatial/fitCalibration";

const capturedAt = "2026-10-24T12:00:00.000Z";
const now = "2026-10-24T12:30:00.000Z";
const measurement = (): BodyMeasurement => ({
  id: "synthetic-pod-chest", subjectRef: "synthetic-subject", dimension: "chest", valueCm: 100,
  provenance: {
    tier: "pod", measuredEntity: "body", source: { kind: "synthetic-fixture", reference: "synthetic-pod-capture" },
    method: { id: "synthetic-pod", version: "v1" }, unit: "cm", capturedAt,
    uncertainty: { plusMinusCm: 0.5, basis: "unvalidated" },
  },
});
const capture = (): PodCapture => ({
  schemaVersion: "pod-capture-v1", id: "synthetic-pod-capture", subjectRef: "synthetic-subject", capturedAt,
  device: { stationRef: "synthetic-station", hardwareRevision: "v1", softwareRevision: "v1", calibrationRef: "synthetic-instrument-check" },
  consent: {
    receiptRef: "synthetic-consent", subjectRef: "synthetic-subject", grantedAt: "2026-10-24T11:59:00.000Z",
    expiresAt: "2026-10-25T12:00:00.000Z", revokedAt: null, purposes: ["fit-personalization", "cross-tier-calibration"],
  },
  retention: { rawGeometry: "memory-only", measurementsExpireAt: "2026-10-25T12:00:00.000Z", deleteDerivedOnRevocation: true },
  measurements: [measurement()],
});
const target = (): BodyMeasurement => ({
  ...measurement(), id: "synthetic-photo-chest", valueCm: 102,
  provenance: {
    ...measurement().provenance, tier: "tier-2", source: { kind: "synthetic-fixture", reference: "synthetic-photo-session" },
    method: { id: "synthetic-photogrammetry", version: "v1" }, uncertainty: { plusMinusCm: 2, basis: "unvalidated" },
  },
});

test("every body dimension requires bounded units, uncertainty, timestamp, source and method provenance", () => {
  expect(parseBodyMeasurement(measurement())).toEqual(measurement());
  for (const invalid of [
    null, { ...measurement(), valueCm: NaN }, { ...measurement(), valueCm: Infinity },
    { ...measurement(), imageUrl: "private-photo" },
    { ...measurement(), provenance: { ...measurement().provenance, unit: "in" } },
    { ...measurement(), provenance: { ...measurement().provenance, capturedAt: "2026-02-30T12:00:00.000Z" } },
    { ...measurement(), provenance: { ...measurement().provenance, source: { kind: "self-reported", reference: "a" } } },
    { ...measurement(), provenance: { ...measurement().provenance, method: { id: "scan" } } },
    { ...measurement(), provenance: { ...measurement().provenance, uncertainty: { plusMinusCm: 0, basis: "unvalidated" } } },
  ]) expect(() => parseBodyMeasurement(invalid)).toThrow();
});

test("Pod intake binds each measurement to its subject, capture and time", () => {
  expect(parsePodCapture(capture()).measurements).toHaveLength(1);
  for (const patch of [{ subjectRef: "another-subject" }, { id: "another-capture" }]) expect(() => parsePodCapture({ ...capture(), ...patch })).toThrow();
  expect(() => parsePodCapture({ ...capture(), measurements: [measurement(), measurement()] })).toThrow(/unique/);
  expect(() => parsePodCapture({ ...capture(), measurements: [{ ...measurement(), provenance: { ...measurement().provenance, tier: "tier-1" } }] })).toThrow();
  expect(() => parsePodCapture({ ...capture(), measurements: [{ ...measurement(), provenance: { ...measurement().provenance, capturedAt: now } }] })).toThrow();
  expect(() => parsePodCapture({ ...capture(), rawGeometryUrl: "private://geometry" })).toThrow();
  expect(() => parsePodCapture({ ...capture(), measurements: new Array(1) })).toThrow();
  expect(() => parsePodCapture({ ...capture(), consent: { ...capture().consent, purposes: ["fit-personalization", ,] } })).toThrow();
});

test("Pod use fails closed on revocation, expiry, future time and unbounded retention", () => {
  expect(requireActivePodCapture(capture(), now).id).toBe("synthetic-pod-capture");
  expect(() => requireActivePodCapture({ ...capture(), consent: { ...capture().consent, revokedAt: "2026-10-24T12:20:00.000Z" } }, now)).toThrow(/revoked/);
  expect(() => requireActivePodCapture(capture(), capture().consent.expiresAt)).toThrow(/expired/);
  expect(() => requireActivePodCapture(capture(), "2026-10-24T11:00:00.000Z")).toThrow();
  expect(() => parsePodCapture({ ...capture(), consent: { ...capture().consent, grantedAt: now } })).toThrow();
  expect(() => parsePodCapture({ ...capture(), consent: { ...capture().consent, revokedAt: "2026-10-24T11:59:30.000Z" } })).toThrow();
  expect(() => parsePodCapture({ ...capture(), consent: { ...capture().consent, expiresAt: "2026-12-01T12:00:00.000Z" }, retention: { ...capture().retention, measurementsExpireAt: "2026-12-01T12:00:00.000Z" } })).toThrow(/30-day/);
  expect(() => parsePodCapture({ ...capture(), retention: { ...capture().retention, rawGeometry: "persist-until-deleted" } })).toThrow();
  expect(() => parsePodCapture({ ...capture(), retention: { ...capture().retention, deleteDerivedOnRevocation: false } })).toThrow();
});

test("paired Pod correction carries both method references and conservative uncertainty without fit claims", () => {
  const result = linkPodCalibration(capture(), target(), now);
  expect(result.correctionCm).toBe(-2);
  expect(result.uncertaintyCm).toBe(2.5);
  expect(result.targetMethod).toEqual({ id: "synthetic-photogrammetry", version: "v1" });
  expect(result.podMeasurementRef).toBe("synthetic-pod-chest");
  expect(result.targetTier).toBe("tier-2");
  expect(result.generalizable).toBe(false);
  expect(result.calibratedFitAvailable).toBe(false);
  expect(result.expiresAt).toBe(capture().retention.measurementsExpireAt);
});

test("cross-tier calibration refuses wrong subjects, missing purpose, stale pairs and mixed real/synthetic data", () => {
  expect(() => linkPodCalibration(capture(), { ...target(), subjectRef: "different-person" }, now)).toThrow();
  expect(() => linkPodCalibration({ ...capture(), consent: { ...capture().consent, purposes: ["fit-personalization"] } }, target(), now)).toThrow(/own consent/);
  expect(() => linkPodCalibration(capture(), measurement(), now)).toThrow(/cheaper-tier/);
  expect(() => linkPodCalibration(capture(), { ...target(), provenance: { ...target().provenance, capturedAt: "2026-09-01T12:00:00.000Z" } }, now)).toThrow(/30-day/);
  expect(() => linkPodCalibration(capture(), { ...target(), provenance: { ...target().provenance, capturedAt: "2026-10-25T12:00:00.000Z" } }, now)).toThrow();
  expect(() => linkPodCalibration(capture(), { ...target(), provenance: { ...target().provenance, source: { kind: "device-estimate", reference: "real-device" } } }, now)).toThrow(/Synthetic and physical/);
  expect(() => linkPodCalibration(capture(), { ...target(), dimension: "waist" }, now)).toThrow(/lacks/);
  expect(() => linkPodCalibration(capture(), { ...target(), provenance: { ...target().provenance, measuredEntity: "garment-proxy" } }, now)).toThrow(/garment proxy/);
});

test("brand output is a fixed fit-outcome projection and rejects attached body data", () => {
  const input = { garmentRef: "garment-1", outcome: "reported-good-fit", basis: "wearer-report" };
  expect(projectBrandFitOutcome(input)).toEqual({ schemaVersion: "brand-fit-outcome-v1", ...input, calibratedFitAvailable: false });
  for (const patch of [{ bodyMeasurements: [measurement()] }, { subjectRef: "private-person" }, { rawGeometry: "private" }, { size: "M" }, { confidence: 1 }]) expect(() => projectBrandFitOutcome({ ...input, ...patch })).toThrow();
  expect(() => projectBrandFitOutcome({ ...input, basis: "unvalidated-estimate" })).toThrow();
  expect(projectBrandFitOutcome({ ...input, outcome: "unknown", basis: "unvalidated-estimate" }).calibratedFitAvailable).toBe(false);
});

const dataset = (): GarmentEvidenceDataset => ({
  schemaVersion: "garment-dimension-evidence-v1", kind: "synthetic-arithmetic",
  protocol: { referenceMethod: "invented-values", estimateMethod: "known-offsets", revision: "v1", evidenceRef: "synthetic-fixture-v1" },
  points: [
    { fixtureId: "a-chest", garmentRef: "a", dimension: "chest", referenceCm: 100, referenceUncertaintyCm: 0.5, estimateCm: 102 },
    { fixtureId: "a-waist", garmentRef: "a", dimension: "waist", referenceCm: 80, referenceUncertaintyCm: 0.5, estimateCm: 78 },
    { fixtureId: "b-hip", garmentRef: "b", dimension: "hip", referenceCm: 100, referenceUncertaintyCm: 0.5, estimateCm: 101 },
  ],
});

test("dimensional error reports sample counts, signed bias, MAE, RMSE and maxima against references", () => {
  const result = evaluateGarmentEvidence(dataset());
  expect(result.fixtureCount).toBe(3);
  expect(result.garmentCount).toBe(2);
  expect(result.dimensionCount).toBe(3);
  expect(result.metrics).toEqual({ unit: "cm", meanSignedErrorCm: 0.333333, meanAbsoluteErrorCm: 1.666667, rootMeanSquareErrorCm: 1.732051, maxAbsoluteErrorCm: 2, meanReferenceUncertaintyCm: 0.5 });
  expect(result.physicalBenchmark).toEqual({ status: "NOT_RUN", physicalGarmentCount: 0, physicalMeasurementCount: 0 });
  expect(result.limits).toMatch(/Synthetic arithmetic/);
  expect(result.calibratedFitAvailable).toBe(false);
  expect(JSON.stringify(result)).not.toContain('"referenceCm"');
});

test("error reporting rejects inflated counts, unknown provenance and malformed numeric input", () => {
  expect(() => evaluateGarmentEvidence({ ...dataset(), points: [] })).toThrow();
  expect(() => evaluateGarmentEvidence({ ...dataset(), points: new Array(1) })).toThrow();
  expect(() => evaluateGarmentEvidence({ ...dataset(), kind: "verified-fit" })).toThrow();
  expect(() => evaluateGarmentEvidence({ ...dataset(), points: [dataset().points[0], dataset().points[0]] })).toThrow(/Duplicate/);
  expect(() => evaluateGarmentEvidence({ ...dataset(), points: [dataset().points[0], { ...dataset().points[0], fixtureId: "duplicate-point" }] })).toThrow(/Repeated garment/);
  for (const estimateCm of [NaN, Infinity, -1, 500]) expect(() => evaluateGarmentEvidence({ ...dataset(), points: [{ ...dataset().points[0], estimateCm }] })).toThrow();
  expect(() => evaluateGarmentEvidence({ ...dataset(), protocol: { referenceMethod: "no-revision-or-evidence" } })).toThrow();
});

test("supplied physical records cannot self-certify calibrated fit or independent verification", () => {
  const result = evaluateGarmentEvidence({ ...dataset(), kind: "physical-garment" });
  expect(result.physicalBenchmark.status).toBe("INPUTS_RECORDED_UNVERIFIED");
  expect(result.calibratedFitAvailable).toBe(false);
  expect(result.limits).toMatch(/not independently verified/);
});

test("manual preparation exports provenance and forged body intervals fail closed", () => {
  const input: MeasurementInput = { height: [180, 180, 180], chest: [100, 100, 100], waist: [80, 80, 80], hip: [100, 100, 100], shoulder: [45, 45, 45], inseam: [80, 80, 80] };
  const result = calibrateMeasurements(input, capturedAt);
  expect(result.measurements.chest.provenance).toMatchObject({ tier: "tier-1", unit: "cm", capturedAt, source: { kind: "self-reported" }, uncertainty: { basis: "unvalidated", plusMinusCm: 1 } });
  const garment = { circumferenceCm: 108, uncertaintyCm: 0.5, source: "demo" as const, revision: "v1" };
  expect(compareCircumference(result, "chest", garment).intervalCm).toEqual([6.5, 9.5]);
  expect(calibrateMeasurements(null as unknown as MeasurementInput).valid).toBe(false);
  expect(calibrateMeasurements({ ...input, chest: [100, , 100] as MeasurementInput["chest"] }).valid).toBe(false);
  expect(result.measurements.inseam.provenance.measuredEntity).toBe("garment-proxy");
  result.measurements.chest.value = NaN;
  expect(() => compareCircumference(result, "chest", garment)).toThrow();
  result.measurements.chest.value = 100;
  result.measurements.chest.uncertainty = 2;
  expect(() => compareCircumference(result, "chest", garment)).toThrow(/provenance/);
});
