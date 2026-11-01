# Stripe Connect integration plan

> **Status (2026-11-01).**
> - **Flow 1 (brands, direct charges): built in test mode, verified only against the fixture
>   stand-in and a loopback wire recorder. Not yet run against Stripe test mode.**
>   Code: `brandme_core/domains/providers/payments/stripe_connect.py`, plus the connected-account
>   routing in `stripe_test.py` / `stripe_wire.py` and the startup config in
>   `brandme_core/domains/commerce/composition.py`. Tests: `tests/test_providers_stripe_connect.py`;
>   the purchase suite also runs on a connected-account rail (`tests/test_commerce_payments_flow.py`,
>   `stripe_connect`).
> - **Flow 2 (member resale): not implemented.**
> - Not built yet for Flow 1: a console/gateway route that serves Account Sessions to the brand's
>   browser; handling of Accounts v2 thin events (readiness is re-read before every authorization
>   instead); and a live-suite run with a real test connected account.
>
> This plan follows the Stripe plugin's Connect guidance (`connect-recommend`, `stripe-best-practices`).
> Stripe's MCP `stripe_implementation_planner` was not reachable. Request fields were checked
> against the pinned SDK (`stripe==16.0.0`, API `2026-09-30.endive`), not against live Stripe.

Founder inputs: Connect is used for **two separate flows**: (1) brands and ateliers selling
to members, and (2) member-to-member resale. The platform fee is **5–15%**.

---

## Flow 1 — Brands and ateliers (SaaS platform, direct charges)

### A. Account configuration
- Accounts API: `/v2/core/accounts` (legacy account `type` is not used)
- Dashboard: full Stripe Dashboard, independent access (`dashboard: "full"`)
- Fee collection: Stripe bills connected accounts (`fees_collector: "stripe"`)
- Negative balance liability: Stripe (`losses_collector: "stripe"`)

Brands and ateliers are established businesses. They sell under their own name and handle
their own refunds and disputes. They need their own Stripe Dashboard to run day-to-day
operations, so Stripe bills them for processing directly and holds negative balance liability.

Each connected account needs the merchant configuration (`configuration.merchant`) with
`card_payments` requested.

### B. Charge pattern: direct charges
The brand is the merchant of record: its name appears on the member's statement and it handles
refunds and disputes. This keeps the existing rule in `brandme_core/domains/providers/merchant.py:138`
("Brand.Me is never the payee"). Brand.Me's revenue is an `application_fee_amount` on each
PaymentIntent created on the connected account (`Stripe-Account` header).

### C. Brand onboarding flow
Onboarding method: **embedded** (`account_onboarding` component in the merchant console).
With embedded onboarding the brand never leaves Brand.Me's console, and the
`notification_banner` component handles requirements that come up later without a redirect loop.

Flow: the operator approves the brand in `brandme-console`. Then: create a v2 account
(merchant config) → embedded onboarding → Stripe verifies → read capability status → enable
the brand's catalog for checkout only once `card_payments` is `active` → keep the banner
mounted so new requirements are surfaced → re-check status before every authorization.

### D. Dashboard access
Brands log in directly at `dashboard.stripe.com`. Embedded components cover workflows inside
Brand.Me.

### H. Fee structure
- Platform fee model: percentage (5–15%, configurable per merchant agreement)
- `application_fee_amount` strategy: **platform fee only** (`platform_fee_only`). The brand pays
  Stripe's processing fee directly because fee collection is set to Stripe, so the low-margin
  concern does not apply to this flow.

```
 Member pays $100
       │
       ▼
 ┌──────────────────┐
 │ Brand (connected │ ── pays Stripe processing fee directly
 │ account, MoR)    │ ── keeps $100 − X% − Stripe fee
 └──────┬───────────┘
        │ application fee X%
        ▼
 ┌──────────────────┐
 │ Brand.Me         │ ── receives X%
 └──────────────────┘
```
Rates: [stripe.com/pricing](https://stripe.com/pricing).

### I. SaaS monetization
Transaction fees only, through `application_fee_amount`. Do not also configure the Platform
Pricing Tool; the two are mutually exclusive. If Brand.Me later charges brands a subscription,
bill the connected account through its v2 customer configuration (`customer_account`). Do not
create a v1 Customer for it.

### K. Risk and liability
- **Negative balance liability:** Stripe. `losses_collector: "stripe"` enables Stripe's Managed Risk product.
- **Risk management:** enable **Radar for Platforms**. Managed Risk assumes Radar is active.

---

## Flow 2 — Member-to-member resale (marketplace, separate charges and transfers)

### A. Account configuration
- Accounts API: `/v2/core/accounts` (legacy account `type` is not used)
- Dashboard: Express, a lightweight view for sellers (`dashboard: "express"`)
- Fee collection: your platform manages pricing (`fees_collector: "application"`)
- Negative balance liability: your platform (`losses_collector: "application"`)

Sellers are individual members, not businesses. They need a light way to get paid, not a full
merchant dashboard. Brand.Me runs the resale checkout, so it owns pricing and negative balance
liability.

Each connected account needs the recipient configuration (`configuration.recipient`) with
`stripe_transfers` on `stripe_balance` requested, so the account can receive transfers from
the platform. Do **not** request the merchant configuration or `card_payments` for these
accounts: it is unnecessary and lengthens onboarding.

### B. Charge pattern: separate charges and transfers
Brand.Me's resale promise is that the garment is authenticated before the seller is paid. That
calls for holding funds until release (a delivery-gated and authentication-gated payout).
Destination charges transfer funds as soon as the payment succeeds, and a manual-capture
authorization expires long before a ship-and-authenticate cycle finishes. So: charge on the
platform, then create a `Transfer` to the seller once authentication passes, linked to the
charge with `source_transaction`. If one cart ever contains several sellers' items, the same
pattern still works.

> If authentication is **not** a gate on payout, switch this flow to **destination charges**
> with `application_fee_amount`. Everything else in this section stays the same. This choice
> is open question 1.

### C. Seller onboarding flow
Onboarding method: **embedded**, inside the member app, and only started when a member first
lists an item. Your privacy rules say not to collect data until a feature needs it
(`docs/design/brandme/01-product-experience.md:105`), so KYC belongs to listing, not to sign-up.

Flow: member lists an item → create a v2 account (recipient config) → embedded onboarding →
Stripe verifies → the listing goes live only once `stripe_transfers` is `active` → keep
`notification_banner` mounted → re-check status before every transfer.

### D. Dashboard access
Sellers reach the Express dashboard through login links that Brand.Me generates. In-app
earnings are shown with embedded components.

### H. Fee structure
- Platform fee model: percentage (5–15%)
- **`application_fee_amount` is not used.** It is incompatible with separate charges and
  transfers. Brand.Me keeps its fee by transferring less than it charged.
- **Margin warning:** in this flow Brand.Me pays Stripe's processing fee on every charge, and
  any refund or dispute fees. At the 5% end, the net margin can be thin. For example, if
  processing cost about 3% (an assumption; check your region), a 5% fee leaves about 2% before
  disputes. To keep margin, set the transfer to `charge − platform fee − estimated Stripe fee`.
  Track the [margin report](https://docs.stripe.com/connect/margin-reports.md).

```
 Buyer pays $100
       │
       ▼
 ┌──────────────────┐
 │ Brand.Me (MoR)   │ ── pays Stripe processing fee; holds funds
 └──────┬───────────┘
        │ after authentication passes:
        │ transfer $100 − X% (− est. Stripe fee if passed through)
        ▼
 ┌──────────────────┐
 │ Seller (member)  │ ── receives transfer, pays out to bank
 └──────────────────┘
```
Rates: [stripe.com/pricing](https://stripe.com/pricing).

### K. Risk and liability
- **Negative balance liability:** your platform. When a buyer disputes a charge, Stripe debits
  Brand.Me's balance. Because Brand.Me holds negative balance liability, it can reverse the
  seller's transfer to recover the funds, and that can push the seller's balance negative.
  Reversal is not automatic: Brand.Me has to call it from its dispute handling.
- **Risk management:** Radar is essential here. Fraud that gets past it comes out of Brand.Me's
  balance. Holding funds until authentication is itself a strong risk control.

---

## Shared sections

### E. Embedded components
Both flows use [Connect embedded components](https://docs.stripe.com/connect/supported-embedded-components.md):
- `account_onboarding`
- `notification_banner`: required in both flows; it keeps accounts enabled as requirements change
- `account_management`
- `payments`: full detail for brands (direct charges); reduced detail for resale sellers
  (separate charges and transfers)
- `payouts`

### F. Webhook integration
Confirm payments with webhooks and verify every signature. Connect events come in on a
**separate Connect webhook endpoint** with its own signing secret. Event-level detail belongs
to the build step.

### G. Onboarding status gating
Read `stripe.v2.core.accounts.retrieve(id)` before enabling payments or transfers:
- Brands: `configuration.merchant.capabilities.card_payments.status == "active"`
  (and `configuration.merchant.capabilities.stripe_balance.payouts.status`)
- Resale sellers: `configuration.recipient.capabilities.stripe_balance.stripe_transfers.status == "active"`
  (and `configuration.recipient.capabilities.stripe_balance.payouts.status`)
- Never use v1 `charges_enabled` / `payouts_enabled`. Do not request `stripe_balance.payouts`
  explicitly; Stripe adds it automatically.

### Running Flow 1 in test mode

Configuration is read only by `commerce/composition.py`:

| Variable | Meaning |
|---|---|
| `BRANDME_COMMERCE_PAYMENTS=stripe_test` | Stripe test-mode rail (demo/development only) |
| `STRIPE_TEST_SECRET_KEY` | `sk_test_…`/`rk_test_…`; a restricted key needs Connect write permission |
| `BRANDME_STRIPE_CONNECT_ACCOUNT` | the brand's test connected account `acct_…`; unset, the platform account stands in |
| `BRANDME_STRIPE_CONNECT_FEE_BPS` | Brand.Me's fee in basis points (default 1000 = 10%) |
| `STRIPE_TEST_CONNECT_WEBHOOK_SECRET[_PREVIOUS]` | the Connect webhook endpoint's `whsec_…` |

The account is created with `StripeConnectAccounts.create_brand_account` and onboarded through
`onboarding_link` (Stripe-hosted) or `component_session` (embedded). Authorizations are refused
with `connected_account_not_ready` until `card_payments` is `active`, and with
`connected_account_misconfigured` if the dashboard or responsibilities differ from §A.

### J. Implementation plan (mapped to this repo)
1. **Account setup.** Add v2 account create/retrieve to `StripeWire`, keeping the existing
   allowlisted-field approach. Store a `connected_account_ref` per merchant and per selling
   member in Spanner. Do not use the account id as `payee_ref` directly; map it through a
   reference, matching how the repo handles other ids.
2. **Onboarding.** A gateway route that issues Account Session client secrets for the
   embedded components. Console onboarding for brands; in-app onboarding for members at first
   listing.
3. **Funds flow.**
   - Brands: extend `stripe_test.py` authorize/capture/void/refund to accept a
     `stripe_account` and `application_fee_amount`. The `ComposedMerchantAdapter.payee_ref`
     binding (`merchant.py:137-139, 324-325`) already prevents paying an unapproved payee;
     bind it to the connected account.
   - Resale: a new processor that charges on the platform and records a pending transfer.
     A transfer is released only after an authentication-pass event, with an idempotency
     key and `source_transaction`. Transfer reversal goes into the dispute path
     (`dispute_records`, PLAN §6).
4. **Webhooks and gating.** Add a Connect endpoint and secret (rotation the same as
   `STRIPE_TEST_WEBHOOK_SECRET[_PREVIOUS]`). Add account and capability events to the handled
   set. Check capability status before authorization and before transfers.
5. **Go-live checks.** Stay test-mode only: the `require_test_secret_key` guard stays as it
   is. Live mode needs the PLAN §7 "real money / KYC" decision reopened.

### L. Why this fits
- Brands keep their own customer relationship, so they are merchant of record. That
  preserves the "Brand.Me is never the payee" rule for retail.
- For resale, Brand.Me is the trust layer and authentication is the product, so it holds the
  funds and releases them once the garment is authenticated.
- Each population gets its own account configuration: full Dashboard for businesses, Express
  for individuals.

### M. Open questions
1. ~~Is authentication a gate on resale payout?~~ **Decided 2026-11-01: yes.** Resale uses
   separate charges and transfers, and the payout is released after authentication.
2. **Invariant change:** the resale flow makes Brand.Me the payee and merchant of record. That
   needs a written amendment to the `merchant.py:138` rule, limited to resale.
3. **KYC scope:** PLAN §7 says "no KYC/AML until after Phase 6". Connect onboarding is KYC.
   Test mode only until that decision is reopened?
4. **Countries:** in which countries are the platform, the brands and the resale sellers?
   Separate charges and transfers across regions is restricted.
5. **Dashboard choice is permanent per account.** Confirm full Dashboard for brands before the
   first brand is onboarded. Small ateliers that don't want a full Dashboard would need the
   Express direct-charge setup, which is in public preview.
