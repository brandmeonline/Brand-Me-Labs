import { createServer } from "node:http";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { createHash } from "node:crypto";
import { chromium } from "@playwright/test";
const toolsDir = path.dirname(fileURLToPath(import.meta.url)),
  root = path.resolve(toolsDir, "../.."),
  pub = path.join(root, "brandme-frontend/public");
const catalog = JSON.parse(await readFile(path.join(pub, "demo/catalog.json")));
const mime = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".glb": "model/gltf-binary",
  ".json": "application/json",
  ".webp": "image/webp",
};
const server = createServer(async (req, res) => {
  try {
    const url = new URL(req.url, "http://localhost");
    const base =
      url.pathname === "/" || url.pathname.startsWith("/tools/")
        ? toolsDir
        : pub;
    const name =
      url.pathname === "/"
        ? path.join(toolsDir, "review.html")
        : path.resolve(base, "." + url.pathname.replace(/^\/tools/, ""));
    if (!name.startsWith(base + path.sep)) throw Error("path");
    res.setHeader(
      "Content-Type",
      mime[path.extname(name)] || "application/octet-stream",
    );
    res.end(await readFile(name));
  } catch {
    res.writeHead(404);
    res.end();
  }
});
await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
let browser;
try {
  browser = await chromium.launch({
    headless: true,
    args: [
      "--no-sandbox",
      "--use-gl=angle",
      "--use-angle=swiftshader",
      "--enable-unsafe-swiftshader",
    ],
  });
  const measurements = [];
  for (const entry of [...catalog.products, ...catalog.rooms]) {
    const isRoom = !!entry.camera;
    const page = await browser.newPage({
      viewport: isRoom
        ? { width: 1440, height: 900 }
        : { width: 600, height: 760 },
    });
    page.on("pageerror", (e) => console.error(e.message));
    await page.goto(
      `http://127.0.0.1:${server.address().port}/?asset=${encodeURIComponent(entry.glb)}${isRoom ? "&room=" + entry.id : ""}`,
    );
    await page.waitForFunction(
      () => window.assetReview?.ready,
      {},
      { timeout: 30000 },
    );
    const data = await page.evaluate(() => ({
      webp: window.assetReview.webp(),
      triangles: window.assetReview.triangles,
      calls: window.assetReview.calls,
      textureCount: window.assetReview.textureCount,
    }));
    const bytes = Buffer.from(data.webp.split(",")[1], "base64");
    await writeFile(path.join(pub, entry.poster), bytes);
    entry.files["poster.webp"] = {
      sha256: createHash("sha256").update(bytes).digest("hex"),
      bytes: bytes.length,
    };
    entry.qa.loader = "Chromium / Three GLTFLoader 0.182.0";
    entry.qa.visual = "rendered; human approval not claimed";
    const manifestPath = path.join(
      pub,
      path.dirname(entry.glb),
      "manifest.json",
    );
    await writeFile(manifestPath, JSON.stringify(entry, null, 2) + "\n");
    measurements.push({
      id: entry.id,
      triangles: data.triangles,
      drawCalls: data.calls,
      textures: data.textureCount,
      viewport: isRoom ? "1440x900" : "600x760",
      renderer: "Chromium software WebGL2; not real-device performance",
    });
    await page.close();
  }
  // An intentional image-only specimen reuses an original garment still, without any 3D association.
  await mkdir(path.join(pub, "demo/photo-only"), { recursive: true });
  const poster = await readFile(path.join(pub, catalog.products[0].poster));
  await writeFile(path.join(pub, "demo/photo-only/poster.webp"), poster);
  await writeFile(
    path.join(pub, "demo/photo-only/manifest.json"),
    JSON.stringify(
      {
        id: "photo-only",
        title: "My reference overshirt",
        fidelity: "P0",
        fidelityLabel: "Photo display",
        poster: "/demo/photo-only/poster.webp",
        rights: "/demo/rights.json",
        source:
          "Original overshirt render used as image-only fallback; no linked 3D representation",
        files: {
          "poster.webp": {
            bytes: poster.length,
            sha256: createHash("sha256").update(poster).digest("hex"),
          },
        },
      },
      null,
      2,
    ) + "\n",
  );
  await writeFile(
    path.join(pub, "demo/catalog.json"),
    JSON.stringify(catalog, null, 2) + "\n",
  );
  await writeFile(
    path.join(toolsDir, "camera-measurements.json"),
    JSON.stringify(measurements, null, 2) + "\n",
  );
  await writeFile(
    path.join(root, "brandme-frontend/features/spatial/generated-catalog.json"),
    await readFile(
      path.join(root, "brandme-frontend/public/demo/catalog.json"),
    ),
  );
  console.log(
    `Rendered ${measurements.length} original posters with real GLB loads; measurements saved.`,
  );
} finally {
  await browser?.close();
  server.close();
}
