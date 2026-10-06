// Provider capability vocabulary and narrow adapter interfaces
// (docs/design/brandme/05-commerce-agents-connectors.md §1). Interfaces only:
// no SDKs, no network side effects, no secrets. Lane 3 (commerce/providers)
// extends these after the foundation merge.
import type { components } from '@brandme/contracts';

export type Environment = components['schemas']['Environment'];
export type Money = components['schemas']['Money'];
export type CapabilityName = components['schemas']['Capability']['name'];
export type CapabilityState = components['schemas']['Capability']['state'];

export const CAPABILITY_NAMES = [
  'catalog.search', 'catalog.detail', 'catalog.feed', 'catalog.images', 'catalog.3d',
  'inventory.read', 'price.quote', 'cart.create', 'cart.update', 'checkout.handoff',
  'checkout.submit', 'orders.read', 'orders.webhook', 'returns.request', 'refunds.read',
  'affiliate.attribution', 'receipts.import', 'tryon.photo', 'tryon.live',
  'rights.issue', 'rights.transfer', 'rights.reprint', 'manufacture.quote', 'manufacture.submit',
] as const satisfies readonly CapabilityName[];

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

export type ProviderErrorKind =
  | 'unsupported'
  | 'not_configured'
  | 'unauthorized'
  | 'contract_restricted'
  | 'throttled'
  | 'transient'
  | 'malformed_provider_response'
  | 'outcome_unknown';

export class ProviderError extends Error {
  readonly kind: ProviderErrorKind;
  readonly provider: string;
  readonly retryable: boolean;
  /** Redacted reference to stored provider evidence; never a raw response body. */
  readonly evidence_ref: string | null;
  constructor(kind: ProviderErrorKind, provider: string, message: string, evidence_ref: string | null = null) {
    super(message);
    this.name = 'ProviderError';
    this.kind = kind;
    this.provider = provider;
    this.retryable = kind === 'throttled' || kind === 'transient';
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

// Normalized payloads are deliberately minimal here; owning lanes refine them.
export interface ProductRef { provider: string; merchant_ref: string; source_product_id: string; source_variant_id: string | null }
export interface CatalogPage<T> { items: T[]; next_cursor: string | null }

export interface CatalogProvider {
  readonly descriptor: AdapterDescriptor;
  search(query: { text?: string; category?: string; cursor?: string; limit: number }, ctx: OperationContext): Promise<ProviderResult<CatalogPage<ProductRef>>>;
  detail(ref: ProductRef, ctx: OperationContext): Promise<ProviderResult<unknown>>;
}
export interface InventoryProvider {
  readonly descriptor: AdapterDescriptor;
  availability(ref: ProductRef, ctx: OperationContext): Promise<ProviderResult<{ available: boolean; checked_at: string }>>;
}
export interface CartProvider {
  readonly descriptor: AdapterDescriptor;
  createCart(lines: { ref: ProductRef; quantity: number }[], ctx: OperationContext): Promise<ProviderResult<{ provider_cart_ref: string; revision: string }>>;
  replaceCart(provider_cart_ref: string, expected_revision: string, lines: { ref: ProductRef; quantity: number }[], ctx: OperationContext): Promise<ProviderResult<{ revision: string }>>;
}
export interface CheckoutProvider {
  readonly descriptor: AdapterDescriptor;
  quote(provider_cart_ref: string, ctx: OperationContext): Promise<ProviderResult<components['schemas']['CheckoutQuote']>>;
  /** Must persist intent before I/O; a timeout after transmission is ProviderError('outcome_unknown'). */
  submit(quote_hash: string, approval_ref: string, ctx: OperationContext): Promise<ProviderResult<{ provider_order_ref: string }>>;
  handoffUrl?(provider_cart_ref: string, ctx: OperationContext): Promise<ProviderResult<{ continue_url: string }>>;
}
export interface OrderProvider {
  readonly descriptor: AdapterDescriptor;
  getOrder(provider_order_ref: string, ctx: OperationContext): Promise<ProviderResult<unknown>>;
  verifyWebhook?(headers: Record<string, string>, raw_body: Uint8Array): Promise<{ event_id: string; occurred_at: string; payload: unknown }>;
}
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
