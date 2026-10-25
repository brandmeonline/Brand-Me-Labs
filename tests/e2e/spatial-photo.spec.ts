import {
  test,
  expect,
} from "../../scripts/assets/node_modules/@playwright/test";
import { createPhotoService } from "../../brandme-frontend/features/spatial/server/photoService";
import { readFile, mkdtemp, rm } from "node:fs/promises";
import path from "node:path";
import os from "node:os";
const publicDir = path.resolve("brandme-frontend/public");
async function setup(limit = 10) {
  const stateDir = await mkdtemp(path.join(os.tmpdir(), "brandme-photo-"));
  const bytes = await readFile(
    path.join(publicDir, "demo/test-person/synthetic-adult.png"),
  );
  let calls = 0;
  let release: () => void = () => {};
  const gate = new Promise<void>((r) => {
    release = r;
  });
  const config = {
    enabled: true,
    project: "brandme-test-dev",
    region: "us-central1",
    token: "conformance-test-token-not-a-credential",
    retention: "Conformance test only; no external provider call.",
    publicDir,
    stateDir,
    limit,
  };
  const provider: typeof fetch = async (input, init) => {
    calls++;
    expect(String(input)).toContain("virtual-try-on-001:predict");
    const body = JSON.parse(init!.body as string);
    expect(body.parameters.sampleCount).toBe(1);
    expect(body.instances[0].productImages).toHaveLength(1);
    await gate;
    return new Response(
      JSON.stringify({
        predictions: [
          {
            mimeType: "image/png",
            bytesBase64Encoded: bytes.toString("base64"),
          },
        ],
      }),
    );
  };
  const service = createPhotoService(config, provider);
  const initial = await service.handle(
    new Request("http://127.0.0.1:4178/try/photo/api"),
  );
  const cookie = initial.headers.get("set-cookie")!.split(";")[0];
  const payload = {
    operationId: "test-operation-1",
    consent: true,
    testOnly: true,
    productSlug: "overshirt",
    personBase64: bytes.toString("base64"),
  };
  const request = (
    method: string,
    suffix = "",
    body?: unknown,
    otherCookie = cookie,
    origin = "http://127.0.0.1:4178",
  ) =>
    new Request("http://127.0.0.1:4178/try/photo/api" + suffix, {
      method,
      headers: {
        cookie: otherCookie,
        origin,
        "Content-Type": "application/json",
      },
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
  return {
    service,
    restart: () => createPhotoService(config, provider),
    bytes,
    cookie,
    payload,
    request,
    release,
    calls: () => calls,
    cleanup: () => rm(stateDir, { recursive: true, force: true }),
  };
}
test("photo service enforces origin, consent, test-only image and ownership before external requests", async () => {
  const s = await setup();
  try {
    expect(
      (
        await s.service.handle(
          s.request(
            "POST",
            "",
            s.payload,
            s.cookie,
            "https://elsewhere.invalid",
          ),
        )
      ).status,
    ).toBe(403);
    expect(
      (
        await s.service.handle(
          s.request("POST", "", { ...s.payload, consent: false }),
        )
      ).status,
    ).toBe(400);
    expect(
      (
        await s.service.handle(
          s.request("POST", "", {
            ...s.payload,
            personBase64: Buffer.from("not the approved photo").toString(
              "base64",
            ),
          }),
        )
      ).status,
    ).toBe(400);
    expect(s.calls()).toBe(0);
    const created = await (
      await s.service.handle(s.request("POST", "", s.payload))
    ).json();
    expect(created.state).toBe("running");
    expect(
      (
        await s.service.handle(
          s.request("GET", `?id=${created.id}`, undefined, "wrong=session"),
        )
      ).status,
    ).toBe(401);
    const cancelled = await (
      await s.service.handle(s.request("DELETE", `?id=${created.id}`))
    ).json();
    expect(cancelled.providerDeletion).toBe(false);
    s.release();
    await expect.poll(s.calls).toBe(1);
    const read = await (
      await s.service.handle(s.request("GET", `?id=${created.id}`))
    ).json();
    expect(read.state).toBe("cancelled");
    expect(read.image).toBeUndefined();
  } finally {
    s.release();
    await s.cleanup();
  }
});
test("photo service keeps retry idempotency, changed-input rejection and durable attempt cap", async () => {
  const s = await setup(1);
  try {
    const normalized = s.request("POST", "", s.payload);
    normalized.headers.set("host", "127.0.0.1:4178");
    const first = await (
      await s.service.handle(new Request("http://localhost:4178/try/photo/api", normalized))
    ).json();
    expect(first.state).toBe("running");
    const externalHost = s.request("POST", "", s.payload);
    externalHost.headers.set("host", "public.example");
    expect((await s.service.handle(externalHost)).status).toBe(403);
    const replay = await (
      await s.service.handle(s.request("POST", "", s.payload))
    ).json();
    expect(replay.id).toBe(first.id);
    expect(
      (
        await s.service.handle(
          s.request("POST", "", { ...s.payload, productSlug: "tee" }),
        )
      ).status,
    ).toBe(409);
    const blocked = await (
      await s.service.handle(
        s.request("POST", "", {
          ...s.payload,
          operationId: "second-operation",
        }),
      )
    ).json();
    expect(blocked.error).toContain("Daily");
    s.release();
    await expect
      .poll(
        async () =>
          (
            await (
              await s.service.handle(s.request("GET", `?id=${first.id}`))
            ).json()
          ).state,
      )
      .toBe("completed");
    expect(s.calls()).toBe(1);
    const restarted = s.restart();
    const reopened = await restarted.handle(
      s.request("GET", "", undefined, ""),
    );
    const freshCookie = reopened.headers.get("set-cookie")!.split(";")[0];
    const retryAfterRestart = await restarted.handle(
      s.request("POST", "", s.payload, freshCookie),
    );
    expect(retryAfterRestart.status).toBe(409);
    expect((await retryAfterRestart.json()).error).toContain(
      "unknown after restart",
    );
    const newAfterRestart = await restarted.handle(
      s.request(
        "POST",
        "",
        {
          ...s.payload,
          operationId: "new-after-restart",
        },
        freshCookie,
      ),
    );
    expect((await newAfterRestart.json()).error).toContain("Daily");
    expect(s.calls()).toBe(1);
  } finally {
    s.release();
    await s.cleanup();
  }
});
test("photo controls drive upload, processing, durable closet reference and deletion through the real dev service with a provider double", async ({
  page,
}) => {
  const s = await setup();
  try {
    await page.route("**/try/photo/api*", async (route) => {
      const req = route.request();
      const headers = await req.allHeaders();
      const response = await s.service.handle(
        new Request(req.url(), {
          method: req.method(),
          headers,
          ...(req.postData() ? { body: req.postData()! } : {}),
        }),
      );
      await route.fulfill({
        status: response.status,
        headers: Object.fromEntries(response.headers),
        body: await response.text(),
      });
    });
    await page.goto("/try/overshirt");
    await page.getByRole("button", { name: /Photo try-on/ }).click();
    await page
      .getByLabel("Review a test photo")
      .setInputFiles(
        path.join(publicDir, "demo/test-person/synthetic-adult.png"),
      );
    await expect(
      page.getByRole("button", { name: "Send test photo" }),
    ).toBeDisabled();
    await page.getByRole("checkbox").check();
    await page.getByRole("button", { name: "Send test photo" }).click();
    await expect(page.getByText("Preview status: running")).toBeVisible();
    s.release();
    await expect(
      page.getByRole("img", {
        name: "Generated visual preview, not a fit estimate",
      }),
    ).toBeVisible();
    await expect(
      page.getByRole("img", {
        name: "Original synthetic test input",
        exact: true,
      }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "Save preview", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: "Saved on this browser" }),
    ).toBeDisabled();
    await page
      .getByRole("button", { name: "Add photo reference to closet" })
      .click();
    await expect(
      page
        .getByRole("status")
        .filter({ hasText: "Added as a photo reference" }),
    ).toBeVisible();
    const saved = await page.evaluate(async () => {
      // @ts-ignore Vite browser module
      const { createGuestClosetRepository } = await import(
        "/brandme-frontend/features/closet/repository.ts"
      );
      return (await createGuestClosetRepository().read()).items.find(
        (i: any) => i.title === "Preview · Field Linen Overshirt",
      );
    });
    expect(saved.fidelity).toBe("P0");
    expect(saved.assetSlug).toBe(null);
    expect(saved.status).toBe("want");
    await page
      .getByRole("button", { name: "Delete preview", exact: true })
      .click();
    await expect(
      page.getByRole("img", {
        name: "Generated visual preview, not a fit estimate",
      }),
    ).toHaveCount(0);
    const remaining = await page.evaluate(async () => {
      // @ts-ignore Vite browser module
      const { createGuestClosetRepository } = await import(
        "/brandme-frontend/features/closet/repository.ts"
      );
      // @ts-ignore Vite browser module
      const { readPreviews } = await import(
        "/brandme-frontend/features/spatial/previewMedia.ts"
      );
      return {
        items: (await createGuestClosetRepository().read()).items.filter(
          (i: any) => i.previewMediaId,
        ),
        media: await readPreviews(),
      };
    });
    expect(remaining.items).toEqual([]);
    expect(remaining.media).toEqual([]);
    expect(s.calls()).toBe(1);
  } finally {
    s.release();
    await s.cleanup();
  }
});

test("a lost photo job stops polling and can be discarded without creating a new provider attempt", async ({
  page,
}) => {
  let posts = 0;
  await page.route("**/try/photo/api*", async (route) => {
    const request = route.request();
    if (request.method() === "POST") {
      posts++;
      return route.fulfill({ json: { id: "expired-job", state: "running" } });
    }
    if (request.url().includes("?id="))
      return route.fulfill({
        status: 401,
        json: { error: "Session expired." },
      });
    return route.fulfill({
      json: {
        enabled: true,
        provider: "Test double",
        model: "test",
        region: "local",
        retention: "No external provider call.",
      },
    });
  });
  await page.goto("/try/overshirt");
  await page.getByRole("button", { name: /Photo try-on/ }).click();
  await page
    .getByLabel("Review a test photo")
    .setInputFiles(
      path.join(publicDir, "demo/test-person/synthetic-adult.png"),
    );
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Send test photo" }).click();
  await expect(page.getByText("Preview status: unknown")).toBeVisible();
  await page
    .getByRole("button", { name: "Delete preview", exact: true })
    .click();
  await expect(page.getByLabel("Review a test photo")).toBeEnabled();
  expect(posts).toBe(1);
});
