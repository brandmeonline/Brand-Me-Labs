/**
 * A presentation adapter, not an anchor registry or an authorization policy.
 *
 * The response discriminator/fields below consume the existing Midnight-owned
 * brandme.passport.claims/v1 contract (PassportClaimsRead in the generated API
 * package). passportClaimsReader supplies its bounded HTTP transport. No
 * scan-to-anchor resolver exists here: the host must inject one and enforce disclosure on the
 * server. A tag identifier, successful lookup, or browser button grants no rights.
 */
export type ScanInput =
  | { kind: "tag"; identifier: string }
  | { kind: "photo"; image: Blob };

export interface ScanConnector {
  mode: "fixture" | "development";
  /** Change on sign-out/account change/revocation; clears displayed claims. */
  sessionKey: string;
  supportsFixturePhoto?: boolean;
  /** Resolve against the authoritative anchor service; return { asset_id }. */
  resolve(input: ScanInput, options: { signal: AbortSignal }): Promise<unknown>;
  /** Must request a server-filtered public projection, even for an owner. */
  readPublicClaims(assetId: string, options: { signal: AbortSignal }): Promise<unknown>;
  /** Optional, authenticated server action. Never accept a browser owner flag. */
  unfoldOwnerClaims?(assetId: string, options: { signal: AbortSignal }): Promise<unknown>;
}

export type ScanFacet = "identity" | "house" | "maker" | "story" | "price" | "ownership" | "logistics";
export const publicScanFacets = ["identity", "house", "maker", "story"] as const;
export const ownerScanFacets = ["price", "ownership", "logistics"] as const;
export const scanFacetLabels: Record<ScanFacet, string> = {
  identity: "Identity", house: "House", maker: "Maker", story: "Story",
  price: "Purchase price", ownership: "Ownership", logistics: "Logistics",
};
export const scanPhotoFixture = "/demo/garments/overshirt/poster.webp";

export interface ScanClaim {
  id: string;
  facet: ScanFacet;
  lines: { label: string; text: string }[];
  statement: string;
  source: string;
  observedAt: string;
  expiresAt: string | null;
  state: "current" | "expired" | "revoked";
  environment: "demo" | "development" | "sandbox" | "production";
  network: "undeployed" | "preview" | "preprod" | "mainnet" | null;
}
export interface ScanClaims { assetId: string; viewer: "public" | "owner"; claims: ScanClaim[] }

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const record = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);
const text = (v: unknown, max = 240): string | null =>
  typeof v === "string" && v.trim().length > 0 && v.length <= max &&
  !/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(v) ? v.trim() : null;
const date = (v: unknown): string | null =>
  typeof v === "string" && v.length <= 40 && /^\d{4}-\d{2}-\d{2}T/.test(v) &&
  Number.isFinite(Date.parse(v)) ? v : null;

export function validateScanTag(value: string): string {
  const tag = value.trim();
  if (!tag || tag.length > 256 || /[\s\u0000-\u001f\u007f]/.test(tag))
    throw new Error("Enter a tag identifier of 1–256 characters without spaces.");
  // Opaque data for the resolver, never a link that the browser follows.
  return tag;
}

export function readResolvedAsset(value: unknown): string {
  if (!record(value) || typeof value.asset_id !== "string" || !uuid.test(value.asset_id))
    throw new Error("The resolver did not return a valid product record.");
  return value.asset_id;
}

// Deliberately small rendering vocabulary. This is defense in depth, not the
// server's disclosure filter. Unknown/nested values, URLs, evidence refs and
// owner identifiers are never dumped into the DOM or followed as links.
const fields: Record<ScanFacet, readonly [string, string][]> = {
  identity: [["name", "Name"], ["category", "Category"]],
  house: [["name", "House"]],
  maker: [["name", "Maker"], ["country", "Country"]],
  story: [["summary", "Story"]],
  price: [],
  ownership: [["status", "Status"]],
  logistics: [["status", "Status"]],
};
const statementLabels: Record<string, string> = {
  product_identified: "Product identified",
  tag_verified: "Tag authentication reported; this does not establish physical possession.",
  issuer_recognized: "Issuer recognized",
  entitlement_controlled: "Digital entitlement control reported; this does not establish physical possession.",
  ownership_claim_reviewed: "Ownership claim reviewed",
  lifecycle_attested: "Lifecycle event attested",
};

function priceLines(data: Record<string, unknown>): { label: string; text: string }[] {
  const rawAmount = data.amount_minor;
  const amount = typeof rawAmount === "number"
    ? Number.isSafeInteger(rawAmount) && rawAmount >= 0 ? String(rawAmount) : null
    : text(rawAmount, 30);
  const currency = text(data.currency, 3);
  if (!amount || !/^\d{1,30}$/.test(amount) || !currency || !/^[A-Z]{3}$/.test(currency)) return [];
  // Intl supplies the currency's exponent; keep the amount as decimal digits
  // throughout so large integer strings never lose cents through Number().
  const exponent = new Intl.NumberFormat("en", { style: "currency", currency }).resolvedOptions().maximumFractionDigits;
  if (exponent === undefined || !Number.isInteger(exponent) || exponent < 0 || exponent > 6) return [];
  const normalized = amount.replace(/^0+(?=\d)/, "");
  const padded = normalized.padStart(exponent + 1, "0");
  const display = exponent === 0 ? normalized : `${padded.slice(0, -exponent)}.${padded.slice(-exponent)}`;
  return [{ label: "Purchase price", text: `${currency} ${display}` }];
}

/** Validate and narrow an already server-filtered claim projection for display. */
export function readScanClaims(value: unknown, assetId: string, viewer: "public" | "owner", now = Date.now()): ScanClaims {
  if (!record(value) || value.api !== "brandme.passport.claims/v1" ||
      value.asset_id !== assetId || value.viewer !== viewer ||
      !Array.isArray(value.statements) || value.statements.length > 100)
    throw new Error(viewer === "owner" ? "Owner disclosure was not authorized for this session." : "The product details could not be verified.");
  const claims: ScanClaim[] = [];
  const ids = new Set<string>();
  for (const raw of value.statements) {
    if (!record(raw)) throw new Error("The product details could not be verified.");
    // `product` is the existing claim API's product-identity facet. The other
    // display facets await the Midnight owner's agreed producer mapping.
    const facet = raw.facet === "product" ? "identity" : raw.facet;
    const allowed: readonly string[] = viewer === "owner" ? [...publicScanFacets, ...ownerScanFacets] : publicScanFacets;
    if (typeof facet !== "string" || !allowed.includes(facet)) continue;
    const id = text(raw.claim_id, 100), source = text(raw.source), observedAt = date(raw.observed_at);
    const expiresAt = raw.expires_at === null ? null : date(raw.expires_at);
    if (!id || ids.has(id) || !source || !observedAt ||
        (raw.expires_at !== null && !expiresAt) ||
        !["current", "expired", "revoked"].includes(String(raw.state)) ||
        !["demo", "development", "sandbox", "production"].includes(String(raw.environment)) ||
        !(raw.network === null || ["undeployed", "preview", "preprod", "mainnet"].includes(String(raw.network))))
      throw new Error("The product details could not be verified.");
    ids.add(id);
    const typedFacet = facet as ScanFacet;
    const data = record(raw.value) ? raw.value : {};
    const expired = expiresAt !== null && Date.parse(expiresAt) <= now;
    const current = raw.state === "current" && !expired;
    const lines = current ? typedFacet === "price" ? priceLines(data) : fields[typedFacet].flatMap(([key, label]) => {
      const entry = text(data[key], key === "summary" ? 1200 : 240);
      return entry ? [{ label, text: entry }] : [];
    }) : [];
    claims.push({
      id, facet: typedFacet, lines,
      statement: typeof raw.statement === "string" && Object.prototype.hasOwnProperty.call(statementLabels, raw.statement)
        ? statementLabels[raw.statement] : "Product statement",
      source, observedAt, expiresAt,
      state: raw.state === "revoked" ? "revoked" : raw.state === "expired" || expired ? "expired" : "current",
      environment: raw.environment as ScanClaim["environment"], network: raw.network as ScanClaim["network"],
    });
  }
  return { assetId, viewer, claims };
}

/** Expiry also applies to a projection already on screen; never retain stale values. */
export function expireScanClaims(result: ScanClaims, now = Date.now()): ScanClaims {
  return { ...result, claims: result.claims.map(claim =>
    claim.state === "current" && claim.expiresAt !== null && Date.parse(claim.expiresAt) <= now
      ? { ...claim, state: "expired", lines: [] } : claim) };
}
