import { createServer } from "node:http";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import { chromium } from "@playwright/test";
const tools = path.dirname(fileURLToPath(import.meta.url)),
  pub = path.resolve(tools, "../../brandme-frontend/public");
const server = createServer(async (req, res) => {
  try {
    const url = new URL(req.url, "http://localhost");
    const base = url.pathname.startsWith("/tools/") ? tools : pub;
    const name =
      url.pathname === "/"
        ? path.join(tools, "overlay.html")
        : path.resolve(base, "." + url.pathname.replace(/^\/tools/, ""));
    if (
      !name.startsWith(base + "/") &&
      name !== path.join(tools, "overlay.html")
    )
      throw Error();
    res.setHeader(
      "Content-Type",
      name.endsWith(".html")
        ? "text/html"
        : name.endsWith(".js")
          ? "text/javascript"
          : "application/octet-stream",
    );
    res.end(await readFile(name));
  } catch {
    res.writeHead(404);
    res.end();
  }
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const browser = await chromium.launch({
  args: ["--no-sandbox", "--enable-unsafe-swiftshader"],
});
const records = [];
try {
  for (const slug of ["overshirt", "tee", "knit", "jacket"]) {
    const page = await browser.newPage();
    await page.goto(`http://127.0.0.1:${server.address().port}/?slug=${slug}`);
    await page.waitForFunction(() => window.exported);
    const output = await page.evaluate(() => window.exported);
    const data = Buffer.from(output.png.split(",")[1], "base64");
    const dest = path.join(pub, "demo/overlays");
    await mkdir(dest, { recursive: true });
    await writeFile(path.join(dest, slug + ".png"), data);
    records.push({
      slug,
      file: `/demo/overlays/${slug}.png`,
      sha256: createHash("sha256").update(data).digest("hex"),
      bytes: data.length,
      dimensions: output.dimensions,
      removed: output.removed,
    });
    await page.close();
  }
  await writeFile(
    path.join(pub, "demo/overlays/manifest.json"),
    JSON.stringify(
      {
        fidelity: "P1",
        label: "Approximate image overlay",
        source:
          "scripts/assets/overlay.mjs + overlay.html; existing original GLBs, neutral orthographic export without hanger",
        rights: "/demo/rights.json",
        fit: false,
        bodyBinding: false,
        assets: records,
      },
      null,
      2,
    ) + "\n",
  );
} finally {
  await browser.close();
  server.close();
}
