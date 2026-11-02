import { test, expect } from "../../scripts/assets/node_modules/@playwright/test";
import { createPassportClaimsReader } from "../../brandme-frontend/features/spatial/passportClaimsReader";
import type { PassportClaimRead, PassportClaimsRead } from "../../packages/contracts/generated/schemas";

const asset = "12345678-1234-4234-8234-123456789abc";
const claimId = (n: number) => `12345678-1234-4234-8234-${n.toString(16).padStart(12, "0")}`;
const claim = (n = 1): PassportClaimRead => ({
  claim_id: claimId(n), facet: "product", statement: "product_identified", assurance: "fixture",
  source: "Synthetic claims fixture", environment: "demo", network: "undeployed", test_network: true,
  evidence_ref: null, value: { name: "Fictional garment" }, observed_at: "2026-10-01T12:00:00Z",
  expires_at: null, state: "current", what_this_means: "Fictional test statement",
});
const projection = (overrides: Partial<PassportClaimsRead> = {}): PassportClaimsRead => ({
  api: "brandme.passport.claims/v1", asset_id: asset, viewer: "public", environment: "demo", network: "undeployed",
  next_cursor: null, statements: [claim()], ...overrides,
});
const json = (body: unknown) => new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json; charset=utf-8" } });
const options = () => ({ signal: new AbortController().signal });
function queuedFetch(pages: unknown[]) {
  const requests: { url: string; init: RequestInit }[] = [];
  const fetcher: typeof fetch = async (url, init) => {
    requests.push({ url: String(url), init: init! });
    if (!pages.length) throw new Error("Unexpected request");
    return json(pages.shift());
  };
  return { fetcher, requests };
}

test("claims transport separates credentials across all pages and preserves the generated projection", async () => {
  for (const viewer of ["public", "owner"] as const) {
    const raw = claim(2);
    raw.facet = "unknown_future_facet";
    raw.value = { arbitrary: ["opaque", { nested: true }] };
    raw.evidence_ref = "https://fixture.invalid/not-followed";
    const queue = queuedFetch([
      projection({ viewer, next_cursor: claimId(1) }), projection({ viewer, statements: [raw] }),
    ]);
    const reader = createPassportClaimsReader(queue.fetcher);
    expect(queue.requests).toEqual([]);
    const result = await (viewer === "public" ? reader.readPublicClaims : reader.unfoldOwnerClaims)(asset.toUpperCase(), options());
    expect(result).toEqual(projection({ viewer, asset_id: asset.toUpperCase(), statements: [claim(), raw] }));
    expect(queue.requests.map(request => request.url)).toEqual([
      `/api/v1/assets/${asset}/passport?limit=24`, `/api/v1/assets/${asset}/passport?limit=24&cursor=${claimId(1)}`,
    ]);
    for (const { init } of queue.requests) {
      expect(init).toMatchObject({ method: "GET", credentials: viewer === "public" ? "omit" : "same-origin",
        mode: "same-origin", redirect: "error", cache: "no-store", headers: { Accept: "application/json" } });
      expect(init.signal).toBeInstanceOf(AbortSignal);
      expect(init.body).toBeUndefined();
    }
  }
});

test("invalid identifiers fail before any request", async () => {
  const queue = queuedFetch([]), reader = createPassportClaimsReader(queue.fetcher);
  for (const id of ["", " ../asset", `${asset}?viewer=owner`, `https://fixture.invalid/${asset}`, `${asset}/passport`])
    await expect(reader.readPublicClaims(id, options())).rejects.toThrow(/valid passport asset identifier/);
  expect(queue.requests).toEqual([]);
});

test("identity, viewer, scope and generated claim shape fail closed", async () => {
  const invalidPages = [
    { ...projection(), api: "other/v1" }, { ...projection(), asset_id: claimId(9) },
    { ...projection(), viewer: "owner" }, { ...projection(), secret: "UNTRUSTED DIAGNOSTIC" },
    { ...projection(), environment: "invented" }, { ...projection(), network: "invented" },
    { ...projection(), next_cursor: "https://fixture.invalid/page" },
    ...[
      { claim_id: "not-a-uuid" }, { source: 7 }, { value: undefined }, { observed_at: "yesterday" },
      { expires_at: "2026-11-01" }, { state: "invented" }, { environment: "production" },
      { network: "mainnet" }, { test_network: "true" }, { evidence_ref: { href: "private" } }, { extra: true },
    ].map(overrides => projection({ statements: [{ ...claim(), ...overrides } as PassportClaimRead] })),
  ];
  for (const page of invalidPages) {
    const queue = queuedFetch([page]);
    await expect(createPassportClaimsReader(queue.fetcher).readPublicClaims(asset, options())).rejects.toThrow("The passport response could not be verified.");
    expect(queue.requests).toHaveLength(1);
  }
});

test("pagination never returns partial claims after duplicate, cyclic, changed-scope or denied later pages", async () => {
  const first = projection({ next_cursor: claimId(1) });
  const badSecondPages = [
    projection(), // Duplicate claim identifier.
    projection({ statements: [claim(2)], next_cursor: claimId(1) }),
    projection({ statements: [], next_cursor: claimId(2) }),
    projection({ statements: [claim(2)], asset_id: claimId(9) }),
    projection({ statements: [{ ...claim(2), environment: "production" }], environment: "production" }),
    projection({ statements: [{ ...claim(2), network: "mainnet" }], network: "mainnet" }),
  ];
  for (const second of badSecondPages) {
    const queue = queuedFetch([first, second]);
    await expect(createPassportClaimsReader(queue.fetcher).readPublicClaims(asset, options())).rejects.toThrow(/could not be verified/);
    expect(queue.requests).toHaveLength(2);
  }
  const owner = queuedFetch([{ ...first, viewer: "owner" }, projection({ statements: [claim(2)] })]);
  await expect(createPassportClaimsReader(owner.fetcher).unfoldOwnerClaims(asset, options())).rejects.toThrow(/not authorized/);
  expect(owner.requests).toHaveLength(2);
  expect(owner.requests.every(request => request.init.credentials === "same-origin")).toBe(true);
});

test("claim and page limits accept exactly 100 and reject any incomplete projection", async () => {
  const pages = Array.from({ length: 5 }, (_, index) => {
    const count = index === 4 ? 4 : 24;
    const statements = Array.from({ length: count }, (_, n) => claim(index * 24 + n + 1));
    return projection({ statements, next_cursor: index === 4 ? null : statements.at(-1)!.claim_id });
  });
  const valid = queuedFetch([...pages]);
  expect((await createPassportClaimsReader(valid.fetcher).readPublicClaims(asset, options())).statements).toHaveLength(100);
  expect(valid.requests.at(-1)!.url).toContain("?limit=4&cursor=");
  const tooMany = queuedFetch(pages.map((page, index) => index === 4 ? { ...page, next_cursor: claimId(100) } : page));
  await expect(createPassportClaimsReader(tooMany.fetcher).readPublicClaims(asset, options())).rejects.toThrow(/limits/);
  expect(tooMany.requests).toHaveLength(5);
  const tooManyPages = queuedFetch(Array.from({ length: 6 }, (_, n) => projection({ statements: [claim(n + 1)], next_cursor: claimId(n + 1) })));
  await expect(createPassportClaimsReader(tooManyPages.fetcher).readPublicClaims(asset, options())).rejects.toThrow(/limits/);
  expect(tooManyPages.requests).toHaveLength(5);
  const oversizedPage = queuedFetch([projection({ statements: Array.from({ length: 25 }, (_, n) => claim(n + 1)) })]);
  await expect(createPassportClaimsReader(oversizedPage.fetcher).readPublicClaims(asset, options())).rejects.toThrow(/could not be verified/);
});

test("streamed bytes and aggregate bytes are bounded even without a content-length", async () => {
  let cancelled = false;
  const largeStream = new ReadableStream<Uint8Array>({
    start(controller) { controller.enqueue(new Uint8Array(1024 * 1024 + 1)); },
    cancel() { cancelled = true; },
  });
  await expect(createPassportClaimsReader(async () => new Response(largeStream, { headers: { "Content-Type": "application/json" } }))
    .readPublicClaims(asset, options())).rejects.toThrow(/limits/);
  expect(cancelled).toBe(true);
  const queue = queuedFetch(Array.from({ length: 3 }, (_, n) => projection({
    statements: [{ ...claim(n + 1), value: "x".repeat(400_000) }], next_cursor: claimId(n + 1),
  })));
  await expect(createPassportClaimsReader(queue.fetcher).readPublicClaims(asset, options())).rejects.toThrow(/limits/);
  expect(queue.requests).toHaveLength(3);
  await expect(createPassportClaimsReader(async () => new Response("", { headers: {
    "Content-Type": "application/json", "Content-Length": String(1024 * 1024 + 1),
  } })).readPublicClaims(asset, options())).rejects.toThrow(/limits/);
});

test("HTTP failures, malformed JSON and redirected responses expose no provider diagnostics", async () => {
  const responses = [
    new Response("UNTRUSTED DIAGNOSTIC", { status: 503 }),
    new Response("UNTRUSTED DIAGNOSTIC", { headers: { "Content-Type": "text/html" } }),
    new Response("UNTRUSTED DIAGNOSTIC", { headers: { "Content-Type": "application/json" } }),
    new Response(new Uint8Array([0xff]), { headers: { "Content-Type": "application/json" } }),
    Object.defineProperty(json(projection()), "redirected", { value: true }),
    Object.defineProperty(json(projection()), "url", { value: `https://fixture.invalid/api/v1/assets/${asset}/passport?limit=24` }),
  ];
  for (const response of responses) {
    const outcome = await createPassportClaimsReader(async () => response).readPublicClaims(asset, options()).catch((error: Error) => error.message);
    expect(outcome).toMatch(/^The passport (service is unavailable|response could not be verified)\.$/);
  }
  for (const status of [401, 403])
    await expect(createPassportClaimsReader(async () => new Response("UNTRUSTED DIAGNOSTIC", { status }))
      .unfoldOwnerClaims(asset, options())).rejects.toThrow(/not authorized/);
});

test("caller cancellation stops fetch and response streaming, including transports that ignore abort", async () => {
  const early = new AbortController(); early.abort("PRIVATE ABORT DETAIL");
  const unused = queuedFetch([]);
  await expect(createPassportClaimsReader(unused.fetcher).readPublicClaims(asset, { signal: early.signal })).rejects.toMatchObject({ name: "AbortError" });
  expect(unused.requests).toEqual([]);
  let requestSignal: AbortSignal | null = null;
  const controller = new AbortController();
  const pending = createPassportClaimsReader(async (_, init) => {
    requestSignal = init!.signal!;
    return new Promise<Response>(() => {});
  }).readPublicClaims(asset, { signal: controller.signal });
  controller.abort("PRIVATE ABORT DETAIL");
  await expect(pending).rejects.toMatchObject({ name: "AbortError", message: "The passport request was cancelled." });
  expect(requestSignal!.aborted).toBe(true);
  let cancelled = false;
  const streaming = new AbortController();
  let started!: () => void;
  const reading = new Promise<void>(resolve => { started = resolve; });
  const body = new ReadableStream<Uint8Array>({ pull() { started(); }, cancel() { cancelled = true; } });
  const read = createPassportClaimsReader(async () => new Response(body, { headers: { "Content-Type": "application/json" } }))
    .readPublicClaims(asset, { signal: streaming.signal });
  await reading;
  streaming.abort();
  await expect(read).rejects.toMatchObject({ name: "AbortError" });
  expect(cancelled).toBe(true);
});

test("real browser public requests omit the session cookie on every page; explicit owner requests include it", async ({ page, context }) => {
  await context.addCookies([{ name: "bm_session", value: "synthetic-session-for-transport-test", url: "http://127.0.0.1:4178", httpOnly: true, sameSite: "Lax" }]);
  const seen: { cookie: string | null; cursor: string | null }[] = [];
  await page.route("**/api/v1/assets/*/passport?*", async route => {
    const request = route.request(), cookie = await request.headerValue("cookie");
    const cursor = new URL(request.url()).searchParams.get("cursor");
    seen.push({ cookie, cursor });
    await route.fulfill({ json: projection({ viewer: cookie ? "owner" : "public",
      statements: [claim(cursor ? 2 : 1)], next_cursor: cursor ? null : claimId(1) }) });
  });
  await page.goto("/add/scan");
  const publicResult = await page.evaluate(async assetId => {
    const { createPassportClaimsReader } = await import("/brandme-frontend/features/spatial/passportClaimsReader.ts");
    return createPassportClaimsReader().readPublicClaims(assetId, { signal: new AbortController().signal });
  }, asset);
  expect(publicResult.viewer).toBe("public");
  expect(publicResult.statements).toHaveLength(2);
  expect(seen).toEqual([{ cookie: null, cursor: null }, { cookie: null, cursor: claimId(1) }]);
  const ownerResult = await page.evaluate(async assetId => {
    const { createPassportClaimsReader } = await import("/brandme-frontend/features/spatial/passportClaimsReader.ts");
    return createPassportClaimsReader().unfoldOwnerClaims(assetId, { signal: new AbortController().signal });
  }, asset);
  expect(ownerResult.viewer).toBe("owner");
  expect(ownerResult.statements).toHaveLength(2);
  expect(seen.slice(2)).toEqual([
    { cookie: "bm_session=synthetic-session-for-transport-test", cursor: null },
    { cookie: "bm_session=synthetic-session-for-transport-test", cursor: claimId(1) },
  ]);
  // Reading alone neither wires the scan UI nor activates its resolver.
  await expect(page.getByRole("status")).toContainText("Scanning is not connected yet");
});

test("real browser refuses redirected API reads without following the destination", async ({ page }) => {
  const destinations: string[] = [];
  await page.route("https://passport-redirect.invalid/**", async route => {
    destinations.push(route.request().url());
    await route.fulfill({ json: projection() });
  });
  await page.route("**/api/v1/assets/*/passport?*", route => route.fulfill({ status: 302, headers: { Location: "https://passport-redirect.invalid/leak" } }));
  await page.goto("/add/scan");
  const outcome = await page.evaluate(async assetId => {
    const { createPassportClaimsReader } = await import("/brandme-frontend/features/spatial/passportClaimsReader.ts");
    return createPassportClaimsReader().readPublicClaims(assetId, { signal: new AbortController().signal })
      .then(() => "unexpected success", (error: Error) => error.message);
  }, asset);
  expect(outcome).toBe("The passport service is unavailable.");
  expect(destinations).toEqual([]);
});

test("whole-read deadline aborts a stalled browser transport", async ({ page }) => {
  await page.goto("/add/scan");
  await page.clock.install();
  await page.evaluate(async assetId => {
    const { createPassportClaimsReader } = await import("/brandme-frontend/features/spatial/passportClaimsReader.ts");
    const state = { aborted: false, result: "pending" };
    (window as any).__claimsDeadline = state;
    void createPassportClaimsReader(async (_, init) => {
      init!.signal!.addEventListener("abort", () => { state.aborted = true; });
      return new Promise<Response>(() => {});
    }).readPublicClaims(assetId, { signal: new AbortController().signal })
      .then(() => { state.result = "unexpected success"; }, (error: Error) => { state.result = error.message; });
  }, asset);
  await page.clock.runFor(15_001);
  expect(await page.evaluate(() => (window as any).__claimsDeadline)).toEqual({ aborted: true, result: "The passport request timed out." });
});
