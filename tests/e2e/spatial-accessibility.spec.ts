import {
  test,
  expect,
  type Page,
} from "../../scripts/assets/node_modules/@playwright/test";
import type { ClosetSnapshot } from "../../brandme-frontend/features/spatial/types";

type StoredCloset = {
  snapshot: ClosetSnapshot;
  operations: Record<string, { digest: string; itemId?: string }>;
};

// Read the real durable record, including its operation ledger. Draft UI changes
// and failed transactions must not change either the snapshot or the ledger.
async function storedCloset(page: Page): Promise<StoredCloset> {
  return page.evaluate(() => new Promise<StoredCloset>((resolve, reject) => {
    const request = indexedDB.open("brandme.spatial.guest.v1", 1);
    request.onerror = () => reject(request.error);
    request.onsuccess = () => {
      const database = request.result;
      const transaction = database.transaction("closet", "readonly");
      const read = transaction.objectStore("closet").get("state");
      let state: StoredCloset;
      read.onsuccess = () => { state = read.result; };
      transaction.oncomplete = () => {
        database.close();
        resolve(state);
      };
      transaction.onerror = () => {
        database.close();
        reject(transaction.error);
      };
    };
  }));
}

const navigatorFor = (page: Page) => page.getByRole("group", {
  name: "Placement keyboard controls",
  exact: true,
});
const moveButton = (page: Page) => page.getByRole("button", {
  name: "Move item",
  exact: true,
});
const itemFrom = (state: StoredCloset) => state.snapshot.items.find(
  (item) => item.id === "guest-overshirt",
)!;
const movesIn = (state: StoredCloset) => Object.values(state.operations).filter(
  (operation) => JSON.parse(operation.digest).type === "move",
).length;

async function openPlacement(page: Page, hold = false) {
  await page.goto(`/closet${hold ? "?save-hold=1" : ""}`);
  await expect(page.getByRole("list", { name: "Wardrobe items" })).toBeVisible();
  await page.getByRole("button", { name: "Simple View", exact: true }).click();
  await expect.poll(async () => (await storedCloset(page)).snapshot.simpleView).toBe(true);
  await page.getByRole("button", {
    name: "Select Field Linen Overshirt",
    exact: true,
  }).press("Enter");
  await moveButton(page).press("Enter");
  await expect(navigatorFor(page)).toBeFocused();
}

async function releaseSave(page: Page) {
  await page.evaluate(() => window.dispatchEvent(new Event("brandme:test-release-save")));
}

test.beforeEach(async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
});

test("placement opens with instructions and native destination and slot keys remain draft edits", async ({ page }) => {
  await openPlacement(page);
  const before = await storedCloset(page);
  const navigation = navigatorFor(page);
  await expect(navigation).toHaveAccessibleDescription(/Arrow.*Enter.*Escape/);
  const destination = page.getByRole("combobox", { name: "Placement destination" });
  const slot = page.getByRole("combobox", { name: "Placement slot" });

  // Genuine native keyboard events expose the old ancestor key handler bug;
  // selectOption alone would bypass it.
  await destination.focus();
  await destination.press("ArrowDown");
  await expect(destination).toHaveValue("rail.right");
  await expect(slot).toHaveValue("0");
  await slot.focus();
  await slot.press("ArrowDown");
  await expect(slot).toHaveValue("1");
  await slot.press("Enter");
  await expect(navigation).toBeVisible();
  expect(await storedCloset(page)).toEqual(before);
});

test("placement navigator previews one destination and Escape or Cancel restores focus without a write", async ({ page }) => {
  await openPlacement(page);
  const before = await storedCloset(page);
  const navigation = navigatorFor(page);
  const slot = page.getByRole("combobox", { name: "Placement slot" });

  await navigation.press("ArrowRight");
  await expect(slot).toHaveValue("3");
  await expect(page.locator('[data-drop-group="rail.left"][data-drop-slot="3"]'))
    .toHaveAttribute("aria-pressed", "true");
  await expect(page.locator('[data-drop-group="rail.left"][data-drop-slot="2"]'))
    .toHaveAttribute("aria-pressed", "false");
  await navigation.press("Control+ArrowRight");
  await expect(slot).toHaveValue("3");
  await navigation.dispatchEvent("keydown", { key: "Enter", code: "Enter", repeat: true });
  expect(await storedCloset(page)).toEqual(before);

  await navigation.press("Escape");
  await expect(moveButton(page)).toBeFocused();
  await expect(page.getByRole("status")).toContainText("saved position is unchanged");
  expect(await storedCloset(page)).toEqual(before);

  await moveButton(page).press("Enter");
  await expect(slot).toHaveValue("2");
  await navigation.press("ArrowLeft");
  await page.getByRole("button", { name: "Cancel", exact: true }).press("Enter");
  await expect(moveButton(page)).toBeFocused();
  expect(await storedCloset(page)).toEqual(before);
});

test("navigator confirmation persists exactly one move and returns keyboard focus", async ({ page }) => {
  await openPlacement(page);
  const before = await storedCloset(page);
  await navigatorFor(page).press("ArrowRight");
  await navigatorFor(page).press("Enter");
  await expect(page.getByRole("status")).toContainText("Moved Field Linen Overshirt to Work rail, slot 4");
  await expect(moveButton(page)).toBeFocused();

  const after = await storedCloset(page);
  expect(itemFrom(after).placement.slotId).toBe(3);
  expect(itemFrom(after).version).toBe(itemFrom(before).version + 1);
  expect(after.snapshot.version).toBe(before.snapshot.version + 1);
  expect(movesIn(after)).toBe(movesIn(before) + 1);
  await page.reload();
  await expect(page.getByRole("list", { name: "Wardrobe items" })).toBeVisible();
  expect(await storedCloset(page)).toEqual(after);
});

test("pending placement cannot be cancelled or submitted twice and restores focus after the real commit", async ({ page }) => {
  await openPlacement(page, true);
  const before = await storedCloset(page);
  await navigatorFor(page).press("ArrowRight");
  const save = page.getByRole("button", { name: /^(Save placement|Saving placement…)$/ });
  const cancel = page.getByRole("button", { name: "Cancel", exact: true });
  await save.press("Enter");
  await expect(page.getByRole("status")).toContainText("Saving placement");
  await expect(save).toHaveAttribute("aria-disabled", "true");
  await expect(cancel).toHaveAttribute("aria-disabled", "true");
  await expect(save).toBeFocused();
  await expect(page.getByRole("combobox", { name: "Placement destination" })).toBeDisabled();
  await expect(page.getByRole("combobox", { name: "Placement slot" })).toBeDisabled();
  await save.press("Escape");
  await save.press("Enter");
  await cancel.dispatchEvent("click");
  await expect(navigatorFor(page)).toBeVisible();
  await expect(page.getByRole("status")).toContainText("Saving placement");
  expect(await storedCloset(page)).toEqual(before);
  await page.getByRole("button", {
    name: "Select Soft Pleat Trousers",
    exact: true,
  }).click();
  await expect(page.getByRole("complementary").getByRole("heading"))
    .toHaveText("Field Linen Overshirt");
  await save.focus();

  // Release the harness gate; the real IndexedDB transaction still supplies the
  // acknowledgment, version checks and durable operation receipt.
  await releaseSave(page);
  await expect(moveButton(page)).toBeFocused();
  await expect(page.getByRole("alert")).toHaveCount(0);
  const after = await storedCloset(page);
  expect(after.snapshot.version).toBe(before.snapshot.version + 1);
  expect(itemFrom(after).version).toBe(itemFrom(before).version + 1);
  expect(movesIn(after)).toBe(movesIn(before) + 1);
});

test("a completed pending move respects deliberate focus outside placement", async ({ page }) => {
  await openPlacement(page, true);
  await navigatorFor(page).press("ArrowRight");
  await navigatorFor(page).press("Enter");
  await expect(page.getByRole("status")).toContainText("Saving placement");
  const search = page.getByRole("searchbox", { name: "Search your closet" });
  await search.focus();
  await search.fill("Linen");
  await releaseSave(page);
  await expect(page.getByRole("status")).toContainText("Moved Field Linen Overshirt");
  await expect(moveButton(page)).toBeVisible();
  await expect(search).toBeFocused();
  expect(itemFrom(await storedCloset(page)).placement.slotId).toBe(3);
});

test("occupied-slot failure keeps the saved placement and keyboard retry usable", async ({ page }) => {
  await openPlacement(page);
  const before = await storedCloset(page);
  // The starter tee occupies Work rail slot 7. Let the real repository reject
  // this command instead of faking an error response in the harness.
  await page.getByRole("combobox", { name: "Placement slot" })
    .selectOption({ value: "6" });
  await expect(page.getByRole("combobox", { name: "Placement slot" }))
    .toHaveValue("6");
  await navigatorFor(page).press("Enter");
  await expect(page.getByRole("alert")).toContainText("That slot is occupied");
  await expect(navigatorFor(page)).toBeFocused();
  await expect(page.getByRole("combobox", { name: "Placement slot" })).toBeEnabled();
  expect(await storedCloset(page)).toEqual(before);

  await navigatorFor(page).press("ArrowRight");
  await navigatorFor(page).press("Enter");
  await expect(moveButton(page)).toBeFocused();
  await expect(page.getByRole("alert")).toHaveCount(0);
  const after = await storedCloset(page);
  expect(itemFrom(after).placement.slotId).toBe(7);
  expect(movesIn(after)).toBe(movesIn(before) + 1);
});
