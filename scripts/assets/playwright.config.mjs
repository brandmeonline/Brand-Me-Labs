import { defineConfig } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";
const root = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../..",
);
export default defineConfig({
  testDir: path.join(root, "tests/e2e"),
  testMatch: "spatial*.spec.ts",
  fullyParallel: false,
  workers: 1,
  timeout: 45000,
  expect: { timeout: 12000 },
  reporter: [
    ["list"],
    [
      "json",
      {
        outputFile: path.join(
          root,
          "scripts/assets/evidence/browser-results.json",
        ),
      },
    ],
  ],
  outputDir: path.join(root, "scripts/assets/evidence/runs"),
  use: {
    baseURL: "http://127.0.0.1:4178",
    viewport: { width: 1440, height: 900 },
    trace: "retain-on-failure",
    video: "retain-on-failure",
    launchOptions: { args: ["--no-sandbox", "--enable-unsafe-swiftshader"] },
  },
  webServer: {
    command: "node scripts/assets/dev.mjs",
    cwd: root,
    url: "http://127.0.0.1:4178/closet",
    reuseExistingServer: false,
    timeout: 30000,
  },
});
