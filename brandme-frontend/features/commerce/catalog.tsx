"use client";
import Link from "next/link";
import { useState } from "react";
import { useResource } from "@/lib/client/use-resource";
import { ResourceState } from "@/components/ui/resource-state";
import { Input } from "@/components/ui/field";
import { Button } from "@/components/ui/button";
import { Price } from "@/components/ui/price";
import type { Money } from "@/lib/money";
type ProviderText = { type: "untrusted_text"; origin: string; text: string };
type Item = {
  provider_id: string;
  merchant_id: string;
  source_product_id: string;
  source_variant_ref: string;
  variant_id: string | null;
  title: ProviderText;
  description: ProviderText;
  category: string;
  size_label: string | null;
  availability: string;
  observed_price: Money | null;
  price_freshness: string;
  checked_at: string | null;
  simulation: boolean;
  disclosure: string;
};
type SearchResult = {
  items: Item[];
  unavailable_providers: {
    provider_id: string;
    reason_code: string;
    handoff: string;
  }[];
  note: string;
};
type Product = {
  provider_id: string;
  source_product_id: string;
  simulation: boolean;
  disclosure: string;
  variants: {
    source_variant_ref: string;
    size_label: string | null;
    title: ProviderText;
    availability: string;
    observed_price: Money | null;
  }[];
};
function providerText(value: ProviderText) {
  return typeof value?.text === "string"
    ? value.text
    : "Product details unavailable";
}
export function Discover() {
  const [draft, setDraft] = useState(""),
    [query, setQuery] = useState(""),
    [inStock, setInStock] = useState(false);
  const r = useResource<SearchResult>(
    query ? `/catalog/search?q=${encodeURIComponent(query)}&limit=24` : null,
  );
  const items =
    r.data?.items.filter((i) => !inStock || i.availability === "in_stock") ??
    [];
  return (
    <div className="bm-flow-stack">
      <form
        className="bm-flow-card"
        onSubmit={(event) => {
          event.preventDefault();
          setQuery(draft.trim());
        }}
      >
        <Input
          label="What are you looking for?"
          value={draft}
          required
          maxLength={200}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="A linen jacket, a raincoat, a new direction…"
        />
        <div className="bm-actions">
          <Button type="submit" disabled={!draft.trim()}>
            Search authorized catalogs
          </Button>
          <label className="bm-checkbox-label">
            <input
              type="checkbox"
              checked={inStock}
              onChange={(e) => setInStock(e.target.checked)}
            />
            Show reported in-stock variants
          </label>
        </div>
      </form>
      {query && <ResourceState {...r} retry={r.reload} />}
      {r.data && (
        <>
          <p>{r.data.note}</p>
          <p role="status">
            {items.length} variants shown for “{query}”.
          </p>
          <div className="bm-choice-grid">
            {items.map((item) => (
              <article
                className="bm-flow-card"
                key={`${item.provider_id}:${item.source_variant_ref}`}
              >
                <p className="bm-eyebrow">
                  {item.provider_id}
                  {item.simulation ? " · Simulated provider" : ""}
                </p>
                <h2>
                  <Link
                    href={`/products/${encodeURIComponent(`${item.provider_id}:${item.source_product_id}`)}`}
                  >
                    {providerText(item.title)}
                  </Link>
                </h2>
                <p>{providerText(item.description)}</p>
                <p>
                  {item.size_label ?? "Size not supplied"} ·{" "}
                  {item.availability.replaceAll("_", " ")}
                </p>
                <Price money={item.observed_price} />
                <p className="bm-support">
                  Observed price · {item.price_freshness.replaceAll("_", " ")}
                  {item.checked_at
                    ? ` · checked ${new Date(item.checked_at).toLocaleString()}`
                    : ""}
                </p>
                <p className="bm-support">{item.disclosure}</p>
              </article>
            ))}
          </div>
          {r.data.unavailable_providers.map((provider) => (
            <p key={provider.provider_id} className="bm-notice">
              {provider.provider_id}:{" "}
              {provider.reason_code.replaceAll("_", " ")}. No offers from this
              provider are shown.
            </p>
          ))}
        </>
      )}
      <p className="bm-support">
        Availability and price are provider observations. A purchase requires a
        fresh quote and your review of the full terms.
      </p>
    </div>
  );
}
export function ProductDetail({ id }: { id: string }) {
  const r = useResource<Product>(`/catalog/products/${encodeURIComponent(id)}`);
  return (
    <div className="bm-flow-stack">
      <ResourceState {...r} retry={r.reload} />
      {r.data && (
        <>
          <p>
            {r.data.provider_id}
            {r.data.simulation ? " · Simulated provider" : ""}
          </p>
          <p>{r.data.disclosure}</p>
          <div className="bm-choice-grid">
            {r.data.variants.map((v) => (
              <article key={v.source_variant_ref} className="bm-flow-card">
                <h2>{providerText(v.title)}</h2>
                <p>
                  {v.size_label ?? "Size not supplied"} ·{" "}
                  {v.availability.replaceAll("_", " ")}
                </p>
                <Price money={v.observed_price} />
                <p className="bm-support">
                  Observed price, not a checkout quote.
                </p>
              </article>
            ))}
          </div>
          <p className="bm-notice">
            This catalog supplies variant observations. Saving, trying on and
            checkout become available when this provider supplies the required
            product and capability links.
          </p>
        </>
      )}
      <Link href="/discover">Back to Discover</Link>
    </div>
  );
}
