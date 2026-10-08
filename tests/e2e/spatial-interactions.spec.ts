import {
  test,
  expect,
} from "../../scripts/assets/node_modules/@playwright/test";

async function ready(
  page: import("../../scripts/assets/node_modules/@playwright/test").Page,
) {
  await expect(page.locator("[data-room-ready]")).toHaveAttribute(
    "data-room-ready",
    "true",
  );
  await expect(page.locator("[data-camera-position]")).toBeVisible();
}

test("slow add prefetches its asset, shows an uncommitted destination, then settles only after commit", async ({
  page,
}) => {
  await page.goto("/add?save-delay=1400");
  const prefetch = page.waitForRequest((r) =>
    r.url().endsWith("/garments/knit/lod1.glb"),
  );
  await page.getByRole("button", { name: /Ribbed Oat Knit/ }).click();
  await prefetch;
  await page
    .getByRole("button", { name: "Add to closet", exact: true })
    .click();
  await expect(page.getByTestId("pending-placement")).toContainText("Saving");
  await expect(page.getByTestId("placement-flight")).toHaveCount(0);
  await expect(
    page.getByRole("combobox", { name: "Destination", exact: true }),
  ).toBeDisabled();
  expect(
    await page.evaluate(async () => {
      const { createGuestClosetRepository } = await import(
        "/brandme-frontend/features/closet/repository.ts"
      );
      return (await createGuestClosetRepository().read()).items.length;
    }),
  ).toBe(7);
  await expect(page.getByRole("status")).toContainText("Added to your");
  await expect(page.getByTestId("pending-placement")).toHaveCount(0);
  expect(
    await page.evaluate(async () => {
      const { createGuestClosetRepository } = await import(
        "/brandme-frontend/features/closet/repository.ts"
      );
      return (await createGuestClosetRepository().read()).items.length;
    }),
  ).toBe(8);
  await page.getByRole("button", { name: "Undo", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Addition undone");
});

test("reduced motion retains usable named camera views and remembers the chosen view", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/closet");
  await ready(page);
  const initial = await page
    .locator("[data-camera-position]")
    .getAttribute("data-camera-position");
  const work = page.getByRole("button", { name: "Work rail", exact: true });
  await expect(work).toBeEnabled();
  await work.click();
  await expect(work).toHaveAttribute("aria-pressed", "true");
  await expect
    .poll(() =>
      page
        .locator("[data-camera-position]")
        .getAttribute("data-camera-position"),
    )
    .not.toBe(initial);
  const chosen = await page
    .locator("[data-camera-position]")
    .getAttribute("data-camera-position");
  await page.reload();
  await ready(page);
  await expect(work).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator("[data-camera-position]")).toHaveAttribute(
    "data-camera-position",
    chosen!,
  );
});

test("saved camera views restore exact poses, remain room-local and can be deleted", async ({
  page,
}) => {
  await page.goto("/closet");
  await ready(page);
  const original = await page
    .locator("[data-camera-position]")
    .getAttribute("data-camera-position");
  await page.getByText("My saved camera views", { exact: true }).click();
  await page.getByLabel("View name", { exact: true }).fill("Morning rail");
  await page
    .getByRole("button", { name: "Save camera view", exact: true })
    .click();
  await page.getByRole("button", { name: "Work rail", exact: true }).click();
  await expect
    .poll(() =>
      page
        .locator("[data-camera-position]")
        .getAttribute("data-camera-position"),
    )
    .not.toBe(original);
  await page.getByRole("button", { name: "Morning rail", exact: true }).click();
  await expect(page.locator("[data-camera-position]")).toHaveAttribute(
    "data-camera-position",
    original!,
  );
  await page.reload();
  await ready(page);
  await page.getByText("My saved camera views", { exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Morning rail", exact: true }),
  ).toBeVisible();
  await page.getByLabel("Room environment").selectOption("garden_studio");
  await ready(page);
  await expect(
    page.getByRole("button", { name: "Morning rail", exact: true }),
  ).toHaveCount(0);
  await page.getByLabel("Room environment").selectOption("walnut_atelier");
  await ready(page);
  await page
    .getByRole("button", {
      name: "Delete camera view Morning rail",
      exact: true,
    })
    .click();
  await expect(
    page.getByRole("button", { name: "Morning rail", exact: true }),
  ).toHaveCount(0);
});

test("orbit position persists after idle and is restored after reload", async ({
  page,
}) => {
  await page.goto("/closet");
  await ready(page);
  const canvas = await page.locator("canvas").boundingBox();
  expect(canvas).not.toBeNull();
  await page.mouse.move(canvas!.x + canvas!.width * 0.45, canvas!.y + 80);
  await page.mouse.down();
  await page.mouse.move(canvas!.x + canvas!.width * 0.6, canvas!.y + 80, {
    steps: 12,
  });
  await page.mouse.up();
  await expect
    .poll(() =>
      page.evaluate(() =>
        localStorage.getItem("brandme.spatial.camera.v1:walnut_atelier"),
      ),
    )
    .not.toBeNull();
  const saved = await page.evaluate(
    () =>
      JSON.parse(
        localStorage.getItem("brandme.spatial.camera.v1:walnut_atelier")!,
      ).last.position,
  );
  expect(saved[0]).not.toBe(0);
  await page.reload();
  await ready(page);
  const actual = (await page
    .locator("[data-camera-position]")
    .getAttribute("data-camera-position"))!
    .split(",")
    .map(Number);
  saved.forEach((n: number, i: number) => expect(actual[i]).toBeCloseTo(n, 5));
});

test("theme change fades the old room before replacement and reduced motion swaps immediately", async ({
  page,
}) => {
  await page.goto("/closet");
  await ready(page);
  const room = page.locator("[data-room-phase]");
  await room.evaluate((node) => {
    (window as any).roomTransitions = [];
    new MutationObserver(() =>
      (window as any).roomTransitions.push({
        phase: node.getAttribute("data-room-phase"),
        room: node.getAttribute("data-displayed-room"),
        at: performance.now(),
      }),
    ).observe(node, {
      attributes: true,
      attributeFilter: ["data-room-phase", "data-displayed-room"],
    });
  });
  await page.getByLabel("Room environment").selectOption("garden_studio");
  await expect(room).toHaveAttribute("data-displayed-room", "garden_studio");
  await expect(room).toHaveAttribute("data-room-phase", "steady");
  await ready(page);
  const history = await page.evaluate(() => (window as any).roomTransitions);
  expect(
    history.some((x: any) => x.phase === "out" && x.room === "walnut_atelier"),
  ).toBe(true);
  expect(
    history.some((x: any) => x.phase === "in" && x.room === "garden_studio"),
  ).toBe(true);
  const out = history.find((x: any) => x.phase === "out");
  const finished = history.find((x: any) => x.phase === "steady");
  expect(finished.at - out.at).toBeGreaterThanOrEqual(400);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.getByLabel("Room environment").selectOption("limestone_gallery");
  await expect(room).toHaveAttribute(
    "data-displayed-room",
    "limestone_gallery",
  );
  await expect(room).toHaveAttribute("data-room-phase", "steady");
});

test("dragging a wardrobe image onto a semantic destination commits one move and survives reload", async ({
  page,
}) => {
  await page.goto("/closet");
  await page
    .getByRole("button", { name: "Select Field Linen Overshirt", exact: true })
    .click();
  await page.getByRole("button", { name: "Move item", exact: true }).click();
  const row = page
    .getByRole("listitem")
    .filter({
      has: page.getByRole("button", {
        name: "Select Field Linen Overshirt",
        exact: true,
      }),
    });
  const target = page.locator(
    '[data-drop-group="rail.right"][data-drop-slot="0"]',
  );
  await row.locator("img").dragTo(target);
  await expect(page.getByRole("status")).toContainText(
    "Moved Field Linen Overshirt to Occasion rail, slot 1",
  );
  await page.reload();
  await page
    .getByRole("button", { name: "Select Field Linen Overshirt", exact: true })
    .click();
  await expect(page.getByRole("complementary")).toContainText(
    "Occasion rail · Slot 1",
  );
});

test("touch long press enters placement while early movement remains scrolling", async ({
  page,
}) => {
  await page.goto("/closet");
  const row = page.getByRole("listitem").first();
  await row.dispatchEvent("pointerdown", {
    pointerType: "touch",
    clientX: 20,
    clientY: 20,
  });
  await row.dispatchEvent("pointermove", {
    pointerType: "touch",
    clientX: 20,
    clientY: 55,
  });
  await page.waitForTimeout(400);
  await expect(page.getByLabel("Placement destination")).toHaveCount(0);
  await row.dispatchEvent("pointerup", { pointerType: "touch" });
  await row.dispatchEvent("pointerdown", {
    pointerType: "touch",
    clientX: 20,
    clientY: 20,
  });
  await page.waitForTimeout(400);
  await expect(page.getByLabel("Placement destination")).toBeVisible();
  await row.dispatchEvent("pointerup", { pointerType: "touch" });
  await page.getByLabel("Placement destination").press("Escape");
  await expect(page.getByLabel("Placement destination")).toHaveCount(0);
});

test("search keeps room context dimmed while the accessible list shows matches", async ({
  page,
}) => {
  await page.goto("/closet");
  await ready(page);
  await expect(page.locator("[data-scene-count]")).toHaveAttribute(
    "data-scene-count",
    "7",
  );
  await page
    .getByRole("searchbox", { name: "Search your closet" })
    .fill("Linen");
  await expect(page.getByRole("listitem")).toHaveCount(1);
  await expect(page.locator("[data-scene-count]")).toHaveAttribute(
    "data-scene-count",
    "7",
  );
  await expect(page.locator("[data-scene-dimmed]")).toHaveAttribute(
    "data-scene-dimmed",
    "6",
  );
  await page.getByRole("searchbox").fill("");
  await expect(page.locator("[data-scene-dimmed]")).toHaveAttribute(
    "data-scene-dimmed",
    "0",
  );
});

test("an image-only item remains a labeled photo display in the rendered room", async ({
  page,
}) => {
  await page.goto("/add");
  await page.getByRole("button", { name: /My reference overshirt/ }).click();
  await page
    .getByRole("button", { name: "Add to closet", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText("Added to your");
  await page.getByRole("link", { name: "Back to closet" }).click();
  await ready(page);
  await expect(page.locator("[data-scene-count]")).toHaveAttribute(
    "data-scene-count",
    "8",
  );
  await page.getByRole("searchbox").fill("My reference");
  await expect(page.getByRole("listitem")).toContainText("Photo display");
  await page
    .getByRole("button", { name: "Select My reference overshirt", exact: true })
    .click();
  await expect(page.getByRole("complementary")).toContainText("Photo display");
});

test("multi-selection across search filters creates a persisted capsule without changing item status", async ({
  page,
}) => {
  await page.goto("/closet");
  await page.getByRole("searchbox").fill("Linen");
  await page
    .getByRole("checkbox", {
      name: "Include Field Linen Overshirt in capsule",
      exact: true,
    })
    .check();
  await page.getByRole("searchbox").fill("Trousers");
  await page
    .getByRole("checkbox", {
      name: "Include Soft Pleat Trousers in capsule",
      exact: true,
    })
    .check();
  await expect(page.getByLabel("Selected pieces tray")).toContainText(
    "2 selected",
  );
  await page.getByLabel("Capsule name", { exact: true }).fill("Workweek");
  await page.getByRole("button", { name: "Save capsule", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Capsule saved");
  await page.getByRole("searchbox").fill("");
  await expect(page.getByRole("listitem")).toHaveCount(2);
  const before = await page.evaluate(async () => {
    const { createGuestClosetRepository } = await import(
      "/brandme-frontend/features/closet/repository.ts"
    );
    const s = await createGuestClosetRepository().read();
    return {
      capsules: s.capsules,
      statuses: s.items.map((i: any) => [i.id, i.status]),
    };
  });
  expect(before.capsules[0].itemIds).toEqual([
    "guest-overshirt",
    "guest-trousers",
  ]);
  await page.reload();
  await page
    .getByRole("combobox", { name: "Capsule", exact: true })
    .selectOption({ label: "Workweek" });
  await expect(page.getByRole("listitem")).toHaveCount(2);
  await page
    .getByRole("button", { name: "Remove capsule", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText("Its items remain");
  const after = await page.evaluate(async () => {
    const { createGuestClosetRepository } = await import(
      "/brandme-frontend/features/closet/repository.ts"
    );
    const s = await createGuestClosetRepository().read();
    return {
      capsules: s.capsules,
      statuses: s.items.map((i: any) => [i.id, i.status]),
    };
  });
  expect(after.capsules).toEqual([]);
  expect(after.statuses).toEqual(before.statuses);
});

test("reversing a room change during fade cannot leave the canvas hidden", async ({
  page,
}) => {
  await page.goto("/closet");
  await ready(page);
  await page
    .getByLabel("Room environment")
    .evaluate((select: HTMLSelectElement) => {
      select.value = "garden_studio";
      select.dispatchEvent(new Event("change", { bubbles: true }));
      setTimeout(() => {
        select.value = "walnut_atelier";
        select.dispatchEvent(new Event("change", { bubbles: true }));
      }, 100);
    });
  await expect(
    page.getByRole("heading", { name: "Walnut Atelier", exact: true }),
  ).toBeVisible();
  await page.waitForTimeout(650);
  await expect(page.locator("[data-room-phase]")).toHaveAttribute(
    "data-room-phase",
    "steady",
  );
  await expect(page.locator("[data-room-phase]")).toHaveAttribute(
    "data-displayed-room",
    "walnut_atelier",
  );
  await ready(page);
});
