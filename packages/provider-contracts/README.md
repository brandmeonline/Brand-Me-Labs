# @brandme/provider-contracts

Interfaces only (spec ch.05 §1): the 24 capability names, `AdapterDescriptor`, `ProviderResult<T>`, `ProviderError` kinds, and narrow `CatalogProvider` / `InventoryProvider` / `CartProvider` / `CheckoutProvider` / `OrderProvider` / `ReceiptImporter` / `TryOnProvider` / `RightsIssuer` / `ManufacturingProvider` / `ContextProvider` interfaces. This package contains no SDKs, no network calls and no secrets.

`assertAdapterAllowed(environment, descriptor)` is called once at startup when an adapter is registered. Production accepts only `live`; sandbox accepts only `sandbox`; demo/development accept `simulated` (with a visible `simulation_label`) and `sandbox`. An adapter built for another environment is refused. There is no runtime fallback from live to simulated.

The commerce/providers lane extends the normalized payload types after the foundation merge.
