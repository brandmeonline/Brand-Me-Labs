import { test, expect } from "../../scripts/assets/node_modules/@playwright/test";
import {
  FIT_HISTORY_KEY, FIT_HISTORY_GENERATION_KEY, FIT_HISTORY_LOCK,
  clearFitHistory, readFitHistory, saveFitNote,
  type FitNoteInput, type FitHistoryCoordinator,
} from "../../brandme-frontend/features/spatial/fitHistory";

const note: FitNoteInput = {
  house: "Test House", garment: "Cotton shirt", category: "tops", sizeSystem: "letter",
  preference: "regular", size: "M", outcome: "comfortable", movement: "free", adjustment: "none",
};
const singleWriter: FitHistoryCoordinator = async (action) => action();
function memoryStorage() {
  const entries = new Map<string, string>();
  return {
    getItem: (key: string) => entries.get(key) ?? null,
    setItem: (key: string, value: string) => { entries.set(key, value); },
    removeItem: (key: string) => { entries.delete(key); },
  };
}
function queuedCoordinator() {
  const queue: (() => void)[] = [];
  const coordinate: FitHistoryCoordinator = <T>(action: () => T) => new Promise<T>((resolve, reject) => {
    queue.push(() => { try { resolve(action()); } catch (error) { reject(error); } });
  });
  return { coordinate, release: () => queue.shift()!() };
}

test("resetting empty history invalidates a queued first save and every later reset", async () => {
  const storage = memoryStorage();
  let lastGeneration: string | null = null;
  for (let i = 0; i < 2; i++) {
    const queue = queuedCoordinator();
    const reset = clearFitHistory(storage, queue.coordinate);
    const saved = saveFitNote(storage, note, queue.coordinate).then(() => "unexpected-save", (error: Error) => error.message);
    queue.release();
    await reset;
    queue.release();
    expect(await saved).toContain("Fit history changed while this note was waiting");
    expect(storage.getItem(FIT_HISTORY_KEY)).toBeNull();
    expect(readFitHistory(storage).notes).toEqual([]);
    const generation = storage.getItem(FIT_HISTORY_GENERATION_KEY);
    expect(generation).toMatch(/^[0-9a-f-]{36}$/);
    expect(generation).not.toBe(lastGeneration);
    lastGeneration = generation;
  }
  // A new, deliberate save after the reset remains available.
  expect((await saveFitNote(storage, note, singleWriter)).notes).toHaveLength(1);
});

test("corrupt or unreadable reset state rejects saves and an explicit reset repairs it", async () => {
  const storage = memoryStorage();
  for (const invalid of ["", "7", "private arbitrary text", "0".repeat(1000)]) {
    storage.setItem(FIT_HISTORY_GENERATION_KEY, invalid);
    await expect(saveFitNote(storage, note, singleWriter)).rejects.toThrow(/reset state could not be read/);
    expect(storage.getItem(FIT_HISTORY_KEY)).toBeNull();
  }
  const unreadable = { ...storage, getItem: (key: string) => {
    if (key === FIT_HISTORY_GENERATION_KEY) throw Error("SecurityError");
    return storage.getItem(key);
  } };
  await expect(saveFitNote(unreadable, note, singleWriter)).rejects.toThrow(/reset state could not be read/);
  await clearFitHistory(storage, singleWriter);
  expect((await saveFitNote(storage, note, singleWriter)).notes).toHaveLength(1);
});

test("failed reset storage never reports deletion or permits older queued drafts", async () => {
  const storage = memoryStorage();
  await saveFitNote(storage, note, singleWriter);
  const original = storage.getItem(FIT_HISTORY_KEY);
  const noMarkerWrite = { ...storage, setItem: (key: string, value: string) => {
    if (key === FIT_HISTORY_GENERATION_KEY) throw Error("QuotaExceededError");
    storage.setItem(key, value);
  } };
  await expect(clearFitHistory(noMarkerWrite, singleWriter)).rejects.toThrow(/Could not delete/);
  expect(storage.getItem(FIT_HISTORY_KEY)).toBe(original);
  expect(storage.getItem(FIT_HISTORY_GENERATION_KEY)).toBeNull();

  const queue = queuedCoordinator();
  const noDelete = { ...storage, removeItem: () => { throw Error("SecurityError"); } };
  const reset = clearFitHistory(noDelete, queue.coordinate).then(() => "unexpected-reset", (error: Error) => error.message);
  const saved = saveFitNote(storage, { ...note, size: "L" }, queue.coordinate).then(() => "unexpected-save", (error: Error) => error.message);
  queue.release();
  expect(await reset).toMatch(/Could not delete/);
  queue.release();
  expect(await saved).toContain("Fit history changed while this note was waiting");
  expect(storage.getItem(FIT_HISTORY_KEY)).toBe(original);
  // The marker contains no note values; retrying deletion can still succeed.
  expect(storage.getItem(FIT_HISTORY_GENERATION_KEY)).toMatch(/^[0-9a-f-]{36}$/);
  await clearFitHistory(storage, singleWriter);
  expect(storage.getItem(FIT_HISTORY_KEY)).toBeNull();
});

test("an empty reset across tabs clears draft answers and rejects a first save queued behind it", async ({ page, context }) => {
  await page.goto("/try/overshirt");
  await page.getByRole("button", { name: /Find your fit/ }).click();
  await page.getByLabel("House or brand", { exact: true }).fill(note.house);
  await page.getByLabel("Garment reference", { exact: true }).fill(note.garment);
  const other = await context.newPage();
  await other.goto("/try/overshirt");
  await other.getByRole("button", { name: /Find your fit/ }).click();
  await page.evaluate(async (name) => {
    await new Promise<void>((acquired) => {
      void navigator.locks.request(name, async () => {
        acquired();
        await new Promise<void>((release) => {
          (window as typeof window & { releaseFitResetLock?: () => void }).releaseFitResetLock = release;
        });
      });
    });
  }, FIT_HISTORY_LOCK);
  const pending = (count: number) => expect.poll(() => page.evaluate(async (name) =>
    (await navigator.locks.query()).pending?.filter((lock) => lock.name === name).length, FIT_HISTORY_LOCK)).toBe(count);
  try {
    await other.getByRole("button", { name: "Delete all fit history and reset" }).click();
    await pending(1);
    await page.evaluate(async (input) => {
      const { saveFitNote } = await import("/brandme-frontend/features/spatial/fitHistory.ts");
      (window as typeof window & { fitResetSave?: Promise<string> }).fitResetSave = saveFitNote(localStorage, input)
        .then(() => "unexpected-save", (error: Error) => error.message);
    }, note);
    await pending(2);
    await page.evaluate(() => (window as typeof window & { releaseFitResetLock?: () => void }).releaseFitResetLock?.());
    expect(await page.evaluate(async () => await (window as typeof window & { fitResetSave?: Promise<string> }).fitResetSave))
      .toContain("Fit history changed while this note was waiting");
    await expect(other.getByText("Fit history and draft answers deleted from this browser.", { exact: true })).toBeVisible();
    await expect(page.getByLabel("House or brand", { exact: true })).toHaveValue("");
    await expect(page.getByLabel("Garment reference", { exact: true })).toHaveValue("");
    expect(await page.evaluate((key) => localStorage.getItem(key), FIT_HISTORY_KEY)).toBeNull();

    // A second empty reset must also notify tabs, even though the history key is still absent.
    await page.getByLabel("House or brand", { exact: true }).fill(note.house);
    await other.getByRole("button", { name: "Delete all fit history and reset" }).click();
    await expect(page.getByLabel("House or brand", { exact: true })).toHaveValue("");
    expect(await page.evaluate((key) => localStorage.getItem(key), FIT_HISTORY_KEY)).toBeNull();
  } finally {
    await page.evaluate(() => (window as typeof window & { releaseFitResetLock?: () => void }).releaseFitResetLock?.());
    await other.close();
  }
});
