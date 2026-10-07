import {
  test,
  expect,
} from "../../scripts/assets/node_modules/@playwright/test";

test("original rooms render from the real cameras and retain usable controls", async ({
  page,
}, info) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/closet");
  await expect(
    page.getByRole("heading", { name: "Walnut Atelier" }),
  ).toBeVisible();
  for (const [id, title] of [
    ["walnut_atelier", "Walnut Atelier"],
    ["limestone_gallery", "Limestone Gallery"],
    ["garden_studio", "Garden Studio"],
  ]) {
    await page.getByLabel("Room environment").selectOption(id);
    await expect(page.getByRole("heading", { name: title })).toBeVisible();
    await expect(page.locator("canvas")).toBeVisible();
    await page.waitForTimeout(600);
    await page.screenshot({
      path: info.outputPath(`${id}-1440.png`),
      fullPage: true,
    });
  }
  expect(errors).toEqual([]);
  expect(await page.locator("vite-error-overlay").count()).toBe(0);
});

test("keyboard placement survives refresh and semantic theme remapping", async ({
  page,
}) => {
  await page.goto("/closet");
  await page
    .getByRole("button", { name: "Select Field Linen Overshirt", exact: true })
    .click();
  await page.getByRole("button", { name: "Move item", exact: true }).click();
  await page.getByLabel("Placement destination").selectOption("rail.right");
  await page.getByLabel("Placement slot").selectOption({ value: "1" });
  await page.getByLabel("Placement slot").press("Enter");
  await expect(page.getByRole("status")).toContainText(
    "Moved Field Linen Overshirt",
  );
  await page.reload();
  await page
    .getByRole("button", { name: "Select Field Linen Overshirt", exact: true })
    .click();
  await expect(page.getByRole("complementary")).toContainText(
    "Occasion rail · Slot 2",
  );
  await page.getByLabel("Room environment").selectOption("garden_studio");
  await expect(page.getByRole("complementary")).toContainText("Unplaced tray");
  await page.reload();
  await page
    .getByRole("button", { name: "Select Field Linen Overshirt", exact: true })
    .click();
  await expect(page.getByRole("complementary")).toContainText("Unplaced tray");
});

test("add animation starts only after the item commit and Undo removes its record", async ({
  page,
}) => {
  await page.goto("/add");
  await page.getByRole("button", { name: /Ribbed Oat Knit/ }).click();
  await page
    .getByRole("combobox", { name: "Closet status", exact: true })
    .selectOption("owned");
  await page
    .getByRole("button", { name: "Add to closet", exact: true })
    .click();
  const flight = page.getByTestId("placement-flight");
  await expect(flight).toBeVisible();
  const itemId = await flight.getAttribute("data-committed-item");
  const exists = await page.evaluate(async (id) => {
    const { createGuestClosetRepository } = await import(
      "/brandme-frontend/features/closet/repository.ts"
    );
    return (await createGuestClosetRepository().read()).items.some(
      (i: { id: string }) => i.id === id,
    );
  }, itemId);
  expect(exists).toBe(true);
  await page.getByRole("button", { name: "Undo", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Addition undone");
  const count = await page.evaluate(async () => {
    const { createGuestClosetRepository } = await import(
      "/brandme-frontend/features/closet/repository.ts"
    );
    return (await createGuestClosetRepository().read()).items.length;
  });
  expect(count).toBe(7);
});

test("reduced motion commits immediately without the flight and persists", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/add");
  await page.getByRole("button", { name: /Ribbed Oat Knit/ }).click();
  await page
    .getByRole("button", { name: "Add to closet", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText("Added to your");
  await expect(page.getByTestId("placement-flight")).toHaveCount(0);
  await page.goto("/closet");
  await expect(page.getByRole("list")).toContainText("Ribbed Oat Knit");
});

test("idempotent retries, key binding and concurrent versions reject duplicate writes", async ({
  page,
}) => {
  await page.goto("/closet");
  await expect(page.getByRole("list")).toBeVisible();
  const result = await page.evaluate(async () => {
    const { createGuestClosetRepository } = await import(
      "/brandme-frontend/features/closet/repository.ts"
    );
    const repo = createGuestClosetRepository("spatial-test-transactions"),
      base = await repo.read();
    const command = {
      type: "add",
      input: {
        productId: null,
        title: "Transaction specimen",
        category: "top",
        status: "want",
        posterUrl: "/demo/photo-only/poster.webp",
        assetSlug: null,
        group: "unplaced",
        slot: 0,
      },
    };
    const first = await repo.commit(command, base.version, "idempotent-1"),
      retry = await repo.commit(command, base.version, "idempotent-1");
    let changedKey = false;
    try {
      await repo.commit(
        { ...command, input: { ...command.input, title: "Changed" } },
        first.snapshot.version,
        "idempotent-1",
      );
    } catch {
      changedKey = true;
    }
    const parallel = await Promise.allSettled([
      repo.commit(
        { type: "preferences", simpleView: true },
        first.snapshot.version,
        "parallel-1",
      ),
      repo.commit(
        { type: "preferences", reducedMotion: true },
        first.snapshot.version,
        "parallel-2",
      ),
    ]);
    return {
      same: first.itemId === retry.itemId,
      count: retry.snapshot.items.length,
      changedKey,
      fulfilled: parallel.filter((x) => x.status === "fulfilled").length,
    };
  });
  expect(result).toEqual({
    same: true,
    count: 8,
    changedKey: true,
    fulfilled: 1,
  });
});

test("500 items remain virtualized, searchable and keyboard reachable", async ({
  page,
}) => {
  await page.goto("/closet");
  await expect(page.getByRole("list")).toBeVisible();
  await page.evaluate(async () => {
    const request = indexedDB.open("brandme.spatial.guest.v1", 1);
    await new Promise<void>((resolve, reject) => {
      request.onsuccess = () => {
        const database = request.result,
          tx = database.transaction("closet", "readwrite"),
          store = tx.objectStore("closet"),
          get = store.get("state");
        get.onsuccess = () => {
          const state = get.result,
            original = state.snapshot.items[0];
          state.snapshot.items = Array.from({ length: 500 }, (_, i) => ({
            ...original,
            id: `large-${i}`,
            title: `Piece ${i + 1}`,
            placement: {
              ...original.placement,
              wardrobeItemId: `large-${i}`,
              semanticGroup: i < 12 ? "rail.left" : "unplaced",
              slotId: i % 12,
            },
          }));
          state.snapshot.version++;
          store.put(state, "state");
        };
        tx.oncomplete = () => {
          database.close();
          resolve();
        };
        tx.onerror = () => reject(tx.error);
      };
    });
  });
  await page.reload();
  await expect(page.getByText(/500 items ·/)).toBeVisible();
  expect(await page.getByRole("listitem").count()).toBeLessThanOrEqual(11);
  await expect(page.locator("[data-scene-count]")).toHaveAttribute(
    "data-scene-count",
    "12",
  );
  await page
    .getByRole("button", { name: "Select Piece 1", exact: true })
    .focus();
  await page.keyboard.press("End");
  await expect(
    page.getByRole("button", { name: "Select Piece 500", exact: true }),
  ).toBeFocused();
  await page.getByLabel("Search your closet").fill("Piece 499");
  await expect(page.getByRole("listitem")).toHaveCount(1);
  await page
    .getByRole("button", { name: "Select Piece 499", exact: true })
    .click();
  await expect(page.getByRole("complementary")).toContainText("Piece 499");
});

test("no WebGL still provides full item organization", async ({ page }) => {
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (
      kind: string,
      ...args: unknown[]
    ) {
      if (kind === "webgl" || kind === "webgl2") return null;
      return original.call(this, kind, ...args);
    };
  });
  await page.goto("/closet");
  await expect(page.getByText(/3D graphics are unavailable/)).toBeVisible();
  await page
    .getByRole("button", { name: "Select Field Linen Overshirt", exact: true })
    .click();
  await page.getByRole("button", { name: "Move item", exact: true }).click();
  await page.getByLabel("Placement slot").selectOption({ value: "0" });
  await page.getByRole("button", { name: "Save placement" }).click();
  await expect(page.getByRole("status")).toContainText("slot 1");
});

test("WebGL context loss exposes Simple View without losing items", async ({
  page,
}) => {
  await page.goto("/closet");
  await expect(page.locator("canvas")).toBeVisible();
  await page
    .locator("canvas")
    .evaluate((canvas) =>
      canvas.dispatchEvent(new Event("webglcontextlost", { cancelable: true })),
    );
  await expect(page.getByText(/Graphics were interrupted/)).toBeVisible();
  await expect(
    page.getByRole("button", {
      name: "Select Field Linen Overshirt",
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.locator("canvas")).toHaveCount(0);
});

test("preview ladder gates camera, provider uploads and calibrated fit", async ({
  page,
}) => {
  const uploads: string[] = [];
  page.on("request", (request) => {
    if (["POST", "PUT"].includes(request.method())) uploads.push(request.url());
  });
  await page.goto("/try/guest-overshirt");
  await expect(
    page.getByRole("button", { name: /Calibrated fit/ }),
  ).toBeDisabled();
  await page.getByRole("button", { name: /Live visual overlay/ }).click();
  await expect(
    page.getByRole("button", { name: "Start local camera" }),
  ).toBeDisabled();
  await page.getByRole("button", { name: /Photo try-on/ }).click();
  await expect(
    page.getByRole("button", { name: "Photo preview unavailable" }),
  ).toBeDisabled();
  await expect(page.locator("input[type=file]")).toHaveCount(0);
  expect(uploads).toEqual([]);
  await page.getByRole("button", { name: /3D inspection/ }).click();
  await expect(page.locator("model-viewer")).toBeVisible();
  await expect
    .poll(() => page.locator("model-viewer").evaluate((el: any) => el.loaded))
    .toBe(true);
  await page.getByRole("button", { name: /Room placement/ }).click();
  await expect(
    page.getByRole("button", { name: "Place in my room" }),
  ).toBeDisabled();
  await expect(page.locator("model-viewer")).toHaveAttribute(
    "ios-src",
    "/demo/garments/overshirt/preview.usdz",
  );
});

test("camera cleanup handles exit and a late permission result without uploads", async ({
  page,
}) => {
  await page.goto("/closet");
  const outcome = await page.evaluate(async () => {
    const { CameraSession } = await import(
      "/brandme-frontend/features/spatial/cameraSession.ts"
    );
    const canvas = document.createElement("canvas");
    canvas.width = 64;
    canvas.height = 64;
    const stream = canvas.captureStream(20),
      video = document.createElement("video");
    video.muted = true;
    document.body.append(video);
    let resolvePermission: (s: MediaStream) => void = () => {};
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: {
        getUserMedia: () =>
          new Promise<MediaStream>((resolve) => {
            resolvePermission = resolve;
          }),
      },
    });
    const session = new CameraSession(
      video,
      () => {},
      () => {},
    );
    const starting = session.start({
      modelUrl: "/demo/vision/pose.task",
      wasmRoot: "/demo/vision/wasm",
    });
    session.stop();
    resolvePermission(stream);
    await starting;
    return {
      stopped: stream.getTracks().every((t) => t.readyState === "ended"),
      cleared: video.srcObject === null,
    };
  });
  expect(outcome).toEqual({ stopped: true, cleared: true });
});

test("expired unsaved preview is removed; saved preview deletes completely", async ({
  page,
}) => {
  await page.goto("/closet");
  const result = await page.evaluate(async () => {
    const media = await import(
      "/brandme-frontend/features/spatial/previewMedia.ts"
    );
    const blob = await (await fetch("/demo/photo-only/poster.webp")).blob();
    const id = await media.storePreview(blob, 1000);
    const expired =
      (await media.readPreviews(1000 + 24 * 60 * 60 * 1000 + 1)).length === 0;
    const kept = await media.storePreview(blob, 2000);
    await media.savePreview(kept, 2001);
    const survives =
      (await media.readPreviews(2000 + 48 * 60 * 60 * 1000)).length === 1;
    await media.deletePreview(kept);
    return {
      expired,
      survives,
      deleted: (await media.readPreviews()).length === 0,
    };
  });
  expect(result).toEqual({ expired: true, survives: true, deleted: true });
});

test("active camera and worker stop when the page is backgrounded", async ({
  page,
}) => {
  await page.goto("/closet");
  const result = await page.evaluate(async () => {
    const { CameraSession } = await import(
      "/brandme-frontend/features/spatial/cameraSession.ts"
    );
    const canvas = document.createElement("canvas");
    canvas.width = 64;
    canvas.height = 64;
    const stream = canvas.captureStream(20),
      video = document.createElement("video");
    video.play = async () => {};
    let terminated = 0;
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: async () => stream },
    });
    // Only the lifecycle is under test here; no pose or real-device capability is claimed.
    globalThis.Worker = class {
      onmessage: any;
      onerror: any;
      postMessage(message: any) {
        if (message.type === "init")
          queueMicrotask(() => this.onmessage?.({ data: { type: "ready" } }));
      }
      terminate() {
        terminated++;
      }
    } as any;
    const states: string[] = [];
    const session = new CameraSession(
      video,
      (s) => states.push(s),
      () => {},
    );
    await session.start({
      modelUrl: "/demo/vision/pose.task",
      wasmRoot: "/demo/vision/wasm",
    });
    const active = stream.getTracks().some((t) => t.readyState === "live");
    Object.defineProperty(document, "hidden", {
      configurable: true,
      get: () => true,
    });
    document.dispatchEvent(new Event("visibilitychange"));
    return {
      active,
      stopped: stream.getTracks().every((t) => t.readyState === "ended"),
      terminated,
      cleared: video.srcObject === null,
      last: states.at(-1),
    };
  });
  expect(result).toEqual({
    active: true,
    stopped: true,
    terminated: 1,
    cleared: true,
    last: "stopped",
  });
});

test("failed placement does not animate or create an item, and retry can succeed", async ({
  page,
}) => {
  await page.goto("/add");
  await page.getByRole("button", { name: /Ribbed Oat Knit/ }).click();
  await page
    .getByRole("combobox", { name: "Slot", exact: true })
    .selectOption({ value: "2" });
  await page
    .getByRole("button", { name: "Add to closet", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("occupied");
  await expect(page.getByTestId("placement-flight")).toHaveCount(0);
  const count = await page.evaluate(async () => {
    const { createGuestClosetRepository } = await import(
      "/brandme-frontend/features/closet/repository.ts"
    );
    return (await createGuestClosetRepository().read()).items.length;
  });
  expect(count).toBe(7);
  await page
    .getByRole("combobox", { name: "Slot", exact: true })
    .selectOption({ value: "1" });
  await page
    .getByRole("button", { name: "Add to closet", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText("Added to your");
});

test("outfit editor saves real item references and survives refresh", async ({
  page,
}) => {
  await page.goto("/style");
  await page.getByLabel("Add a piece").selectOption("guest-overshirt");
  await page.getByLabel("Add a piece").selectOption("guest-trousers");
  await page.getByRole("button", { name: "Save look", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Look saved");
  await page.reload();
  await expect(page.getByRole("list", { name: "Layer order" })).toContainText(
    "Field Linen Overshirt",
  );
  await expect(page.getByRole("list", { name: "Layer order" })).toContainText(
    "Soft Pleat Trousers",
  );
});

for (const width of [320, 390, 768])
  test(`spatial UI reflows at ${width}px without document overflow`, async ({
    page,
  }, info) => {
    await page.setViewportSize({ width, height: width === 768 ? 1024 : 844 });
    await page.goto("/closet");
    await expect(
      page.getByRole("heading", { name: "Walnut Atelier" }),
    ).toBeVisible();
    await page
      .getByRole("button", {
        name: "Select Field Linen Overshirt",
        exact: true,
      })
      .click();
    await page.getByRole("button", { name: "Move item", exact: true }).click();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.locator("[data-room-ready]").scrollIntoViewIfNeeded();
    await expect(page.locator("[data-room-ready]")).toHaveAttribute(
      "data-room-ready",
      "true",
    );
    await page.screenshot({
      path: info.outputPath(`closet-${width}.png`),
      fullPage: true,
    });
  });
