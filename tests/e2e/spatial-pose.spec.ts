import {
  test,
  expect,
} from "../../scripts/assets/node_modules/@playwright/test";
import fs from "node:fs/promises";

test("real pinned local model detects synthetic fixture and rejects an empty frame", async ({
  page,
}, testInfo) => {
  test.setTimeout(90000);
  const outgoing: string[] = [];
  page.on("request", (r) => {
    if (r.method() === "POST" || !r.url().startsWith("http://127.0.0.1:4178"))
      outgoing.push(r.url());
  });
  await page.goto("/try/overshirt");
  const evidence = await page.evaluate(async () => {
    const worker = new Worker("/demo/vision/pose-worker.js");
    const message = () =>
      new Promise<any>((resolve, reject) => {
        const timer = setTimeout(
          () => reject(Error("Worker timed out")),
          30000,
        );
        worker.onmessage = (e) => {
          clearTimeout(timer);
          e.data.type === "error"
            ? reject(Error(e.data.message))
            : resolve(e.data);
        };
        worker.onerror = (e) => {
          clearTimeout(timer);
          reject(Error(e.message));
        };
      });
    try {
      let wait = message();
      worker.postMessage({
        type: "init",
        modelUrl: "/demo/vision/pose-lite-v1.task",
        wasmRoot: "/demo/vision/0.10.35/wasm",
      });
      await wait;
      const blob = await (
        await fetch("/demo/test-person/synthetic-adult.png")
      ).blob();
      const samples = [];
      let points;
      for (let i = 0; i < 12; i++) {
        const bitmap = await createImageBitmap(blob);
        wait = message();
        worker.postMessage(
          { type: "frame", bitmap, timestamp: 1000 + i * 100 },
          [bitmap],
        );
        const m = await wait;
        samples.push(m.latencyMs);
        points = m.landmarks;
      }
      const empty = new OffscreenCanvas(640, 480);
      empty.getContext("2d")!.fillRect(0, 0, 640, 480);
      const bitmap = empty.transferToImageBitmap();
      wait = message();
      worker.postMessage({ type: "frame", bitmap, timestamp: 3000 }, [bitmap]);
      const blank = await wait;
      return {
        runtime: "0.10.35",
        model: "pose-lite-float16-v1",
        samples,
        landmarks: points,
        blankCount: blank.count,
      };
    } finally {
      worker.terminate();
    }
  });
  expect(evidence.landmarks).toHaveLength(33);
  expect(evidence.blankCount).toBe(0);
  expect(outgoing).toEqual([]);
  for (const index of [11, 12, 23, 24])
    expect(evidence.landmarks[index].visibility).toBeGreaterThan(0.65);
  const annotation = JSON.parse(
    await fs.readFile(
      "brandme-frontend/public/demo/test-person/annotations.json",
      "utf8",
    ),
  );
  const errors = Object.entries(annotation.points).map(([id, xy]) => {
    const [x, y] = xy as number[];
    const p = evidence.landmarks[Number(id)];
    return Math.hypot(
      (p.x - x) * annotation.width,
      (p.y - y) * annotation.height,
    );
  });
  const tolerancePixels = 0.15 * 0.28 * annotation.height;
  const accuracy = {
    method: annotation.method,
    annotationUncertaintyPixels: annotation.annotationUncertaintyPixels,
    meanPixelError: errors.reduce((a, b) => a + b, 0) / errors.length,
    pckAt015Torso:
      errors.filter((e) => e <= tolerancePixels).length / errors.length,
    tolerancePixels,
  };
  expect(accuracy.pckAt015Torso).toBeGreaterThanOrEqual(0.75);
  const sorted = evidence.samples.slice(1).sort((a, b) => a - b);
  await fs.writeFile(
    testInfo.outputPath("pose-inference.json"),
    JSON.stringify(
      {
        ...evidence,
        accuracy,
        measuredAt: new Date().toISOString(),
        medianMs: sorted[Math.floor(sorted.length / 2)],
        p95Ms: sorted[Math.ceil(sorted.length * 0.95) - 1],
        limits:
          "One synthetic fixture, Chromium CPU, no physical camera or population accuracy/fit validation.",
      },
      null,
      2,
    ) + "\n",
  );
});

test("actual try-on camera flow uses real local worker and stops on mode exit", async ({
  page,
}, testInfo) => {
  test.setTimeout(90000);
  await page.goto("/try/overshirt");
  await page.evaluate(async () => {
    const image = new Image();
    image.src = "/demo/test-person/synthetic-adult.png";
    await image.decode();
    const canvas = document.createElement("canvas");
    canvas.width = 640;
    canvas.height = 960;
    canvas.getContext("2d")!.drawImage(image, 0, 0, 640, 960);
    const stream = canvas.captureStream(20);
    const timer = setInterval(
      () => canvas.getContext("2d")!.drawImage(image, 0, 0, 640, 960),
      50,
    );
    (window as any).__poseStream = stream;
    (window as any).__poseTimer = timer;
    Object.defineProperty(navigator.mediaDevices, "getUserMedia", {
      value: async () => stream,
      configurable: true,
    });
  });
  await page.getByRole("button", { name: /Live visual overlay/ }).click();
  await expect(
    page.getByRole("button", { name: "Start local camera" }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Start local camera" }).click();
  await expect(
    page.getByRole("img", { name: "Approximate visual overlay", exact: true }),
  ).toBeVisible({ timeout: 30000 });
  await page
    .getByRole("heading", { name: "Field Linen Overshirt" })
    .scrollIntoViewIfNeeded();
  await page.screenshot({
    path: testInfo.outputPath("pose-preview.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: /Item image/ }).click();
  expect(
    await page.evaluate(() => {
      clearInterval((window as any).__poseTimer);
      return (window as any).__poseStream.getVideoTracks()[0].readyState;
    }),
  ).toBe("ended");
});
