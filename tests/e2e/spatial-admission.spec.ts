import {
  test,
  expect,
} from "../../scripts/assets/node_modules/@playwright/test";

test("shoe admission rejects geometric overlap atomically and permits separated slots, undo and retry", async ({
  page,
}) => {
  await page.goto("/closet");
  const result = await page.evaluate(async () => {
    // @ts-ignore browser-side Vite module
    const { createGuestClosetRepository } = await import(
      "/brandme-frontend/features/closet/repository.ts"
    );
    const repo = createGuestClosetRepository("shoe-admission-test");
    const original = await repo.read();
    const input = {
      productId: null,
      title: "Second pair",
      category: "shoes",
      status: "owned",
      posterUrl: "/demo/garments/sneaker/poster.webp",
      assetSlug: "sneaker",
      group: "shelf.shoes",
      slot: 5,
    };
    let message = "";
    try {
      await repo.commit({ type: "add", input }, original.version, "shoe-op");
    } catch (e) {
      message = String(e);
    }
    const afterFailure = await repo.read();
    const committed = await repo.commit(
      { type: "add", input: { ...input, slot: 0 } },
      original.version,
      "shoe-op",
    );
    const replay = await repo.commit(
      { type: "add", input: { ...input, slot: 0 } },
      original.version,
      "shoe-op",
    );
    let moveError = "";
    try {
      await repo.commit(
        {
          type: "move",
          itemId: committed.itemId,
          expectedItemVersion: 1,
          group: "shelf.shoes",
          slot: 3,
        },
        committed.snapshot.version,
        "move-op",
      );
    } catch (e) {
      moveError = String(e);
    }
    const afterMove = await repo.read();
    const removed = await repo.commit(
      { type: "undo_add", itemId: committed.itemId, expectedItemVersion: 1 },
      afterMove.version,
      "undo-op",
    );
    return {
      original,
      afterFailure,
      message,
      committed,
      replay,
      moveError,
      afterMove,
      removed,
    };
  });
  expect(result.message).toContain("Not enough space");
  expect(result.afterFailure).toEqual(result.original);
  expect(result.replay).toEqual(result.committed);
  expect(result.moveError).toContain("Not enough space");
  expect(result.afterMove).toEqual(result.committed.snapshot);
  expect(result.removed.snapshot.items).toEqual(result.original.items);
});

test("concurrent shoe reservations admit one transaction and unplaced remains available", async ({
  page,
}) => {
  await page.goto("/closet");
  const result = await page.evaluate(async () => {
    // @ts-ignore browser-side Vite module
    const { createGuestClosetRepository } = await import(
      "/brandme-frontend/features/closet/repository.ts"
    );
    const a = createGuestClosetRepository("shoe-race-test"),
      b = createGuestClosetRepository("shoe-race-test");
    const s = await a.read();
    const input = {
      productId: null,
      title: "Pair",
      category: "shoes",
      status: "owned",
      posterUrl: "/demo/garments/sneaker/poster.webp",
      assetSlug: "sneaker",
      group: "shelf.shoes",
      slot: 0,
    };
    const results = await Promise.allSettled([
      a.commit({ type: "add", input }, s.version, "a"),
      b.commit({ type: "add", input: { ...input, slot: 1 } }, s.version, "b"),
    ]);
    const current = await a.read();
    const fallback = await a.commit(
      { type: "add", input: { ...input, group: "unplaced" } },
      current.version,
      "overflow",
    );
    return {
      statuses: results.map((r) => r.status),
      count: current.items.length,
      start: s.items.length,
      last: fallback.snapshot.items.at(-1),
    };
  });
  expect(result.statuses.sort()).toEqual(["fulfilled", "rejected"]);
  expect(result.count).toBe(result.start + 1);
  expect(result.last.placement.semanticGroup).toBe("unplaced");
});
