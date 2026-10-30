// Type-only generated entry avoids the runtime client/barrel in the isolated
// spatial harness, whose tsconfig does not enable .ts runtime import paths.
import type { PassportClaimRead, PassportClaimsRead } from "../../../packages/contracts/generated/schemas";

/** The HTTP half of ScanConnector; resolution and session lifecycle belong to its host. */
export interface PassportClaimsReader {
  readPublicClaims(assetId: string, options: { signal: AbortSignal }): Promise<PassportClaimsRead>;
  unfoldOwnerClaims(assetId: string, options: { signal: AbortSignal }): Promise<PassportClaimsRead>;
}

const uuid = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
const environments = ["demo", "development", "sandbox", "production"];
const networks = ["undeployed", "preview", "preprod", "mainnet"];
const pageKeys = ["api", "asset_id", "viewer", "environment", "network", "next_cursor", "statements"];
const claimKeys = ["claim_id", "facet", "statement", "assurance", "source", "environment", "network",
  "test_network", "evidence_ref", "value", "observed_at", "expires_at", "state", "what_this_means"];
const MAX_CLAIMS = 100, PAGE_SIZE = 24, MAX_PAGES = 5, MAX_BYTES = 1024 * 1024, TIMEOUT_MS = 15_000;

class ClaimsReadError extends Error {}
const invalid = () => new ClaimsReadError("The passport response could not be verified.");
const oversized = () => new ClaimsReadError("The passport exceeds the scan reader's limits.");
const denied = () => new ClaimsReadError("Owner disclosure was not authorized for this session.");
const aborted = () => new DOMException("The passport request was cancelled.", "AbortError");
const record = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);
const exactKeys = (value: Record<string, unknown>, keys: string[]) =>
  Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
const oneOf = (value: unknown, values: string[]) => typeof value === "string" && values.includes(value);
const date = (value: unknown) => typeof value === "string" &&
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/i.test(value) && Number.isFinite(Date.parse(value));

function validatePage(value: unknown, assetId: string, viewer: PassportClaimsRead["viewer"], limit: number): PassportClaimsRead {
  if (!record(value) || !exactKeys(value, pageKeys) || value.api !== "brandme.passport.claims/v1" ||
      typeof value.asset_id !== "string" || value.asset_id.toLowerCase() !== assetId.toLowerCase() ||
      !oneOf(value.viewer, ["public", "owner"]) || !oneOf(value.environment, environments) ||
      !oneOf(value.network, networks) || !Array.isArray(value.statements) || value.statements.length > limit ||
      !(value.next_cursor === null || typeof value.next_cursor === "string" && uuid.test(value.next_cursor))) throw invalid();
  if (value.viewer !== viewer) throw viewer === "owner" ? denied() : invalid();
  for (const claim of value.statements) {
    if (!record(claim) || !exactKeys(claim, claimKeys) || typeof claim.claim_id !== "string" || !uuid.test(claim.claim_id) ||
        !["facet", "statement", "assurance", "source", "what_this_means"].every(key => typeof claim[key] === "string") ||
        claim.environment !== value.environment || !(claim.network === null || claim.network === value.network) ||
        typeof claim.test_network !== "boolean" || !(claim.evidence_ref === null || typeof claim.evidence_ref === "string") ||
        !date(claim.observed_at) || !(claim.expires_at === null || date(claim.expires_at)) ||
        !oneOf(claim.state, ["current", "expired", "revoked"])) throw invalid();
  }
  // `value` is deliberately opaque in the generated contract. This transport
  // supplies no facet mappings and never renders or follows evidence references.
  return value as unknown as PassportClaimsRead;
}

/** Reject promptly even if a test transport or response stream ignores cancellation. */
async function withAbort<T>(operation: Promise<T>, signal: AbortSignal): Promise<T> {
  let onAbort: () => void = () => {};
  const interruption = new Promise<never>((_, reject) => {
    onAbort = () => reject(aborted());
    signal.addEventListener("abort", onAbort, { once: true });
    if (signal.aborted) onAbort();
  });
  try { return await Promise.race([operation, interruption]); }
  finally { signal.removeEventListener("abort", onAbort); }
}

async function readBody(response: Response, remaining: number, signal: AbortSignal): Promise<{ value: unknown; bytes: number }> {
  const length = response.headers.get("content-length");
  if (length !== null && (!/^\d+$/.test(length) || Number(length) > remaining)) {
    void response.body?.cancel().catch(() => {});
    throw oversized();
  }
  if (!response.body) throw invalid();
  const reader = response.body.getReader(), chunks: Uint8Array[] = [];
  let bytes = 0, completed = false;
  try {
    while (true) {
      const chunk = await withAbort(reader.read(), signal);
      if (chunk.done) { completed = true; break; }
      bytes += chunk.value.byteLength;
      if (bytes > remaining) throw oversized();
      chunks.push(chunk.value);
    }
    const body = new Uint8Array(bytes);
    let offset = 0;
    for (const chunk of chunks) { body.set(chunk, offset); offset += chunk.byteLength; }
    try { return { value: JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(body)), bytes }; }
    catch { throw invalid(); }
  } finally {
    if (!completed) void reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

/**
 * Same-origin browser transport for the generated PassportClaimsRead contract.
 * Creation performs no requests. Only an explicit unfoldOwnerClaims call sends
 * same-origin session credentials; every public page uses credentials: "omit".
 * See passportClaimsReader.md for composition, limits and integration obligations.
 * An injected fetch must be a trusted Fetch-compatible test transport, never a
 * helper that adds authentication, rewrites URLs or changes request options.
 */
export function createPassportClaimsReader(fetcher: typeof fetch = globalThis.fetch): PassportClaimsReader {
  async function read(assetId: string, viewer: PassportClaimsRead["viewer"], { signal }: { signal: AbortSignal }): Promise<PassportClaimsRead> {
    if (typeof assetId !== "string" || !uuid.test(assetId)) throw new ClaimsReadError("A valid passport asset identifier is required.");
    if (signal.aborted) throw aborted();
    const controller = new AbortController();
    const onAbort = () => controller.abort();
    signal.addEventListener("abort", onAbort, { once: true });
    let timedOut = false;
    const timer = setTimeout(() => { timedOut = true; controller.abort(); }, TIMEOUT_MS);
    let first: PassportClaimsRead | undefined, cursor: string | null = null, bytes = 0;
    const statements: PassportClaimRead[] = [], claimIds = new Set<string>(), cursors = new Set<string>();
    try {
      for (let pageIndex = 0; pageIndex < MAX_PAGES; pageIndex++) {
        const limit = Math.min(PAGE_SIZE, MAX_CLAIMS - statements.length);
        if (limit === 0) throw oversized();
        const query = new URLSearchParams({ limit: String(limit) });
        if (cursor !== null) query.set("cursor", cursor);
        const path = `/api/v1/assets/${assetId.toLowerCase()}/passport?${query}`;
        // mode: same-origin also fails closed if a document's base URL points
        // elsewhere. There is no configurable origin, header or disclosure flag.
        const response = await withAbort(fetcher(path, {
          method: "GET", credentials: viewer === "public" ? "omit" : "same-origin",
          mode: "same-origin", redirect: "error", cache: "no-store",
          headers: { Accept: "application/json" }, signal: controller.signal,
        }), controller.signal);
        const url = response.url ? new URL(response.url) : null;
        if (response.redirected || response.type === "opaqueredirect" || response.type === "opaque" ||
            url && (typeof location === "undefined" || url.origin !== location.origin || url.pathname + url.search !== path)) {
          void response.body?.cancel().catch(() => {});
          throw invalid();
        }
        if (response.status !== 200 || response.headers.get("content-type")?.split(";", 1)[0].trim().toLowerCase() !== "application/json") {
          void response.body?.cancel().catch(() => {});
          if (viewer === "owner" && [401, 403].includes(response.status)) throw denied();
          throw new ClaimsReadError("The passport service is unavailable.");
        }
        const body = await readBody(response, MAX_BYTES - bytes, controller.signal);
        bytes += body.bytes;
        const page = validatePage(body.value, assetId, viewer, limit);
        if (first && (page.environment !== first.environment || page.network !== first.network)) throw invalid();
        first ??= page;
        for (const claim of page.statements) {
          const id = claim.claim_id.toLowerCase();
          if (claimIds.has(id)) throw invalid();
          claimIds.add(id);
          statements.push(claim);
        }
        if (controller.signal.aborted) throw aborted();
        if (page.next_cursor === null) {
          // Preserve the requested UUID's representation for ScanExperience's
          // exact identity comparison; the server identity was checked above.
          return { ...first, asset_id: assetId, statements, next_cursor: null };
        }
        const next = page.next_cursor.toLowerCase();
        if (!page.statements.length || cursors.has(next)) throw invalid();
        cursors.add(next);
        cursor = next;
      }
      throw oversized();
    } catch (error) {
      if (signal.aborted) throw aborted();
      if (timedOut) throw new ClaimsReadError("The passport request timed out.");
      if (error instanceof ClaimsReadError) throw error;
      // Never surface provider bodies, request URLs, identifiers or fetch errors.
      throw new ClaimsReadError("The passport service is unavailable.");
    } finally {
      clearTimeout(timer);
      signal.removeEventListener("abort", onAbort);
      controller.abort();
    }
  }
  return {
    readPublicClaims: (assetId, options) => read(assetId, "public", options),
    unfoldOwnerClaims: (assetId, options) => read(assetId, "owner", options),
  };
}
