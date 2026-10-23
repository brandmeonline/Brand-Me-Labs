# @brandme/provider-contracts

Interfaces only (spec ch.05 §1). This package contains no SDKs, no network calls and no secrets.

- **Vocabulary:** the 24 capability names, the capability states, the states in which an operation may run
  (`EXECUTABLE_STATES`), the evidence kinds that can make a capability `verified`, and the `ProviderError` kinds.
  `tests/test_providers.py` checks these lists are identical to the Python contracts in
  `brandme_core/domains/providers/contracts.py`.
- **Provider DTO:** `ProviderPublic` (from `@brandme/contracts`) is the sanitized provider record the browser gets.
  `capabilityOf()` / `canExecute()` treat an unlisted capability as `unsupported`, never as available.
- **Results and errors:** `ProviderResult<T>` and `ProviderError`. A `ProviderError` with `transmitted` set (always the
  case for `outcome_unknown`) is never retryable: it is reconciled through the same idempotency key.
- **Normalized payloads**, mirroring the Python dataclasses:
  - Catalog: `SourceVariant`, `CatalogPage` with tombstones, `InventoryObservation`.
  - Cart and checkout: `CartLineRequest`, `ProviderCart`, `ProviderQuote`, `CheckoutTerms`, `SubmitRequest`,
    `SubmitAck`, `HandoffLink`.
  - Orders: `ObservedLine`, `OrderObservation`, `WebhookEvent`.
  - A feed price is an observation; only commerce turns a `ProviderQuote` into a hashed `CheckoutQuote`.
- **Narrow adapter interfaces:**
  - `CatalogProvider` / `CatalogFeedProvider` / `InventoryProvider`
  - `CartProvider` / `CheckoutProvider` / `CheckoutHandoffProvider`
  - `OrderProvider` / `ReturnsProvider`
  - Declared for other lanes, which own their payloads: `ReceiptImporter`, `TryOnProvider`, `RightsIssuer`,
    `ManufacturingProvider`, `ContextProvider`.

  An adapter implements only what the provider supports. There are no success-shaped no-ops.

`assertAdapterAllowed(environment, descriptor)` is called once at startup when an adapter is registered. Allowed
adapter modes by environment:

| Environment | Allowed modes |
|---|---|
| production | `live` |
| sandbox | `sandbox` |
| demo, development | `simulated` (with a visible `simulation_label`), `sandbox` |

An adapter built for another environment is refused. There is no runtime fallback from live to simulated.

Sole writer: the opus-commerce-agents lane (`docs/build/status/opus-commerce-agents.md`).
