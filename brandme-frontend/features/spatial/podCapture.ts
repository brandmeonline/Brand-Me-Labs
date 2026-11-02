import {
  exactRecord, opaqueReference, oneOf, parseBodyMeasurement, utcTimestamp,
  type BodyMeasurement, type BodyDimension,
} from "./measurementProvenance";

const DAY = 86_400_000;
export const POD_MODEL_VERSION = "pod-capture-v1" as const;
/** A proposed phase-two contract; no Pod device, persistence or server authorization is implemented. */
export type PodCapture = {
  schemaVersion: typeof POD_MODEL_VERSION;
  id: string;
  subjectRef: string;
  capturedAt: string;
  device: { stationRef: string; hardwareRevision: string; softwareRevision: string; calibrationRef: string };
  consent: {
    receiptRef: string;
    subjectRef: string;
    grantedAt: string;
    expiresAt: string;
    revokedAt: string | null;
    purposes: ("fit-personalization" | "cross-tier-calibration")[];
  };
  retention: {
    rawGeometry: "memory-only";
    measurementsExpireAt: string;
    deleteDerivedOnRevocation: true;
  };
  measurements: BodyMeasurement[];
};

export function parsePodCapture(value: unknown): PodCapture {
  const r = exactRecord(value, ["schemaVersion", "id", "subjectRef", "capturedAt", "device", "consent", "retention", "measurements"], "Pod capture");
  const device = exactRecord(r.device, ["stationRef", "hardwareRevision", "softwareRevision", "calibrationRef"], "Pod device");
  const consent = exactRecord(r.consent, ["receiptRef", "subjectRef", "grantedAt", "expiresAt", "revokedAt", "purposes"], "Pod consent");
  const retention = exactRecord(r.retention, ["rawGeometry", "measurementsExpireAt", "deleteDerivedOnRevocation"], "Pod retention");
  const subjectRef = opaqueReference(r.subjectRef, "Subject reference");
  const id = opaqueReference(r.id, "Capture ID");
  const capturedAt = utcTimestamp(r.capturedAt, "Capture time");
  const grantedAt = utcTimestamp(consent.grantedAt, "Consent time");
  const expiresAt = utcTimestamp(consent.expiresAt, "Consent expiry");
  const measurementExpiry = utcTimestamp(retention.measurementsExpireAt, "Measurement expiry");
  if (consent.subjectRef !== subjectRef || grantedAt > capturedAt || expiresAt <= capturedAt) throw Error("Capture requires matching consent valid at capture time.");
  if (consent.revokedAt !== null && utcTimestamp(consent.revokedAt, "Revocation time") <= capturedAt) throw Error("Capture cannot follow consent revocation.");
  if (measurementExpiry <= capturedAt || measurementExpiry > capturedAt + 30 * DAY || measurementExpiry > expiresAt) throw Error("Measurements must expire within consent and the proposed 30-day maximum.");
  if (retention.deleteDerivedOnRevocation !== true) throw Error("Revocation must invalidate derived calibration.");
  if (!Array.isArray(consent.purposes) || !consent.purposes.length || consent.purposes.length > 2 || new Set(consent.purposes).size !== consent.purposes.length) throw Error("Explicit, distinct consent purposes are required.");
  const purposes = Array.from(consent.purposes).map((purpose) => oneOf(purpose, ["fit-personalization", "cross-tier-calibration"] as const, "Consent purpose"));
  if (!purposes.includes("fit-personalization")) throw Error("Personal fit consent is required for capture.");
  if (!Array.isArray(r.measurements) || !r.measurements.length || r.measurements.length > 6) throw Error("Capture requires one to six supported body dimensions.");
  const measurements = Array.from(r.measurements).map(parseBodyMeasurement);
  if (new Set(measurements.map((m) => m.dimension)).size !== measurements.length || new Set(measurements.map((m) => m.id)).size !== measurements.length) throw Error("Capture measurement IDs and dimensions must be unique.");
  for (const m of measurements) {
    if (m.subjectRef !== subjectRef || m.provenance.tier !== "pod" || m.provenance.source.reference !== id || m.provenance.capturedAt !== r.capturedAt) throw Error("Every Pod measurement must be bound to this subject, capture and time.");
  }
  return {
    schemaVersion: oneOf(r.schemaVersion, [POD_MODEL_VERSION], "Pod schema"), id, subjectRef, capturedAt: r.capturedAt as string,
    device: {
      stationRef: opaqueReference(device.stationRef, "Station reference"), hardwareRevision: opaqueReference(device.hardwareRevision, "Hardware revision"),
      softwareRevision: opaqueReference(device.softwareRevision, "Software revision"), calibrationRef: opaqueReference(device.calibrationRef, "Device calibration reference"),
    },
    consent: {
      receiptRef: opaqueReference(consent.receiptRef, "Consent receipt"), subjectRef, grantedAt: consent.grantedAt as string,
      expiresAt: consent.expiresAt as string, revokedAt: consent.revokedAt as string | null, purposes,
    },
    retention: { rawGeometry: oneOf(retention.rawGeometry, ["memory-only"], "Geometry retention"), measurementsExpireAt: retention.measurementsExpireAt as string, deleteDerivedOnRevocation: true },
    measurements,
  };
}

/** The caller must also resolve the receipt against its authoritative consent service. */
export function requireActivePodCapture(value: unknown, now: string): PodCapture {
  const capture = parsePodCapture(value);
  const time = utcTimestamp(now, "Current time");
  if (capture.consent.revokedAt !== null || time < Date.parse(capture.capturedAt) || time >= Date.parse(capture.consent.expiresAt) || time >= Date.parse(capture.retention.measurementsExpireAt)) throw Error("Pod data is revoked, expired or not yet captured.");
  return capture;
}

export type PodCalibrationLink = {
  method: "paired-observation-difference-v1";
  podCaptureRef: string;
  podMeasurementRef: string;
  targetMeasurementRef: string;
  dimension: BodyDimension;
  targetTier: "tier-1" | "tier-2";
  targetMethod: BodyMeasurement["provenance"]["method"];
  correctionCm: number;
  uncertaintyCm: number;
  pairedAt: string;
  expiresAt: string;
  consentReceiptRef: string;
  generalizable: false;
  calibratedFitAvailable: false;
};

/** A single-person paired correction is not a population calibration or calibrated fit. */
export function linkPodCalibration(value: unknown, targetValue: unknown, now: string): PodCalibrationLink {
  const capture = requireActivePodCapture(value, now);
  const target = parseBodyMeasurement(targetValue);
  if (!capture.consent.purposes.includes("cross-tier-calibration")) throw Error("Cross-tier calibration needs its own consent purpose.");
  if (target.provenance.tier === "pod" || target.subjectRef !== capture.subjectRef) throw Error("Calibration requires a cheaper-tier measurement of the same subject.");
  if (target.provenance.measuredEntity !== "body") throw Error("A garment proxy cannot calibrate against a Pod body measurement.");
  const reference = capture.measurements.find((m) => m.dimension === target.dimension);
  if (!reference) throw Error("The Pod capture lacks the target dimension.");
  if ((reference.provenance.source.kind === "synthetic-fixture") !== (target.provenance.source.kind === "synthetic-fixture")) throw Error("Synthetic and physical observations cannot calibrate each other.");
  const targetTime = Date.parse(target.provenance.capturedAt);
  if (targetTime > Date.parse(now) || Math.abs(targetTime - Date.parse(capture.capturedAt)) > 30 * DAY) throw Error("Pair observations within the proposed 30-day window.");
  return {
    method: "paired-observation-difference-v1", podCaptureRef: capture.id, podMeasurementRef: reference.id,
    targetMeasurementRef: target.id, dimension: target.dimension, targetTier: target.provenance.tier,
    targetMethod: { ...target.provenance.method }, correctionCm: reference.valueCm - target.valueCm,
    uncertaintyCm: reference.provenance.uncertainty.plusMinusCm + target.provenance.uncertainty.plusMinusCm,
    pairedAt: now, expiresAt: capture.retention.measurementsExpireAt, consentReceiptRef: capture.consent.receiptRef,
    generalizable: false, calibratedFitAvailable: false,
  };
}

export type BrandFitOutcome = {
  schemaVersion: "brand-fit-outcome-v1";
  garmentRef: string;
  outcome: "reported-too-small" | "reported-good-fit" | "reported-too-large" | "unknown";
  basis: "wearer-report" | "unvalidated-estimate";
  calibratedFitAvailable: false;
};

/** Use ONLY this DTO at a future brand boundary. No subject/capture IDs, sizes or body values. */
export function projectBrandFitOutcome(value: unknown): BrandFitOutcome {
  const record = exactRecord(value, ["garmentRef", "outcome", "basis"], "Brand fit outcome input");
  const outcome = oneOf(record.outcome, ["reported-too-small", "reported-good-fit", "reported-too-large", "unknown"], "Fit outcome");
  const basis = oneOf(record.basis, ["wearer-report", "unvalidated-estimate"], "Outcome basis");
  if (basis === "unvalidated-estimate" && outcome !== "unknown") throw Error("An unvalidated estimate cannot claim a reported fit outcome.");
  return {
    schemaVersion: "brand-fit-outcome-v1", garmentRef: opaqueReference(record.garmentRef, "Garment reference"),
    outcome, basis, calibratedFitAvailable: false,
  };
}
