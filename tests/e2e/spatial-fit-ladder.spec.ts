import { test, expect, type Page } from "../../scripts/assets/node_modules/@playwright/test";
import {
  FIT_HISTORY_KEY, FIT_HISTORY_LOCK, clearFitHistory as clearPersistedHistory, deleteFitNote as deletePersistedNote, inferHouseFit, parseFitHistory,
  readFitHistory, saveFitNote as savePersistedNote, validateFitNote, type FitNoteInput, type FitHistoryCoordinator,
} from "../../brandme-frontend/features/spatial/fitHistory";
import { probeDepthCapability } from "../../brandme-frontend/features/spatial/depthCapabilities";

const report: FitNoteInput = { house: "Test House", category: "tops", sizeSystem: "letter", preference: "regular",
  garment: "Cotton shirt", size: "M", outcome: "comfortable", movement: "free", adjustment: "none" };
function memoryStorage() {
  const entries = new Map<string, string>();
  return { getItem: (key: string) => entries.get(key) ?? null,
    setItem: (key: string, value: string) => { entries.set(key, value); },
    removeItem: (key: string) => { entries.delete(key); } };
}
// Unit storage has one writer. Browser tests below exercise the real origin Web Lock.
const singleWriter: FitHistoryCoordinator = async (action) => action();
const saveFitNote = (storage: ReturnType<typeof memoryStorage>, value: unknown) => savePersistedNote(storage, value, singleWriter);
const deleteFitNote = (storage: ReturnType<typeof memoryStorage>, id: string) => deletePersistedNote(storage, id, singleWriter);
const clearFitHistory = (storage: ReturnType<typeof memoryStorage>) => clearPersistedHistory(storage, singleWriter);

test("fit learning isolates houses, categories, size systems and silhouette, and replaces repeat garments", async () => {
  const storage = memoryStorage();
  const first = await saveFitNote(storage, report);
  expect(inferHouseFit(first, report)).toMatchObject({ status: "limited-history", size: "M", supportingGarments: 1, calibratedFitAvailable: false });
  for (const scope of [{ ...report, house: "Other House" }, { ...report, category: "bottoms" as const },
    { ...report, sizeSystem: "EU" as const }, { ...report, preference: "relaxed" as const }])
    expect(inferHouseFit(first, scope)).toMatchObject({ status: "no-history", size: null });
  const updated = await saveFitNote(storage, { ...report, house: " test HOUSE ", garment: "cotton SHIRT", size: "L" });
  expect(updated.notes).toHaveLength(1);
  expect(updated.notes[0].id).toBe(first.notes[0].id);
  expect(inferHouseFit(updated, report)).toMatchObject({ size: "L", supportingGarments: 1 });
  const twice = await saveFitNote(storage, { ...report, garment: "Linen shirt", size: "L" });
  expect(inferHouseFit(twice, report)).toMatchObject({ status: "repeated-history", size: "L", supportingGarments: 2 });
  const otherHouse = await saveFitNote(storage, { ...report, house: "Other House", size: "S" });
  expect(inferHouseFit(otherHouse, report).size).toBe("L");
  expect(inferHouseFit(otherHouse, { ...report, house: "Other House" }).size).toBe("S");
  const deleted = await deleteFitNote(storage, first.notes[0].id);
  expect(inferHouseFit(deleted, report).supportingGarments).toBe(1);
  await clearFitHistory(storage);
  expect(storage.getItem(FIT_HISTORY_KEY)).toBeNull();
});

test("fit inference withholds a starting size for ties, discomfort, restriction and tailoring needs", async () => {
  for (const modification of [{ outcome: "too-snug" }, { outcome: "too-loose" }, { movement: "restricted" }, { adjustment: "chest" }]) {
    const storage = memoryStorage();
    await saveFitNote(storage, report);
    const history = await saveFitNote(storage, { ...report, ...modification, garment: "Second shirt" });
    expect(inferHouseFit(history, report)).toMatchObject({ status: "mixed-history", size: null });
  }
  const storage = memoryStorage();
  await saveFitNote(storage, report);
  const tie = await saveFitNote(storage, { ...report, garment: "Other cut", size: "L" });
  expect(inferHouseFit(tie, report)).toMatchObject({ status: "mixed-history", size: null });
  // A poor result for another size is not supporting evidence for the candidate.
  const changed = await saveFitNote(storage, { ...report, garment: "Other cut", size: "L", outcome: "too-loose" });
  expect(inferHouseFit(changed, report)).toMatchObject({ size: "M", supportingGarments: 1, totalGarments: 2 });
});

test("fit boundaries reject unsafe fields, malformed provenance, corrupt storage, duplicate evidence and unbounded history", async () => {
  for (const modification of [{ house: "<script>" }, { house: "x\nY" }, { house: "a".repeat(65) },
    { garment: "" }, { size: "<img>" }, { size: Infinity }, { sizeSystem: "made-up" }, { bodyMeasurements: { chest: 99 } }])
    expect(() => validateFitNote({ ...report, ...modification })).toThrow();
  expect(() => validateFitNote(JSON.parse('{"__proto__":{}}'))).toThrow();
  const storage = memoryStorage(), history = await saveFitNote(storage, report);
  for (const raw of ["not JSON", "x".repeat(100_001), JSON.stringify({ ...history, version: 2 }),
    JSON.stringify({ ...history, rawBodyData: [1, 2] }),
    JSON.stringify({ ...history, notes: [history.notes[0], history.notes[0]] }),
    JSON.stringify({ ...history, notes: [{ ...history.notes[0], recordedAt: "2026-02-31T00:00:00.000Z" }] }),
    JSON.stringify({ ...history, notes: [{ ...history.notes[0], provenance: { ...history.notes[0].provenance, tier: "pod" } }] })]) {
    storage.setItem(FIT_HISTORY_KEY, raw);
    expect(() => readFitHistory(storage)).toThrow(/nothing has been overwritten/);
    await expect(saveFitNote(storage, report)).rejects.toThrow();
    expect(storage.getItem(FIT_HISTORY_KEY)).toBe(raw);
  }
  await clearFitHistory(storage);
  for (let i = 0; i < 100; i++) await saveFitNote(storage, { ...report, garment: `Garment ${i}` });
  await expect(saveFitNote(storage, { ...report, garment: "Overflow garment" })).rejects.toThrow(/history is full/);
  expect((await saveFitNote(storage, { ...report, garment: "Garment 0", size: "L" })).notes).toHaveLength(100);
  expect(() => inferHouseFit({ ...history, notes: [{ ...history.notes[0], size: "<bad>" }] }, report)).toThrow();
  expect(parseFitHistory(null).notes).toEqual([]);
});

test("failed device writes and deletions preserve existing evidence and never assert success", async () => {
  const storage = memoryStorage(), history = await saveFitNote(storage, report), original = storage.getItem(FIT_HISTORY_KEY);
  const blocked = { ...storage, setItem: () => { throw Error("QuotaExceededError"); }, removeItem: () => { throw Error("SecurityError"); } };
  await expect(saveFitNote(blocked, { ...report, garment: "Second shirt" })).rejects.toThrow(/Could not save/);
  await expect(deleteFitNote(blocked, history.notes[0].id)).rejects.toThrow(/Could not save/);
  await expect(clearFitHistory(blocked)).rejects.toThrow(/Could not delete/);
  expect(storage.getItem(FIT_HISTORY_KEY)).toBe(original);
  expect(() => readFitHistory({ ...storage, getItem: () => { throw Error("SecurityError"); } })).toThrow(/unavailable/);
});

test("depth capability uses feature results and never promotes AR or exposed APIs to depth capture", async () => {
  let calls = 0;
  const xr = { isSessionSupported: async () => { calls++; return true; } };
  expect(await probeDepthCapability({ secureContext: false, depthApiExposed: true, xr })).toMatchObject({ state: "insecure", captureEnabled: false });
  expect(calls).toBe(0);
  expect(await probeDepthCapability({ secureContext: true, depthApiExposed: false })).toMatchObject({ state: "no-webxr", depth: "unverified" });
  expect(await probeDepthCapability({ secureContext: true, depthApiExposed: true, xr })).toMatchObject({ state: "ar-available", depthApiExposed: true, depth: "unverified", infrared: "unverified", captureEnabled: false });
  expect(await probeDepthCapability({ secureContext: true, depthApiExposed: true, xr: { isSessionSupported: async () => false } })).toMatchObject({ state: "ar-unavailable", captureEnabled: false });
  expect(await probeDepthCapability({ secureContext: true, depthApiExposed: true, xr: { isSessionSupported: async () => { throw Error("denied"); } } })).toMatchObject({ state: "unknown", captureEnabled: false });
  expect(await probeDepthCapability({ secureContext: true, depthApiExposed: false, xr: { isSessionSupported: () => new Promise(() => {}) } }, 5)).toMatchObject({ state: "unknown", captureEnabled: false });
});

async function openFit(page: Page) {
  await page.goto("/try/overshirt");
  await page.getByRole("button", { name: /Find your fit/ }).click();
  await expect(page.getByRole("button", { name: "Save fit note on this device" })).toBeEnabled();
}
async function fillGarment(page: Page, garment = "Cotton shirt", size = "M") {
  await page.getByLabel("Garment reference", { exact: true }).fill(garment);
  await page.getByLabel("Size on the label", { exact: true }).fill(size);
  await page.getByRole("combobox", { name: "How did it feel?", exact: true }).selectOption("comfortable");
  await page.getByRole("combobox", { name: "Could you move comfortably?", exact: true }).selectOption("free");
  await page.getByRole("combobox", { name: "Where would you ask a tailor for an adjustment?", exact: true }).selectOption("none");
  await page.getByRole("button", { name: "Save fit note on this device" }).click();
}

test("guest fit questions persist, isolate each house and can be corrected and deleted without uploads", async ({ page }) => {
  const uploads: string[] = [];
  page.on("request", (request) => { if (request.method() === "POST") uploads.push(request.url()); });
  await openFit(page);
  await page.getByRole("button", { name: "Save fit note on this device" }).click();
  await expect(page.getByRole("alert")).toContainText("Enter a valid house");
  await page.getByLabel("House or brand", { exact: true }).fill("Test House");
  await fillGarment(page);
  await expect(page.getByTestId("house-fit-reading")).toContainText("Your history favors M");
  await expect(page.getByTestId("house-fit-reading")).toContainText("Limited evidence: one garment");
  await fillGarment(page, "Cotton shirt", "L");
  await expect(page.getByRole("article", { name: "Test House Cotton shirt fit note", exact: true })).toContainText("Test House · Cotton shirt · L");
  await expect(page.getByTestId("house-fit-reading")).toContainText("Your history favors L");
  await expect(page.getByRole("heading", { name: "My saved fit notes (1)" })).toBeVisible();
  await page.getByLabel("House or brand", { exact: true }).fill("Other House");
  await expect(page.getByLabel("Size on the label", { exact: true })).toHaveValue("");
  await expect(page.getByTestId("house-fit-reading")).toContainText("No matching fit notes");
  await fillGarment(page, "Second shirt", "S");
  // Saving takes the asynchronous origin lock; wait for the committed note before navigating.
  await expect(page.getByRole("article", { name: "Other House Second shirt fit note", exact: true })).toContainText("Other House · Second shirt · S");
  await expect(page.getByRole("heading", { name: "My saved fit notes (2)" })).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: /Find your fit/ }).click();
  await expect(page.getByRole("heading", { name: "My saved fit notes (2)" })).toBeVisible();
  await page.getByRole("button", { name: "Review Cotton shirt", exact: true }).click();
  await expect(page.getByTestId("house-fit-reading")).toContainText("Your history favors L");
  await page.getByRole("button", { name: "Delete fit note Test House Cotton shirt", exact: true }).click();
  await expect(page.getByLabel("House or brand", { exact: true })).toHaveValue("");
  await expect(page.getByLabel("Garment reference", { exact: true })).toHaveValue("");
  await expect(page.getByLabel("Size on the label", { exact: true })).toHaveValue("");
  await expect(page.getByRole("combobox", { name: "How did it feel?", exact: true })).toHaveValue("");
  await page.getByRole("button", { name: "Save fit note on this device" }).click();
  await expect(page.getByRole("alert")).toContainText("Enter a valid house");
  await expect(page.getByRole("heading", { name: "My saved fit notes (1)" })).toBeVisible();
  await page.getByRole("button", { name: "Delete all fit history and reset" }).click();
  await expect(page.getByRole("heading", { name: "My saved fit notes (0)" })).toBeVisible();
  await expect(page.getByLabel("House or brand", { exact: true })).toHaveValue("");
  expect(await page.evaluate((key) => localStorage.getItem(key), FIT_HISTORY_KEY)).toBeNull();
  expect(uploads).toEqual([]);
});

test("corrupt guest storage stays quarantined until explicit reset and unsafe answers do not create notes", async ({ page }) => {
  await page.addInitScript((key) => localStorage.setItem(key, "broken JSON"), FIT_HISTORY_KEY);
  await page.goto("/try/overshirt");
  await page.getByRole("button", { name: /Find your fit/ }).click();
  await expect(page.getByRole("alert")).toContainText("nothing has been overwritten");
  await expect(page.getByRole("button", { name: "Save fit note on this device" })).toBeDisabled();
  expect(await page.evaluate((key) => localStorage.getItem(key), FIT_HISTORY_KEY)).toBe("broken JSON");
  await page.getByRole("button", { name: "Delete all fit history and reset" }).click();
  await page.getByLabel("House or brand", { exact: true }).fill("<script>");
  await fillGarment(page);
  await expect(page.getByRole("alert")).toContainText("without markup");
  await expect(page.getByRole("heading", { name: "My saved fit notes (0)" })).toBeVisible();
  expect(await page.evaluate((key) => localStorage.getItem(key), FIT_HISTORY_KEY)).toBeNull();
});

test("storage failures retain data, recover on retry and deletions in another tab clear the reading", async ({ page, context }) => {
  await openFit(page);
  await page.getByLabel("House or brand", { exact: true }).fill("Test House");
  await page.evaluate((key) => {
    const original = Storage.prototype.setItem;
    (window as typeof window & { restoreFitStorage?: () => void }).restoreFitStorage = () => { Storage.prototype.setItem = original; };
    Storage.prototype.setItem = function (storageKey, value) { if (storageKey === key) throw Error("QuotaExceededError"); original.call(this, storageKey, value); };
  }, FIT_HISTORY_KEY);
  await fillGarment(page);
  await expect(page.getByRole("alert")).toContainText("Could not save");
  await expect(page.getByTestId("house-fit-reading")).toContainText("No matching fit notes");
  await page.evaluate(() => (window as typeof window & { restoreFitStorage?: () => void }).restoreFitStorage?.());
  await page.getByRole("button", { name: "Save fit note on this device" }).click();
  await expect(page.getByTestId("house-fit-reading")).toContainText("Your history favors M");
  const other = await context.newPage();
  await other.goto("/try/overshirt");
  await other.evaluate((key) => localStorage.removeItem(key), FIT_HISTORY_KEY);
  await expect(page.getByRole("heading", { name: "My saved fit notes (0)" })).toBeVisible();
  await expect(page.getByLabel("House or brand", { exact: true })).toHaveValue("");
  await expect(page.getByTestId("house-fit-reading")).not.toContainText("Your history favors");
});

test("fit saves, single deletes and resets serialize across tabs under the real origin lock", async ({ page, context }) => {
  await openFit(page);
  await page.getByLabel("House or brand", { exact: true }).fill("Test House");
  await fillGarment(page);
  await expect(page.getByRole("heading", { name: "My saved fit notes (1)" })).toBeVisible();
  const other = await context.newPage();
  await other.goto("/try/overshirt");
  async function holdLock() {
    await page.evaluate(async (name) => {
      await new Promise<void>((acquired) => {
        void navigator.locks.request(name, async () => {
          acquired();
          await new Promise<void>((release) => {
            (window as typeof window & { releaseFitLock?: () => void }).releaseFitLock = release;
          });
        });
      });
    }, FIT_HISTORY_LOCK);
  }
  async function pending(count: number) {
    await expect.poll(() => page.evaluate(async (name) =>
      (await navigator.locks.query()).pending?.filter((lock) => lock.name === name).length, FIT_HISTORY_LOCK)).toBe(count);
  }
  async function finish() {
    await page.evaluate(() => (window as typeof window & { releaseFitLock?: () => void }).releaseFitLock?.());
    await Promise.all([page, other].map((tab) => tab.evaluate(async () =>
      await (window as typeof window & { pendingFitMutation?: Promise<unknown> }).pendingFitMutation)));
  }
  await holdLock();
  await page.evaluate(async (note) => {
    const { saveFitNote } = await import("/brandme-frontend/features/spatial/fitHistory.ts");
    (window as typeof window & { pendingFitMutation?: Promise<unknown> }).pendingFitMutation = saveFitNote(localStorage, { ...note, garment: "Second shirt" });
  }, report);
  await pending(1);
  await other.evaluate(async () => {
    const { deleteFitNote, readFitHistory } = await import("/brandme-frontend/features/spatial/fitHistory.ts");
    const id = readFitHistory(localStorage).notes[0].id;
    (window as typeof window & { pendingFitMutation?: Promise<unknown> }).pendingFitMutation = deleteFitNote(localStorage, id);
  });
  await pending(2);
  // Neither mutation is allowed to read/modify/write while the origin lock is held elsewhere.
  expect(await other.evaluate((key) => JSON.parse(localStorage.getItem(key)!).notes.map((note: { garment: string }) => note.garment), FIT_HISTORY_KEY)).toEqual(["Cotton shirt"]);
  await finish();
  expect(await page.evaluate((key) => JSON.parse(localStorage.getItem(key)!).notes.map((note: { garment: string }) => note.garment), FIT_HISTORY_KEY)).toEqual(["Second shirt"]);

  await holdLock();
  await page.evaluate(async (note) => {
    const { saveFitNote } = await import("/brandme-frontend/features/spatial/fitHistory.ts");
    (window as typeof window & { pendingFitMutation?: Promise<unknown> }).pendingFitMutation = saveFitNote(localStorage, { ...note, garment: "Third shirt" });
  }, report);
  await pending(1);
  await other.evaluate(async () => {
    const { clearFitHistory } = await import("/brandme-frontend/features/spatial/fitHistory.ts");
    (window as typeof window & { pendingFitMutation?: Promise<unknown> }).pendingFitMutation = clearFitHistory(localStorage);
  });
  await pending(2);
  await finish();
  expect(await page.evaluate((key) => localStorage.getItem(key), FIT_HISTORY_KEY)).toBeNull();
  await expect(page.getByRole("heading", { name: "My saved fit notes (0)" })).toBeVisible();

  // Reverse the order: an already-entered draft waiting behind a deletion must not restore it.
  for (const removeAll of [false, true]) {
    await page.evaluate(async (note) => {
      const { saveFitNote } = await import("/brandme-frontend/features/spatial/fitHistory.ts");
      await saveFitNote(localStorage, note);
    }, report);
    await holdLock();
    await other.evaluate(async (all) => {
      const { clearFitHistory, deleteFitNote, readFitHistory } = await import("/brandme-frontend/features/spatial/fitHistory.ts");
      (window as typeof window & { pendingFitMutation?: Promise<unknown> }).pendingFitMutation = all
        ? clearFitHistory(localStorage)
        : deleteFitNote(localStorage, readFitHistory(localStorage).notes[0].id);
    }, removeAll);
    await pending(1);
    await page.evaluate(async (note) => {
      const { saveFitNote } = await import("/brandme-frontend/features/spatial/fitHistory.ts");
      (window as typeof window & { pendingFitMutation?: Promise<unknown> }).pendingFitMutation = saveFitNote(localStorage, note)
        .then(() => "unexpected-save", (error: Error) => error.message);
    }, report);
    await pending(2);
    await finish();
    expect(await page.evaluate(async () => await (window as typeof window & { pendingFitMutation?: Promise<unknown> }).pendingFitMutation))
      .toContain("Fit history changed while this note was waiting");
    expect(await page.evaluate(async () => {
      const { readFitHistory } = await import("/brandme-frontend/features/spatial/fitHistory.ts");
      return readFitHistory(localStorage).notes;
    })).toEqual([]);
  }
});

test("without cross-tab locking fit history is read-only and mutation APIs fail closed", async ({ page }) => {
  const storage = memoryStorage();
  await saveFitNote(storage, report);
  await page.addInitScript(({ key, raw }) => {
    localStorage.setItem(key, raw);
    Object.defineProperty(navigator, "locks", { configurable: true, value: undefined });
  }, { key: FIT_HISTORY_KEY, raw: storage.getItem(FIT_HISTORY_KEY)! });
  await page.goto("/try/overshirt");
  await page.getByRole("button", { name: /Find your fit/ }).click();
  await expect(page.getByText(/cannot safely coordinate fit storage across tabs/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Save fit note on this device" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Delete all fit history and reset" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Delete fit note Test House Cotton shirt" })).toBeDisabled();
  await page.getByRole("button", { name: "Review Cotton shirt", exact: true }).click();
  await expect(page.getByTestId("house-fit-reading")).toContainText("Your history favors M");
  await page.getByRole("button", { name: "Clear draft answers" }).click();
  await expect(page.getByLabel("Garment reference", { exact: true })).toHaveValue("");
  const failures = await page.evaluate(async (note) => {
    const { saveFitNote, deleteFitNote, clearFitHistory, readFitHistory } = await import("/brandme-frontend/features/spatial/fitHistory.ts");
    const id = readFitHistory(localStorage).notes[0].id;
    return (await Promise.allSettled([saveFitNote(localStorage, note), deleteFitNote(localStorage, id), clearFitHistory(localStorage)])).map((result) => result.status);
  }, report);
  expect(failures).toEqual(["rejected", "rejected", "rejected"]);
  expect(await page.evaluate((key) => localStorage.getItem(key), FIT_HISTORY_KEY)).toBe(storage.getItem(FIT_HISTORY_KEY));
});

test("tier 2 stays unavailable with no uploads or camera session even when a browser reports AR support", async ({ page }) => {
  await page.addInitScript(() => {
    const counts = { camera: 0, session: 0, support: 0 };
    (window as typeof window & { fitProbeCounts?: typeof counts }).fitProbeCounts = counts;
    Object.defineProperty(navigator, "xr", { configurable: true, value: {
      isSessionSupported: async () => { counts.support++; return true; },
      requestSession: async () => { counts.session++; throw Error("Must not request an AR session"); },
    } });
    Object.defineProperty(window, "XRDepthInformation", { configurable: true, value: class {} });
    if (navigator.mediaDevices) navigator.mediaDevices.getUserMedia = async () => { counts.camera++; throw Error("Must not request a camera"); };
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await openFit(page);
  await expect(page.getByRole("button", { name: /Calibrated fit/ })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Start photogrammetry capture · unavailable" })).toBeDisabled();
  await expect(page.locator('input[type="file"]')).toHaveCount(0);
  await page.getByRole("button", { name: "Check depth pathway availability" }).click();
  await expect(page.getByTestId("depth-capability")).toContainText("reports immersive AR support");
  await expect(page.getByTestId("depth-capability")).toContainText("Depth: unverified. Infrared: unverified. Capture remains disabled");
  await expect(page.getByRole("button", { name: "Start depth or infrared capture · unavailable" })).toBeDisabled();
  expect(await page.evaluate(() => (window as typeof window & { fitProbeCounts?: unknown }).fitProbeCounts)).toEqual({ camera: 0, session: 0, support: 1 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
