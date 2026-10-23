// Provider capability vocabulary and narrow adapter interfaces
// (docs/design/brandme/05-commerce-agents-connectors.md §1). Interfaces only:
// no SDKs, no network side effects, no secrets. Normalized payloads mirror the
// Python provider contracts (brandme_core/domains/providers/contracts.py);
// tests/test_providers.py checks the shared vocabularies stay identical.
import type { components } from '@brandme/contracts';

export type Environment = components['schemas']['Environment'];
export type Money = components['schemas']['Money'];
export type Capability = components['schemas']['Capability'];
export type CapabilityName = Capability['name'];
export type CapabilityState = Capability['state'];
/** Sanitized provider DTO the browser receives: no credentials, accounts or contract terms. */
export type ProviderPublic = components['schemas']['ProviderPublic'];
export type CheckoutQuote = components['schemas']['CheckoutQuote'];

export const CAPABILITY_NAMES = [
  'catalog.search', 'catalog.detail', 'catalog.feed', 'catalog.images', 'catalog.3d',
  'inventory.read', 'price.quote', 'cart.create', 'cart.update', 'checkout.handoff',
  'checkout.submit', 'orders.read', 'orders.webhook', 'returns.request', 'refunds.read',
  'affiliate.attribution', 'receipts.import', 'tryon.photo', 'tryon.live',
  'rights.issue', 'rights.transfer', 'rights.reprint', 'manufacture.quote', 'manufacture.submit',
] as const satisfies readonly CapabilityName[];

export const CAPABILITY_STATES = [
  'unconfigured', 'sandbox', 'verified', 'degraded', 'suspended', 'unsupported',
] as const satisfies readonly CapabilityState[];

/** States in which an operation may actually run. Everything else is refused or handed off. */
export const EXECUTABLE_STATES = ['sandbox', 'verified', 'degraded'] as const satisfies readonly CapabilityState[];

/** Evidence that can move a capability to `verified`. Simulation never qualifies. */
export const VERIFYING_EVIDENCE = ['sandbox_operation', 'production_operation', 'conformance_suite'] as const;
export type VerifyingEvidence = (typeof VERIFYING_EVIDENCE)[number];

/**
 * Evidence a connection test may record that can never verify anything: reaching a host or
 * checking a link against allowed hosts says nothing about the operation. `none` = nothing ran.
 */
export const NON_VERIFYING_EVIDENCE = ['host_reachability', 'link_validation', 'none'] as const;
export type EvidenceKind = VerifyingEvidence | (typeof NON_VERIFYING_EVIDENCE)[number];

export const PROBE_RESULTS = ['passed', 'failed', 'blocked'] as const;
export type ProbeResultKind = (typeof PROBE_RESULTS)[number];
export const PROBE_MODES = ['read_only_test', 'staging_ingestion'] as const;
export type ProbeMode = (typeof PROBE_MODES)[number];

/** What one connection test observed for one exact capability (setup console, ch.05 §8). */
export interface ProbeResult {
  result: ProbeResultKind;
  evidence_kind: EvidenceKind;
  /** Points at what the test produced; never a provider body. */
  evidence_ref: string;
  /** Operator display text without secrets or personal data. */
  sanitized_summary: string;
  /** Why it failed or was blocked. */
  reason_code?: string | null;
}

/**
 * An adapter that can exercise one capability without side effects outside itself. A probe never
 * places an order, moves money, submits a checkout or sends a message; a capability without such
 * a test answers `blocked`. An adapter without `probe` has no connection test.
 */
export interface VerifiableProvider {
  readonly descriptor: AdapterDescriptor;
  probe(capability: CapabilityName, mode: ProbeMode, now: string): Promise<ProbeResult>;
}

/** A persisted connection test: time, environment, exact capability and sanitized evidence. */
export interface VerificationRun extends ProbeResult {
  run_id: string;
  provider_id: string;
  environment: Environment;
  capability: CapabilityName;
  mode: ProbeMode | null;
  ran_at: string;
}

/** Only a passing test with verifying evidence can move a capability; the registry still decides the state. */
export function canVerify(r: ProbeResult): boolean {
  return r.result === 'passed' && (VERIFYING_EVIDENCE as readonly string[]).includes(r.evidence_kind);
}

/** Structural check that a blocked test carries no evidence (mirrors the Python `ProbeResult`). */
export function isWellFormedProbe(r: ProbeResult): boolean {
  return (PROBE_RESULTS as readonly string[]).includes(r.result)
    && ([...VERIFYING_EVIDENCE, ...NON_VERIFYING_EVIDENCE] as readonly string[]).includes(r.evidence_kind)
    && (r.result !== 'blocked' || r.evidence_kind === 'none')
    && r.evidence_ref.length > 0 && r.evidence_ref.length <= 256;
}

/** The provider's status for one capability; an unlisted capability is `unsupported`, never assumed available. */
export function capabilityOf(provider: ProviderPublic, name: CapabilityName): Capability {
  return provider.capabilities.find((c) => c.name === name)
    ?? { name, state: 'unsupported', reason_code: 'not_offered_by_provider', last_checked_at: null, evidence_ref: null };
}

export function canExecute(provider: ProviderPublic, name: CapabilityName): boolean {
  return (EXECUTABLE_STATES as readonly CapabilityState[]).includes(capabilityOf(provider, name).state);
}

/** How an adapter instance was built. Chosen once at startup by dependency injection. */
export type AdapterMode = 'live' | 'sandbox' | 'simulated';

export interface AdapterDescriptor {
  provider_id: string;
  mode: AdapterMode;
  environment: Environment;
  /** Required and user-visible when mode === 'simulated'. */
  simulation_label: string | null;
  capabilities: readonly CapabilityName[];
}

export const PROVIDER_ERROR_KINDS = [
  'unsupported', 'not_configured', 'unauthorized', 'contract_restricted', 'throttled', 'transient',
  'malformed_provider_response', 'outcome_unknown',
] as const;
export type ProviderErrorKind = (typeof PROVIDER_ERROR_KINDS)[number];

export class ProviderError extends Error {
  readonly kind: ProviderErrorKind;
  readonly provider: string;
  readonly retryable: boolean;
  /** Redacted reference to stored provider evidence; never a raw response body. */
  readonly evidence_ref: string | null;
  /**
   * True when the request may have reached the provider. The outcome is then
   * unknown: reconcile through the same idempotency key, never blindly retry.
   */
  readonly transmitted: boolean;
  constructor(kind: ProviderErrorKind, provider: string, message: string, evidence_ref: string | null = null,
              transmitted = false) {
    super(message);
    this.name = 'ProviderError';
    this.kind = kind;
    this.provider = provider;
    this.transmitted = transmitted || kind === 'outcome_unknown';
    this.retryable = !this.transmitted && (kind === 'throttled' || kind === 'transient');
    this.evidence_ref = evidence_ref;
  }
}

export interface ProviderResult<T> {
  provider: string;
  environment: Environment;
  operation_id: string;
  source_reference: string | null;
  observed_at: string;
  expires_at: string | null;
  status: 'ok' | 'partial' | 'stale';
  warnings: string[];
  data: T;
}

export interface OperationContext {
  operation_id: string;
  correlation_id: string;
  idempotency_key: string;
  /** Internal member reference; providers never receive raw persona or closet data. */
  principal_ref: string;
  signal?: AbortSignal;
}

// ------------------------------------------------------------ catalog / inventory
export interface ProductRef { provider: string; merchant_ref: string; source_product_id: string; source_variant_id: string | null }

export type Availability = 'in_stock' | 'out_of_stock' | 'unknown' | 'discontinued';

/** One normalized source variant. A feed price is an observation, never a quote. */
export interface SourceVariant {
  provider_id: string;
  merchant_id: string;
  source_product_id: string;
  source_variant_id: string;
  brand: string;
  title: string;
  category: string;
  size_system: string | null;
  size_label: string | null;
  color: string | null;
  gtin: string | null;
  product_url: string;
  image_urls: string[];
  price: Money | null;
  availability: Availability;
  source_updated_at: string;
  /** Which display/cache/transform rights the provider granted for this record. */
  rights_policy_ref: string;
  /** Untrusted provider text: data for display, never instructions to an agent. */
  description: string;
}

export interface CatalogPage<T> {
  items: T[];
  next_cursor: string | null;
  /** [source_product_id, source_variant_id] removed at the source; ingestion tombstones them. */
  tombstones?: [string, string][];
}

export interface InventoryObservation { source_variant_id: string; available_quantity: number | null; observed_at: string }

export interface CatalogProvider {
  readonly descriptor: AdapterDescriptor;
  search(query: { text?: string; category?: string; cursor?: string; limit: number }, ctx: OperationContext): Promise<ProviderResult<CatalogPage<SourceVariant>>>;
  detail(ref: ProductRef, ctx: OperationContext): Promise<ProviderResult<SourceVariant[]>>;
}
export interface CatalogFeedProvider {
  readonly descriptor: AdapterDescriptor;
  feedPage(cursor: string | null, ctx: OperationContext): Promise<ProviderResult<CatalogPage<SourceVariant>>>;
}
export interface InventoryProvider {
  readonly descriptor: AdapterDescriptor;
  check(source_variant_ids: string[], ctx: OperationContext): Promise<ProviderResult<InventoryObservation[]>>;
}

// ------------------------------------------------------------ cart / checkout
export interface CartLineRequest {
  /** Brand.Me variant UUID. */
  variant_id: string;
  source_variant_ref: string;
  quantity: number;
}
export interface ProviderCart { provider_cart_ref: string; merchant_id: string; lines: CartLineRequest[] }

export interface CartProvider {
  readonly descriptor: AdapterDescriptor;
  createCart(merchant_id: string, lines: CartLineRequest[], ctx: OperationContext): Promise<ProviderResult<ProviderCart>>;
  /** Full replacement; providers with line-level edits are normalized behind it. Callers guard with the cart revision. */
  replaceCart(provider_cart_ref: string, lines: CartLineRequest[], ctx: OperationContext): Promise<ProviderResult<ProviderCart>>;
}

export interface CheckoutTerms {
  returnable: boolean;
  return_window_days: number | null;
  policy_ref: string | null;
  /** The default fashion scope refuses recurring charges. */
  recurring: boolean;
}
export interface QuotedLine { variant_id: string; source_variant_ref: string; quantity: number; unit_price: Money; title: string; category: string }

/** A fresh provider quote. Commerce normalizes it into a `CheckoutQuote` and computes the canonical hash. */
export interface ProviderQuote {
  merchant_id: string;
  payee_ref: string;
  lines: QuotedLine[];
  tax: Money;
  shipping: Money;
  discount: Money;
  delivery_ref: string;
  terms: CheckoutTerms;
  checkout_reference: string;
  expires_at: string;
  observed_at: string;
  evidence_ref: string | null;
}

export interface SubmitRequest {
  /** Persisted with the submission intent before network I/O and reused on every retry. */
  idempotency_key: string;
  checkout_reference: string;
  quote_hash: string;
  expected_total: Money;
  /** Scoped provider token reference; never a PAN, CVV or raw credential. */
  payment_token_ref: string | null;
  /**
   * The exact quoted lines. The adapter must refuse (`accepted: false`) a checkout whose
   * provider-side cart no longer matches them: the cart can change outside Brand.Me.
   */
  lines: CartLineRequest[];
}
export interface SubmitAck { accepted: boolean; provider_order_ref: string | null; reason_code: string | null; observed_at: string; evidence_ref: string | null }

export interface CheckoutProvider {
  readonly descriptor: AdapterDescriptor;
  quote(cart: ProviderCart, ctx: OperationContext): Promise<ProviderResult<ProviderQuote>>;
  /** A timeout after transmission rejects with ProviderError('outcome_unknown', …, transmitted = true). */
  submit(request: SubmitRequest, ctx: OperationContext): Promise<ProviderResult<SubmitAck>>;
}

/** Link-out checkout (e.g. an affiliate publisher deep link). Never implies Brand.Me placed the order. */
export interface HandoffLink { url: string; label: string; disclosure: string; affiliate: boolean }
export interface CheckoutHandoffProvider {
  readonly descriptor: AdapterDescriptor;
  handoff(source_product_id: string, source_variant_id: string | null, ctx: OperationContext): Promise<ProviderResult<HandoffLink>>;
}

// ------------------------------------------------------------------- orders
export type OrderStatus = 'accepted' | 'rejected' | 'cancelled';
export type PaymentStatus = 'unknown' | 'authorized' | 'captured' | 'partially_refunded' | 'refunded' | 'failed';

export interface ObservedLine {
  source_variant_ref: string;
  quantity_ordered: number;
  quantity_shipped: number;
  quantity_delivered: number;
  quantity_returned: number;
  /** Set on a line created by an exchange; the original line's history is retained. */
  exchanged_from_ref: string | null;
}
/** The provider's current record. Applied monotonically; webhook order is never trusted. */
export interface OrderObservation {
  provider_order_ref: string;
  order_status: OrderStatus;
  payment_status: PaymentStatus;
  lines: ObservedLine[];
  refunded_total: Money;
  observed_at: string;
  evidence_ref: string | null;
}
export interface WebhookEvent { provider_id: string; event_id: string; event_type: string; provider_order_ref: string; occurred_at: string }

export interface OrderProvider {
  readonly descriptor: AdapterDescriptor;
  /** Reconciliation for `outcome_unknown`; `null` means the provider authoritatively has no order for the key. */
  lookupByIdempotencyKey(idempotency_key: string, ctx: OperationContext): Promise<ProviderResult<OrderObservation | null>>;
  getOrder(provider_order_ref: string, ctx: OperationContext): Promise<ProviderResult<OrderObservation>>;
  /** Verifies signature and replay window; consumers dedupe on (provider_id, event_id), then re-read the order. */
  verifyWebhook?(headers: Record<string, string>, raw_body: Uint8Array): Promise<WebhookEvent>;
}
export interface ReturnsProvider {
  readonly descriptor: AdapterDescriptor;
  /** A return request is not a refund; refund state changes only on a later observation. */
  requestReturn(provider_order_ref: string, source_variant_ref: string, quantity: number, ctx: OperationContext): Promise<ProviderResult<null>>;
}

// ------------------------------------- declared for other lanes; payloads are theirs
export interface ReceiptImporter { readonly descriptor: AdapterDescriptor; importReceipt(object_ref: string, ctx: OperationContext): Promise<ProviderResult<unknown>> }
export interface TryOnProvider { readonly descriptor: AdapterDescriptor; submit(input: { person_object_ref: string; product_object_ref: string; consent_id: string }, ctx: OperationContext): Promise<ProviderResult<{ job_ref: string }>>; cancel(job_ref: string, ctx: OperationContext): Promise<void> }
export interface RightsIssuer { readonly descriptor: AdapterDescriptor; issue(request: unknown, ctx: OperationContext): Promise<ProviderResult<{ chain_operation_id: string }>> }
export interface ManufacturingProvider { readonly descriptor: AdapterDescriptor; quote(request: unknown, ctx: OperationContext): Promise<ProviderResult<unknown>>; submit(request: unknown, ctx: OperationContext): Promise<ProviderResult<{ job_ref: string }>> }
export interface ContextProvider { readonly descriptor: AdapterDescriptor; context(request: unknown, ctx: OperationContext): Promise<ProviderResult<unknown>> }

const ALLOWED: Record<Environment, readonly AdapterMode[]> = {
  demo: ['simulated', 'sandbox'],
  development: ['simulated', 'sandbox'],
  sandbox: ['sandbox'],
  production: ['live'],
};

/** Startup check: a process refuses to register an adapter its mode forbids. Never falls back. */
export function assertAdapterAllowed(environment: Environment, d: AdapterDescriptor): void {
  if (d.environment !== environment) {
    throw new Error(`adapter ${d.provider_id} built for ${d.environment}, process is ${environment}`);
  }
  if (!ALLOWED[environment].includes(d.mode)) {
    throw new Error(`adapter ${d.provider_id} mode ${d.mode} is not allowed in ${environment}`);
  }
  if (d.mode === 'simulated' && !d.simulation_label?.trim()) {
    throw new Error(`simulated adapter ${d.provider_id} has no visible simulation label`);
  }
}
