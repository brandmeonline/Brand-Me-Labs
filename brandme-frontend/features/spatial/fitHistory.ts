/** Tier 1 learns only from a guest's own reports. It is not a measurement or fit solver. */
export const FIT_HISTORY_KEY = "brandme:guest:spatial:fit-history:v1";
export const FIT_HISTORY_LOCK = "brandme:guest:spatial:fit-history:mutation";
export const fitCategories = ["tops", "bottoms", "one-piece", "outerwear", "footwear"] as const;
export const sizeSystems = ["letter", "US", "UK", "EU", "house-specific"] as const;
export const fitPreferences = ["tailored", "regular", "relaxed"] as const;
export const fitOutcomes = ["comfortable", "too-snug", "too-loose"] as const;
export const fitAdjustments = ["none", "shoulders", "chest", "waist", "hips", "length", "feet"] as const;
export type FitScope = {
  house: string;
  category: (typeof fitCategories)[number];
  sizeSystem: (typeof sizeSystems)[number];
  preference: (typeof fitPreferences)[number];
};
export type FitNoteInput = FitScope & {
  garment: string;
  size: string;
  outcome: (typeof fitOutcomes)[number];
  movement: "free" | "restricted";
  adjustment: (typeof fitAdjustments)[number];
};
export type FitNote = FitNoteInput & {
  id: string;
  recordedAt: string;
  provenance: {
    tier: "tier-1";
    source: "self-reported-history";
    method: "house-history-v1";
  };
};
export type FitHistory = { version: 1; notes: FitNote[] };
type LocalStore = Pick<Storage, "getItem" | "setItem" | "removeItem">;
export type FitHistoryCoordinator = <T>(action: () => T) => Promise<T>;
export const FIT_HISTORY_READ_ONLY = "This browser cannot safely coordinate fit storage across tabs. Saving and deleting notes are unavailable. You can review existing notes and clear draft answers; use browser site-data controls to remove saved notes.";

export function fitHistoryMutationsAvailable() {
  try { return typeof window !== "undefined" && window.isSecureContext === true && typeof navigator.locks?.request === "function"; }
  catch { return false; }
}
/** Every writer uses the same origin lock. No unlocked read/modify/write fallback.
 * https://www.w3.org/TR/2025/WD-web-locks-20250924/
 */
const browserCoordinator: FitHistoryCoordinator = async (action) => {
  if (!fitHistoryMutationsAvailable()) throw Error(FIT_HISTORY_READ_ONLY);
  const abort = new AbortController();
  const timer = setTimeout(() => abort.abort(), 5000);
  let entered = false;
  try {
    return await navigator.locks.request(FIT_HISTORY_LOCK, { mode: "exclusive", signal: abort.signal }, () => {
      entered = true;
      clearTimeout(timer);
      return action();
    });
  } catch (error) {
    if (!entered) throw Error("Fit storage is busy or unavailable. No change was made; please retry.");
    throw error;
  } finally { clearTimeout(timer); }
};
const MAX_NOTES = 100;
const MAX_BYTES = 100_000;
const INPUT_KEYS = ["house", "category", "sizeSystem", "preference", "garment", "size", "outcome", "movement", "adjustment"];
const PROVENANCE = { tier: "tier-1", source: "self-reported-history", method: "house-history-v1" } as const;

function record(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value) &&
    [Object.prototype, null].includes(Object.getPrototypeOf(value));
}
function exactKeys(value: Record<string, unknown>, keys: readonly string[]) {
  return Object.keys(value).length === keys.length && Object.keys(value).every((key) => keys.includes(key));
}
function choice<T extends string>(value: unknown, options: readonly T[], label: string): T {
  if (typeof value !== "string" || !options.includes(value as T)) throw Error(`Choose a valid ${label}.`);
  return value as T;
}
function shortText(value: unknown, label: string, max: number, size = false) {
  if (typeof value !== "string" || value.length > max * 2 || /[\u0000-\u001f\u007f]/u.test(value))
    throw Error(`Enter a valid ${label}.`);
  const normalized = value.normalize("NFKC").trim().replace(/\s+/gu, " ");
  const pattern = size ? /^[\p{L}\p{N}][\p{L}\p{N} ./-]*$/u : /^[\p{L}\p{N}][\p{L}\p{N} .&'’/_-]*$/u;
  if (!normalized || normalized.length > max || !pattern.test(normalized))
    throw Error(`Enter a valid ${label} (up to ${max} characters, without markup).`);
  return normalized;
}
function identity(value: string) { return value.toLowerCase(); }

export function validateFitNote(value: unknown): FitNoteInput {
  if (!record(value) || !exactKeys(value, INPUT_KEYS)) throw Error("Fit note has unexpected or missing fields.");
  return {
    house: shortText(value.house, "house or brand", 64),
    garment: shortText(value.garment, "garment reference", 80),
    size: shortText(value.size, "size label", 20, true),
    category: choice(value.category, fitCategories, "garment category"),
    sizeSystem: choice(value.sizeSystem, sizeSystems, "size system"),
    preference: choice(value.preference, fitPreferences, "preferred silhouette"),
    outcome: choice(value.outcome, fitOutcomes, "reported fit"),
    movement: choice(value.movement, ["free", "restricted"], "movement report"),
    adjustment: choice(value.adjustment, fitAdjustments, "adjustment area"),
  };
}
function sameScope(a: FitScope, b: FitScope) {
  return identity(a.house) === identity(b.house) && a.category === b.category &&
    a.sizeSystem === b.sizeSystem && a.preference === b.preference;
}
function sameGarment(a: FitNoteInput, b: FitNoteInput) {
  return sameScope(a, b) && identity(a.garment) === identity(b.garment);
}

export function parseFitHistory(raw: string | null): FitHistory {
  if (raw === null) return { version: 1, notes: [] };
  try {
    if (raw.length > MAX_BYTES) throw Error("Too large");
    const value: unknown = JSON.parse(raw);
    if (!record(value) || !exactKeys(value, ["version", "notes"]) || value.version !== 1 ||
      !Array.isArray(value.notes) || value.notes.length > MAX_NOTES) throw Error("Invalid history");
    const notes: FitNote[] = [];
    for (const entry of value.notes) {
      if (!record(entry) || !exactKeys(entry, [...INPUT_KEYS, "id", "recordedAt", "provenance"])) throw Error("Invalid entry");
      const input = validateFitNote(Object.fromEntries(INPUT_KEYS.map((key) => [key, entry[key]])));
      const provenance = entry.provenance;
      if (typeof entry.id !== "string" || !/^[a-zA-Z0-9-]{1,64}$/.test(entry.id) ||
        typeof entry.recordedAt !== "string" || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(entry.recordedAt) ||
        !Number.isFinite(Date.parse(entry.recordedAt)) || new Date(entry.recordedAt).toISOString() !== entry.recordedAt ||
        !record(provenance) || !exactKeys(provenance, Object.keys(PROVENANCE)) ||
        Object.entries(PROVENANCE).some(([key, expected]) => provenance[key] !== expected) ||
        notes.some((note) => note.id === entry.id || sameGarment(note, input))) throw Error("Invalid evidence");
      notes.push({ ...input, id: entry.id, recordedAt: entry.recordedAt, provenance: { ...PROVENANCE } });
    }
    return { version: 1, notes };
  } catch {
    throw Error("Saved fit notes could not be read. Delete fit history to reset it; nothing has been overwritten.");
  }
}
function readFitHistorySource(storage: LocalStore): string | null {
  try { return storage.getItem(FIT_HISTORY_KEY); }
  catch { throw Error("Device storage is unavailable. Fit notes could not be read."); }
}
export function readFitHistory(storage: LocalStore): FitHistory {
  return parseFitHistory(readFitHistorySource(storage));
}
function writeHistory(storage: LocalStore, history: FitHistory) {
  const raw = JSON.stringify(history);
  if (raw.length > MAX_BYTES) throw Error("Fit history is full. Delete an older note before saving another.");
  try { storage.setItem(FIT_HISTORY_KEY, raw); }
  catch { throw Error("Could not save fit notes on this device. Storage may be blocked or full."); }
  return history;
}
export async function saveFitNote(storage: LocalStore, value: unknown, coordinate = browserCoordinator): Promise<FitHistory> {
  const input = validateFitNote(value);
  const expectedSource = readFitHistorySource(storage);
  parseFitHistory(expectedSource);
  return coordinate(() => {
    const currentSource = readFitHistorySource(storage);
    const history = parseFitHistory(currentSource);
    // A queued draft must not recreate data removed by an earlier delete/reset.
    // The lock serializes writes; this check also rejects a draft based on older history.
    if (currentSource !== expectedSource) throw Error("Fit history changed while this note was waiting. Review the current notes before saving again.");
    const existing = history.notes.find((note) => sameGarment(note, input));
    if (!existing && history.notes.length >= MAX_NOTES) throw Error("Fit history is full. Delete an older note before saving another.");
    const note: FitNote = {
      ...input,
      id: existing?.id ?? crypto.randomUUID(),
      recordedAt: new Date().toISOString(),
      provenance: { ...PROVENANCE },
    };
    return writeHistory(storage, { version: 1, notes: [...history.notes.filter((n) => n.id !== note.id), note] });
  });
}
export async function deleteFitNote(storage: LocalStore, id: string, coordinate = browserCoordinator): Promise<FitHistory> {
  return coordinate(() => {
    const history = readFitHistory(storage);
    return writeHistory(storage, { version: 1, notes: history.notes.filter((note) => note.id !== id) });
  });
}
export async function clearFitHistory(storage: LocalStore, coordinate = browserCoordinator): Promise<FitHistory> {
  return coordinate(() => {
    try { storage.removeItem(FIT_HISTORY_KEY); }
    catch { throw Error("Could not delete fit history on this device. Try again when storage is available."); }
    return { version: 1, notes: [] };
  });
}
export type FitReading = {
  status: "no-history" | "limited-history" | "repeated-history" | "mixed-history";
  size: string | null;
  supportingGarments: number;
  totalGarments: number;
  calibratedFitAvailable: false;
  label: "Self-reported history · non-calibrated";
  explanation: string;
};
export function inferHouseFit(history: FitHistory, scope: FitScope): FitReading {
  // Revalidate at the inference boundary; imports and local storage are not trusted evidence.
  const notes = parseFitHistory(JSON.stringify(history)).notes;
  const safeScope = {
    house: shortText(scope.house, "house or brand", 64),
    category: choice(scope.category, fitCategories, "garment category"),
    sizeSystem: choice(scope.sizeSystem, sizeSystems, "size system"),
    preference: choice(scope.preference, fitPreferences, "preferred silhouette"),
  };
  const relevant = notes.filter((note) => sameScope(note, safeScope));
  const base = { totalGarments: relevant.length, calibratedFitAvailable: false as const, label: "Self-reported history · non-calibrated" as const };
  if (!relevant.length) return { ...base, status: "no-history", size: null, supportingGarments: 0,
    explanation: "No matching fit notes yet. Add a garment you have worn in this house, category, size system and preferred silhouette." };
  const sizes = new Map<string, FitNote[]>();
  for (const note of relevant) {
    const key = identity(note.size);
    sizes.set(key, [...(sizes.get(key) ?? []), note]);
  }
  const candidates = [...sizes.values()].filter((group) => group.every((note) =>
    note.outcome === "comfortable" && note.movement === "free" && note.adjustment === "none"));
  candidates.sort((a, b) => b.length - a.length);
  if (!candidates.length || (candidates[1] && candidates[0].length === candidates[1].length))
    return { ...base, status: "mixed-history", size: null, supportingGarments: 0,
      explanation: "Your reports do not support a single size starting point. Review the garment cut and size chart; changing size alone may not address an adjustment." };
  const best = candidates[0];
  return { ...base, status: best.length > 1 ? "repeated-history" : "limited-history", size: best[0].size,
    supportingGarments: best.length,
    explanation: `Your history favors ${best[0].size} for this scope, based on ${best.length} distinct garment${best.length === 1 ? "" : "s"} reported comfortable with free movement and no adjustments. Check the exact product's size chart and cut. This is not a physical size prediction.` };
}
