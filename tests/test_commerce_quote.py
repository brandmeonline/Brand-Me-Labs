"""Money arithmetic and canonical quote binding (contracts invariants 6–7; BM-COM-004/005)."""

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jsonschema
import pytest

from brandme_core.domains.commerce.errors import InvalidQuote, QuoteExpired
from brandme_core.domains.commerce.money import Money, MoneyError
from brandme_core.domains.commerce.quote import CheckoutQuote, CheckoutTerms, QuoteLine, material_diff

SPEC = Path(__file__).resolve().parents[1] / "docs/design/brandme/contracts"
T0 = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
USD = lambda n: Money(n, "USD")


def quote(**kw) -> CheckoutQuote:
    base = dict(
        id="f36cb317-ec35-5a15-afe4-d8fd7c888384", environment="demo", provider_id="demo_atelier",
        merchant_id="fictional-demo-merchant", payee_ref="demo-payee",
        cart_id="f90f1d6a-86ab-5cc7-847d-fe363d6cc105", cart_revision=2,
        lines=(QuoteLine("c70ea8fb-78db-593b-9c3c-824ef1412393", "demo-overshirt-m", 1, USD(8900), USD(8900),
                         "Field Linen Overshirt — fictional demo", "top"),),
        subtotal=USD(8900), tax=USD(712), shipping=USD(0), discount=USD(0), total=USD(9612),
        delivery_ref="demo-delivery", terms=CheckoutTerms(True, 30, "demo-returns-v1"),
        checkout_reference="demo-checkout-1", issued_at=T0, expires_at=T0 + timedelta(minutes=5))
    base.update(kw)
    return CheckoutQuote(**base).seal()


class TestMoney:
    def test_rejects_float_and_negative_and_unknown_currency(self):
        with pytest.raises(MoneyError):
            Money.from_wire({"amount_minor": 96.12, "currency": "USD"})
        with pytest.raises(MoneyError):
            Money.from_wire({"amount_minor": "-1", "currency": "USD"})
        with pytest.raises(MoneyError):
            Money(100, "XXX")
        with pytest.raises(MoneyError):
            Money.from_wire({"amount_minor": "01", "currency": "USD"})

    def test_no_implicit_fx(self):
        with pytest.raises(MoneyError):
            Money(1, "USD") + Money(1, "EUR")

    def test_exponent_aware_display(self):
        assert Money(9612, "USD").display() == "96.12 USD"
        assert Money(9612, "JPY").display() == "9612 JPY"
        assert Money(1500, "KWD").display() == "1.500 KWD"


class TestQuoteHash:
    def test_contract_example_arithmetic_and_schema(self):
        q = quote()
        schema = json.loads((SPEC / "domain.schema.json").read_text())
        validator = jsonschema.Draft202012Validator(
            {"$ref": "#/$defs/CheckoutQuote", "$defs": schema["$defs"]},
            format_checker=jsonschema.FormatChecker())
        validator.validate(q.to_wire())
        assert q.total == USD(9612)
        assert q.quote_hash.startswith("sha256:") and len(q.quote_hash) == 71

    def test_hash_is_deterministic_and_line_order_independent(self):
        l1 = QuoteLine("00000000-0000-4000-8000-000000000001", "a", 1, USD(100), USD(100))
        l2 = QuoteLine("00000000-0000-4000-8000-000000000002", "b", 2, USD(50), USD(100))
        q1 = quote(lines=(l1, l2), subtotal=USD(200), tax=USD(0), total=USD(200))
        q2 = quote(lines=(l2, l1), subtotal=USD(200), tax=USD(0), total=USD(200))
        assert q1.quote_hash == q2.quote_hash

    @pytest.mark.parametrize("change", [
        dict(merchant_id="other-merchant"), dict(payee_ref="other-payee"), dict(cart_revision=3),
        dict(delivery_ref="express"), dict(checkout_reference="demo-checkout-2"),
        dict(expires_at=T0 + timedelta(minutes=6)), dict(environment="sandbox"),
        dict(terms=CheckoutTerms(False, None, "final-sale")),
        dict(shipping=USD(500), total=USD(10112)),
    ])
    def test_every_material_change_changes_hash(self, change):
        assert quote(**change).quote_hash != quote().quote_hash

    def test_price_and_variant_and_quantity_are_material(self):
        base = quote()
        price = quote(lines=(replace(base.lines[0], unit_price=USD(9900), line_total=USD(9900)),),
                      subtotal=USD(9900), total=USD(10612))
        variant = quote(lines=(replace(base.lines[0], source_variant_ref="demo-overshirt-l"),))
        qty = quote(lines=(replace(base.lines[0], quantity=2, line_total=USD(17800)),),
                    subtotal=USD(17800), total=USD(18512))
        for q in (price, variant, qty):
            assert q.quote_hash != base.quote_hash
        assert "total" in material_diff(base, price) and "lines" in material_diff(base, price)

    def test_display_text_is_not_material(self):
        base = quote()
        renamed = quote(lines=(replace(base.lines[0], title="Renamed copy"),))
        assert renamed.quote_hash == base.quote_hash

    def test_tampered_quote_fails_seal(self):
        q = quote()
        tampered = replace(q, total=USD(1), subtotal=USD(1))
        with pytest.raises(InvalidQuote):
            tampered.verify_seal()

    @pytest.mark.parametrize("bad", [
        dict(total=USD(9611)),
        dict(subtotal=USD(8901), total=USD(9613)),
        dict(tax=Money(712, "EUR")),
        dict(expires_at=T0),
        dict(terms=CheckoutTerms(True, 30, recurring=True)),
    ])
    def test_invalid_arithmetic_currency_expiry_recurrence(self, bad):
        with pytest.raises(InvalidQuote):
            quote(**bad)

    def test_expiry(self):
        q = quote()
        q.ensure_fresh(T0 + timedelta(minutes=4))
        with pytest.raises(QuoteExpired):
            q.ensure_fresh(T0 + timedelta(minutes=5))
