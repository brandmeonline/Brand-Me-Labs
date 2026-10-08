import { chromium } from "@playwright/test";
import { mkdir, rename, rm } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { server } from "./dev.mjs";
const evidence = path.join(
  path.dirname(fileURLToPath(import.meta.url)),
  "evidence",
);
await mkdir(evidence, { recursive: true });
const browser = await chromium.launch({
  headless: true,
  args: ["--no-sandbox", "--enable-unsafe-swiftshader"],
});
const temporary = path.join(evidence, "motion-capture");
try {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    recordVideo: { dir: temporary, size: { width: 1440, height: 900 } },
  });
  const page = await context.newPage();
  await page.goto("http://127.0.0.1:4178/add");
  await page.getByRole("button", { name: /Ribbed Oat Knit/ }).click();
  await page.locator("[data-room-ready]").scrollIntoViewIfNeeded();
  await page.waitForFunction(
    () =>
      document
        .querySelector("[data-room-ready]")
        ?.getAttribute("data-room-ready") === "true",
  );
  await page
    .getByRole("button", { name: "Add to closet", exact: true })
    .click();
  await page.getByTestId("placement-flight").waitFor({ state: "visible" });
  await page.waitForTimeout(1200);
  await page.getByRole("button", { name: "Undo", exact: true }).click();
  await page
    .getByRole("status")
    .filter({ hasText: "Addition undone" })
    .waitFor();
  await page.waitForTimeout(400);
  const video = page.video();
  await context.close();
  await video.saveAs(path.join(evidence, "signature-placement.webm"));
  await rm(temporary, { recursive: true, force: true });
  console.log(
    "Recorded committed add, 900ms transition, settled state, and inverse Undo.",
  );
} finally {
  await browser.close();
  await server.close();
}
