import { test, expect } from "../../scripts/assets/node_modules/@playwright/test";

test("folded placement loads the authored variant and survives refresh and each room", async ({ page }, testInfo) => {
  await page.goto("/closet");
  await page.getByRole("button", { name: "Select Field Linen Overshirt", exact: true }).click();
  await page.getByRole("button", { name: "Move item", exact: true }).click();
  const row = page.getByRole("listitem").filter({ has: page.getByRole("button", { name: "Select Field Linen Overshirt", exact: true }) });
  const loaded = page.waitForResponse(r => r.url().endsWith("/overshirt/folded.glb") && r.ok());
  await row.locator("img").dragTo(page.locator('[data-drop-group="shelf.folded"][data-drop-slot="5"]'));
  await loaded;
  await expect(page.getByRole("status")).toContainText("Folded shelf, slot 6");
  await page.reload();
  const position = await page.evaluate(async () => {
    const { createGuestClosetRepository } = await import("/brandme-frontend/features/closet/repository.ts");
    return (await createGuestClosetRepository().read()).items.find(i => i.id === "guest-overshirt")!.placement.positionMeters;
  });
  expect(position).toEqual([0.4, 1.505, -1.17]);
  await page.evaluate(async () => {
    const { createGuestClosetRepository } = await import("/brandme-frontend/features/closet/repository.ts");
    const { assets } = await import("/brandme-frontend/features/spatial/catalog.ts");
    const repo = createGuestClosetRepository();
    let s = await repo.read();
    for (const [slot, slug] of ["tee", "jacket", "dress", "trousers"].entries()) {
      const item = s.items.find(i => i.assetSlug === slug)!;
      s = (await repo.commit({ type: "move", itemId: item.id, expectedItemVersion: item.version, group: "shelf.folded", slot }, s.version, crypto.randomUUID())).snapshot;
    }
    const a = assets.find(a => a.slug === "knit")!;
    await repo.commit({ type: "add", input: { productId: a.id, title: a.title, category: a.category, status: "owned", posterUrl: a.poster, assetSlug: a.slug, group: "shelf.folded", slot: 4 } }, s.version, crypto.randomUUID());
  });
  await page.reload();
  for (const room of ["walnut_atelier", "limestone_gallery", "garden_studio"]) {
    await page.getByLabel("Room environment").selectOption(room);
    await expect(page.locator("[data-room-ready]")).toHaveAttribute("data-room-ready", "true");
    await expect(page.locator("[data-room-phase]")).toHaveAttribute("data-room-phase", "steady");
    const saved = await page.evaluate(async () => {
      const { createGuestClosetRepository } = await import("/brandme-frontend/features/closet/repository.ts");
      const { roomById } = await import("/brandme-frontend/features/spatial/catalog.ts");
      const s = await createGuestClosetRepository().read();
      return { items: s.items.filter(i => i.placement.semanticGroup === "shelf.folded"), slots: roomById(s.roomId).groups.find(g => g.id === "shelf.folded")!.positions };
    });
    expect(saved.items).toHaveLength(6);
    saved.items.forEach(i => expect(i.placement.positionMeters).toEqual(saved.slots![i.placement.slotId]));
    await page.waitForTimeout(700); // Allow GLB decode/demand frames to settle for visual evidence.
    await page.screenshot({ path: testInfo.outputPath(`folded-${room}.png`), fullPage: true, animations: "disabled" });
  }
});

test("legacy folded coordinates migrate once and stale writes conflict without losing identity", async ({ page }) => {
  await page.goto("/closet");
  const result = await page.evaluate(async () => {
    const { createGuestClosetRepository, initialSnapshot } = await import("/brandme-frontend/features/closet/repository.ts");
    const repo = createGuestClosetRepository("spatial-folded-migration");
    await repo.read();
    const s = initialSnapshot(), item = s.items.find(i => i.id === "guest-overshirt")!;
    item.placement.semanticGroup = "shelf.folded";
    item.placement.slotId = 5;
    item.placement.positionMeters = [0.458333, 1.05, -1.15];
    s.capsules = [{ id: "saved-capsule", title: "Keep me", itemIds: [item.id] }];
    await new Promise<void>((resolve, reject) => {
      const open = indexedDB.open("spatial-folded-migration", 1);
      open.onsuccess = () => {
        const db = open.result, tx = db.transaction("closet", "readwrite");
        tx.objectStore("closet").put({ snapshot: s, operations: {} }, "state");
        tx.oncomplete = () => { db.close(); resolve(); };
        tx.onerror = () => reject(tx.error);
      };
    });
    let conflict = false;
    try { await repo.commit({ type: "preferences", simpleView: true }, 1, "stale-layout-write"); }
    catch (e) { conflict = (e as Error).constructor.name === "ClosetConflict"; }
    return { conflict, first: await repo.read(), second: await repo.read() };
  });
  expect(result.conflict).toBe(true);
  expect(result.first.version).toBe(2);
  expect(result.second).toEqual(result.first);
  expect(result.first.capsules![0].itemIds).toEqual(["guest-overshirt"]);
  const item = result.first.items.find(i => i.id === "guest-overshirt")!;
  expect(item.placement.positionMeters).toEqual([0.4, 1.505, -1.17]);
  expect(item.version).toBe(2);
});
