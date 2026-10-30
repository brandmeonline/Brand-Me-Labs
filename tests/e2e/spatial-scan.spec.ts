import { test, expect, type Page } from "../../scripts/assets/node_modules/@playwright/test";

/** Fixtures are injected only by the isolated development harness, never the app route. */
async function fixture(page: Page, behavior = "normal") {
  await page.addInitScript(({ behavior }) => {
    const asset = "12345678-1234-4234-8234-123456789abc";
    const state = { calls: [] as string[], release: undefined as (() => void) | undefined, aborted: false };
    (window as any).__scanFixture = state;
    const claim = (facet: string, value: unknown, id = facet) => ({
      claim_id: id, facet, statement: facet === "ownership" ? "entitlement_controlled" : "product_identified",
      assurance: "fixture", source: "Fictional atelier fixture", environment: "demo", network: "undeployed",
      evidence_ref: "javascript:alert('never render')", test_network: true,
      value, observed_at: "2026-10-01T12:00:00Z",
      expires_at: behavior === "expiring" ? new Date(Date.now() + 5000).toISOString() : behavior === "expired" && facet === "ownership" ? new Date(Date.now() - 1000).toISOString() : null,
      state: behavior === "revoked" && facet === "ownership" ? "revoked" : "current", what_this_means: "UNTRUSTED RAW COPY",
    });
    const claims = (viewer: string) => ({
      api: "brandme.passport.claims/v1", asset_id: asset, viewer,
      environment: "demo", network: "undeployed", next_cursor: null,
      statements: [
        claim("product", { name: "Field Linen Overshirt", category: "Top", owner_email: "SECRET@example.invalid", nested: { receipt: "SECRET RECEIPT" } }),
        claim("house", { name: "Fictional House" }), claim("maker", { name: "Fictional Maker", country: "Fixture country" }),
        claim("story", { summary: "An original garment fixture for the scan experience.", href: "https://evil.invalid" }),
        // Deliberately overbroad fixture response tests display minimization. The
        // actual connector must filter on its server before data reaches a browser.
        claim("price", { amount_minor: "12000", currency: "USD" }),
        claim("ownership", { status: "Fictional owner control", owner_id: "DO NOT RENDER OWNER ID" }),
        claim("logistics", { status: "Fixture delivery pending", shipping_address: "SECRET ADDRESS" }),
        claim("arbitrary", { name: "UNKNOWN FACET SECRET" }),
      ],
    });
    (window as any).__brandmeScanTestConnector = {
      mode: "fixture", sessionKey: "fictional-session", supportsFixturePhoto: true,
      async resolve(input: any, { signal }: { signal: AbortSignal }) {
        state.calls.push(`resolve:${input.kind}`);
        signal.addEventListener("abort", () => { state.aborted = true; }, { once: true });
        if (input.kind === "photo") {
          state.calls.push(`photo:${input.image instanceof Blob}:${input.image.size > 0}:${input.image.type}`);
        }
        if (behavior === "error") throw new Error("SECRET PROVIDER DIAGNOSTIC");
        if (behavior === "race" && input.identifier === "slow") await new Promise<void>(resolve => { state.release = resolve; });
        if (behavior === "timeout") await new Promise<void>(() => {});
        return { asset_id: asset, owner_id: "DO NOT RENDER OWNER ID", anchor_url: "javascript:alert(1)" };
      },
      async readPublicClaims() {
        state.calls.push("public");
        return claims(behavior === "overprivileged" ? "owner" : "public");
      },
      async unfoldOwnerClaims() {
        state.calls.push("owner");
        return claims(behavior === "denied" ? "public" : "owner");
      },
    };
  }, { behavior });
}

async function resolveTag(page: Page, tag = "fixture-tag") {
  await page.getByLabel("Tag identifier", { exact: true }).fill(tag);
  await page.getByRole("button", { name: "Resolve garment", exact: true }).click();
}

test("scan defaults to an honest unconfigured state with no capture or upload", async ({ page }) => {
  const uploads: string[] = [];
  page.on("request", request => { if (["POST", "PUT"].includes(request.method())) uploads.push(request.url()); });
  await page.goto("/add/scan");
  await expect(page.getByRole("heading", { name: "Every piece has a story." })).toBeVisible();
  await expect(page.getByRole("status")).toContainText("Scanning is not connected yet");
  await page.getByLabel("Tag identifier", { exact: true }).fill("fixture-tag");
  await expect(page.getByRole("button", { name: "Resolve garment" })).toBeDisabled();
  await page.getByRole("button", { name: "Photo", exact: true }).click();
  await expect(page.getByText("Photo resolution is unavailable until a test connector is supplied.")).toBeVisible();
  await expect(page.locator("input[type=file], video, canvas")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Shared product details" })).toHaveCount(0);
  expect(uploads).toEqual([]);
});

test("scan displays public facets and opens private details only through explicit owner requests", async ({ page }, info) => {
  await fixture(page);
  await page.goto("/add/scan");
  await resolveTag(page);
  await expect(page.getByText("Field Linen Overshirt", { exact: true })).toBeVisible();
  await expect(page.getByRole("status")).toContainText("simulated lookup");
  for (const name of ["Identity details", "House details", "Maker details", "Story details"])
    await expect(page.getByRole("region", { name, exact: true })).toBeVisible();
  await expect(page.getByText("12000", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Fictional owner control", { exact: true })).toHaveCount(0);
  await expect(page.locator("body")).not.toContainText("SECRET");
  await expect(page.locator("body")).not.toContainText("DO NOT RENDER");
  await expect(page.locator("body")).not.toContainText("UNTRUSTED RAW COPY");
  await expect(page.locator('a[href^="javascript:"], a[href*="evil.invalid"]')).toHaveCount(0);
  expect(await page.evaluate(() => (window as any).__scanFixture.calls)).toEqual(["resolve:tag", "public"]);
  await page.getByRole("button", { name: "Open owner details" }).click();
  await expect(page.getByText("Fictional owner control", { exact: true })).toBeVisible();
  await expect(page.getByText("Fixture delivery pending", { exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "Purchase price details" })).toContainText("USD 120.00");
  await expect(page.locator("body")).not.toContainText("SECRET");
  expect(await page.evaluate(() => (window as any).__scanFixture.calls)).toEqual(["resolve:tag", "public", "owner"]);
  await page.getByRole("button", { name: "Close owner details" }).click();
  await expect(page.getByText("Fictional owner control", { exact: true })).toHaveCount(0);
  await page.setViewportSize({ width: 320, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath("scan-public-320.png"), fullPage: true });
  await page.getByRole("button", { name: "Open owner details" }).click();
  await page.evaluate(() => {
    Object.defineProperty(document, "hidden", { configurable: true, value: true });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await expect(page.getByText("Fictional owner control", { exact: true })).toHaveCount(0);
});

test("owner denial leaves private fields closed and error text does not expose provider data", async ({ page }) => {
  await fixture(page, "denied");
  await page.goto("/add/scan");
  await resolveTag(page);
  await page.getByRole("button", { name: "Open owner details" }).click();
  await expect(page.getByRole("alert")).toContainText("access was denied");
  await expect(page.getByText("Fictional owner control", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Shared product details" })).toBeVisible();
});

for (const behavior of ["expired", "revoked"])
  test(`${behavior} owner claims never disclose their private payload`, async ({ page }) => {
    await fixture(page, behavior);
    await page.goto("/add/scan");
    await resolveTag(page);
    await page.getByRole("button", { name: "Open owner details" }).click();
    await expect(page.getByRole("alert")).toContainText("private details remain closed");
    await expect(page.getByText("Fictional owner control", { exact: true })).toHaveCount(0);
    await expect(page.getByRole("region", { name: "Purchase price details" })).toHaveCount(0);
  });

test("visible claims expire in place and owner disclosure closes without a navigation", async ({ page }) => {
  await fixture(page, "expiring");
  await page.clock.install();
  await page.goto("/add/scan");
  await resolveTag(page);
  await page.getByRole("button", { name: "Open owner details" }).click();
  await expect(page.getByText("Fictional owner control", { exact: true })).toBeVisible();
  await page.clock.runFor(5001);
  await expect(page.getByText("Fictional owner control", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Field Linen Overshirt", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Open owner details" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Identity details", exact: true })).toContainText("expired");
});

test("a non-public default projection is rejected instead of rendering private data", async ({ page }) => {
  await fixture(page, "overprivileged");
  await page.goto("/add/scan");
  await resolveTag(page);
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Shared product details" })).toHaveCount(0);
  await expect(page.getByText("Fictional owner control", { exact: true })).toHaveCount(0);
});

test("changed scan input cancels pending work and ignores a late resolver response", async ({ page }) => {
  await fixture(page, "race");
  await page.goto("/add/scan");
  await resolveTag(page, "slow");
  await expect(page.getByRole("button", { name: "Resolving garment…" })).toBeVisible();
  await page.getByLabel("Tag identifier", { exact: true }).fill("new-tag");
  await page.evaluate(() => (window as any).__scanFixture.release());
  await expect(page.getByRole("heading", { name: "Shared product details" })).toHaveCount(0);
  expect(await page.evaluate(() => (window as any).__scanFixture.calls)).toEqual(["resolve:tag"]);
  expect(await page.evaluate(() => (window as any).__scanFixture.aborted)).toBe(true);
  await page.getByRole("button", { name: "Resolve garment", exact: true }).click();
  await expect(page.getByText("Field Linen Overshirt", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Clear scan" }).click();
  await expect(page.getByRole("heading", { name: "Shared product details" })).toHaveCount(0);
});

test("photo scan sends only the supplied original fixture after explicit consent", async ({ page }) => {
  await fixture(page);
  await page.goto("/add/scan");
  await page.getByRole("button", { name: "Photo", exact: true }).click();
  await expect(page.getByRole("button", { name: "Resolve garment" })).toBeDisabled();
  await expect(page.locator("input[type=file]")).toHaveCount(0);
  await page.getByRole("checkbox", { name: "Use this supplied test image for this resolution request." }).check();
  await page.getByRole("button", { name: "Resolve garment" }).click();
  await expect(page.getByText("Field Linen Overshirt", { exact: true })).toBeVisible();
  expect(await page.evaluate(() => (window as any).__scanFixture.calls)).toEqual(["resolve:photo", "photo:true:true:image/webp", "public"]);
});

test("scan timeout and cancellation keep the request retryable without opening data", async ({ page }) => {
  await fixture(page, "timeout");
  await page.clock.install();
  await page.goto("/add/scan");
  await resolveTag(page);
  await page.clock.runFor(20001);
  await expect(page.getByRole("alert")).toContainText("timed out");
  await expect(page.getByRole("button", { name: "Resolve garment", exact: true })).toBeEnabled();
  expect(await page.evaluate(() => (window as any).__scanFixture.aborted)).toBe(true);
  await page.getByRole("button", { name: "Resolve garment", exact: true }).click();
  await page.getByRole("button", { name: "Cancel request" }).click();
  await expect(page.getByRole("status")).toContainText("Request cancelled");
  await expect(page.getByRole("heading", { name: "Shared product details" })).toHaveCount(0);
});

test("resolver failure is redacted and offline clears all displayed details", async ({ page }) => {
  await fixture(page, "error");
  await page.goto("/add/scan");
  await resolveTag(page);
  await expect(page.getByRole("alert")).toContainText("could not resolve");
  await expect(page.locator("body")).not.toContainText("SECRET PROVIDER");
  await page.context().setOffline(true);
  await expect(page.getByRole("button", { name: "Resolve garment", exact: true })).toBeDisabled();
  await expect(page.getByText("Offline · resolution is paused.")).toBeVisible();
});

test("claims parser rejects mismatched assets, malformed metadata and duplicate claims", async ({ page }) => {
  await page.goto("/add/scan");
  const result = await page.evaluate(async () => {
    const { readScanClaims, readResolvedAsset, validateScanTag } = await import("/brandme-frontend/features/spatial/scanResolution.ts");
    const asset = "12345678-1234-4234-8234-123456789abc";
    const base = {
      api: "brandme.passport.claims/v1", asset_id: asset, viewer: "public",
      statements: [{ claim_id: "c1", facet: "product", statement: "product_identified", source: "Fixture source",
        value: { name: "Fixture item", owner_email: "secret" }, environment: "demo", network: null,
        state: "current", observed_at: "2026-10-01T00:00:00Z", expires_at: "2026-10-02T00:00:00Z" }],
    };
    const rejects = (value: unknown) => { try { readScanClaims(value, asset, "public"); return false; } catch { return true; } };
    let invalidTag = false, invalidResolution = false;
    try { validateScanTag("two identifiers"); } catch { invalidTag = true; }
    try { readResolvedAsset({ asset_id: "not-a-record" }); } catch { invalidResolution = true; }
    const price = (amount_minor: number | string, currency: string) => readScanClaims({ ...base, viewer: "owner", statements: [{ ...base.statements[0], facet: "price", value: { amount_minor, currency }, expires_at: null }] }, asset, "owner").claims[0].lines;
    return {
      mismatch: rejects({ ...base, asset_id: "another-record" }),
      duplicate: rejects({ ...base, statements: [base.statements[0], base.statements[0]] }),
      malformed: rejects({ ...base, statements: [{ ...base.statements[0], observed_at: "tomorrow" }] }),
      oversized: rejects({ ...base, statements: Array(101).fill(base.statements[0]) }),
      expired: readScanClaims(base, asset, "public", Date.parse("2026-10-03T00:00:00Z")).claims[0].state,
      expiredLines: readScanClaims(base, asset, "public", Date.parse("2026-10-03T00:00:00Z")).claims[0].lines,
      minimized: readScanClaims(base, asset, "public", Date.parse("2026-10-01T12:00:00Z")).claims[0].lines,
      numericPrice: price(12000, "USD"),
      zeroExponentPrice: price("12000", "JPY"),
      threeExponentPrice: price("12001", "KWD"),
      largeExactPrice: price("900719925474099312345", "USD"),
      unsafeNumericPrice: price(Number.MAX_SAFE_INTEGER + 1, "USD"),
      unknownStatement: readScanClaims({ ...base, statements: [{ ...base.statements[0], statement: "__proto__" }] }, asset, "public").claims[0].statement,
      invalidTag, invalidResolution,
    };
  });
  expect(result).toEqual({ mismatch: true, duplicate: true, malformed: true, oversized: true, expired: "expired", expiredLines: [], minimized: [{ label: "Name", text: "Fixture item" }],
    numericPrice: [{ label: "Purchase price", text: "USD 120.00" }],
    zeroExponentPrice: [{ label: "Purchase price", text: "JPY 12000" }],
    threeExponentPrice: [{ label: "Purchase price", text: "KWD 12.001" }],
    largeExactPrice: [{ label: "Purchase price", text: "USD 9007199254740993123.45" }],
    unsafeNumericPrice: [], unknownStatement: "Product statement", invalidTag: true, invalidResolution: true });
});
