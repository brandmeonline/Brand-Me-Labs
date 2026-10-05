"""Provider registry, Nordstrom gate, ingestion, media rights and URL safety (W06 evidence)."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jsonschema
import pytest

from brandme_core.domains.commerce.money import Money
from brandme_core.domains.providers import nordstrom
from brandme_core.domains.providers.contracts import CatalogPage, ProviderError, ProviderErrorKind, SourceVariant
from brandme_core.domains.providers.ingestion import (
    CatalogIngestor, IngestionAudit, MediaRightsDenied, authorize_media_transform, price_freshness,
)
from brandme_core.domains.providers.registry import (
    CapabilityStatus, ProviderRegistry, RegistryError,
)
from brandme_core.domains.providers.url_guard import (
    RawResponse, SafeFetcher, UnsafeUrl, check_public_url, validate_redirect,
)
from tests.fixtures.commerce.harness import world

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "docs/design/brandme/contracts/domain.schema.json").read_text())
T0 = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)


def _validator(defn):
    return jsonschema.Draft202012Validator({"$ref": f"#/$defs/{defn}", "$defs": SCHEMA["$defs"]},
                                           format_checker=jsonschema.FormatChecker())


# ------------------------------------------------------------------ registry
def test_verified_requires_operation_evidence():
    with pytest.raises(RegistryError):
        CapabilityStatus("checkout.submit", "verified", "ok", T0, None, None)
    with pytest.raises(RegistryError):
        CapabilityStatus("checkout.submit", "verified", "ok", T0, "ping-ok", "host_reachability")
    reg = ProviderRegistry("development")
    reg.register(nordstrom.connection("development"))
    with pytest.raises(RegistryError):
        reg.record_verification("nordstrom_impact", "catalog.feed", evidence_ref="dns-ok",
                                evidence_kind="host_reachability", checked_at=T0)


def test_simulation_never_reaches_verified():
    w = world()
    st = w.registry.record_verification("demo_atelier", "checkout.submit", evidence_ref="run-1",
                                        evidence_kind="production_operation", checked_at=T0)
    assert st.state == "sandbox" and st.reason_code == "deterministic_local_simulation"


def test_public_dto_matches_contract_and_carries_no_secrets():
    setup = nordstrom.NordstromSetup(account_ref="acct-ref-placeholder",
                                     credential_secret_ref="projects/p/secrets/s/versions/1")
    conn = nordstrom.connection("development", setup)
    dto = conn.to_public()
    _validator("ProviderPublic").validate(dto)
    blob = json.dumps(dto)
    assert "acct-ref-placeholder" not in blob and "secrets" not in blob
    w = world()
    _validator("ProviderPublic").validate(w.registry.get("demo_atelier").to_public())


# ----------------------------------------------------------------- nordstrom
def test_nordstrom_unconfigured_shows_gate_and_no_purchase():  # BM-PROV-001/002
    conn = nordstrom.connection("development")
    assert conn.capability("catalog.feed").state == "unconfigured"
    assert conn.capability("catalog.feed").reason_code == "partner_approval_required"
    for cap in ("checkout.submit", "cart.create", "orders.read", "orders.webhook"):
        assert conn.capability(cap).state == "unsupported"
        assert not conn.can_execute(cap)
    missing = nordstrom.NordstromSetup().missing()
    assert {i.section for i in missing} >= {"prerequisites", "credentials", "data_use", "tests", "activation"}
    assert any(nordstrom.OFFICIAL_PROGRAM_URL in i.action for i in missing)
    with pytest.raises(ProviderError) as e:
        conn.adapter.feed_page(None)
    assert e.value.kind is ProviderErrorKind.NOT_CONFIGURED


def test_nordstrom_module_contains_no_guessed_api_endpoint():
    src = (ROOT / "brandme_core/domains/providers/nordstrom.py").read_text()
    assert "api.nordstrom.com" not in src
    assert "/v1/" not in src and "Catalogs/" not in src


def test_partial_setup_never_enables_capability():
    setup = nordstrom.NordstromSetup(program_application_opened=True, account_ref="ref",
                                     credential_secret_ref="projects/p/secrets/s/versions/1")
    conn = nordstrom.connection("development", setup)
    assert not conn.can_execute("catalog.feed") and setup.missing()


def test_link_only_path():
    saved = nordstrom.save_link_only("https://www.nordstrom.com/s/fictional-item/0000000#reviews")
    assert saved.cta.label == "Continue at Nordstrom"
    assert saved.purchase_state == "not_confirmed"
    assert saved.url.endswith("/0000000")
    for bad in ("http://www.nordstrom.com/s/x", "https://nordstrom.com.evil.example/s/x",
                "https://user:pw@www.nordstrom.com/s/x", "javascript:alert(1)", "https://www.nordstrom.com:8443/s/x"):
        with pytest.raises(UnsafeUrl):
            nordstrom.save_link_only(bad)


# ---------------------------------------------------------------- ingestion
def _page(raw, provider="nordstrom_impact"):
    items = tuple(SourceVariant(
        provider_id=provider, merchant_id="fictional-merchant", source_product_id=r["product"],
        source_variant_id=r["variant"], brand="Fictional", title=r["title"], category="outerwear",
        size_system=None, size_label=None, color=None, gtin=None,
        product_url="https://www.nordstrom.com/s/fictional", image_urls=(), price=Money(r["price"], "USD"),
        availability="in_stock", source_updated_at=T0, rights_policy_ref="fictional")
        for r in raw["items"])
    return CatalogPage(items, raw["next"], tuple(tuple(t) for t in raw.get("tombstones", [])))


def test_feed_replay_and_tombstone():  # BM-PROV-004
    feed = json.loads((ROOT / "tests/fixtures/providers/impact_feed_fictional.json").read_text())
    ing = CatalogIngestor()
    for _ in range(3):  # replay the full cursor range
        audit = IngestionAudit("run", "nordstrom_impact")
        for raw in feed["pages"]:
            ing.ingest_page(_page(raw), provider_id="nordstrom_impact", now=T0, audit=audit)
    assert len(ing.variants) == 3
    offers = {v.source_variant_id for v in ing.offers("nordstrom_impact")}
    assert offers == {"fx-100-m", "fx-200-one"}  # deleted variant no longer offered
    assert audit.accepted == 0 and audit.tombstoned == 0  # third replay changed nothing


def test_stale_feed_price_is_labeled_not_a_quote():  # BM-PROV-006
    v = _page(json.loads((ROOT / "tests/fixtures/providers/impact_feed_fictional.json").read_text())["pages"][0]).items[0]
    label = price_freshness(v, T0 + timedelta(days=2))
    assert label.state == "stale" and not label.price_is_quote and "confirmed at checkout" in label.message


def test_forbidden_media_derivative_blocked():  # BM-PROV-005
    with pytest.raises(MediaRightsDenied):
        authorize_media_transform("derive_3d", {"display_images": True, "derive_3d_or_ai": False})
    with pytest.raises(MediaRightsDenied):
        authorize_media_transform("unknown_transform", {"display_images": True})
    assert authorize_media_transform("display", {"display_images": True}) == "display_images"


# ----------------------------------------------------------------- URL safety
def fake_dns(table):
    return lambda host: table.get(host, [])


@pytest.mark.parametrize("url", [
    "http://example.com/a.jpg", "file:///etc/passwd", "gopher://x", "https://localhost/x",
    "https://127.0.0.1/x", "https://10.0.0.5/x", "https://169.254.169.254/latest/meta-data",
    "https://metadata.google.internal/computeMetadata/v1/", "https://[::1]/x", "https://[::ffff:10.0.0.1]/x",
    "https://user:pass@cdn.example/x", "https://cdn.example:8080/x", "https://internal.example/x",
])
def test_unsafe_urls_rejected(url):
    with pytest.raises(UnsafeUrl):
        check_public_url(url, fake_dns({"cdn.example": ["93.184.216.34"], "internal.example": ["192.168.1.4"]}))


def test_redirect_to_private_network_rejected_before_request():  # BM-PROV-010
    requested = []

    def transport(url, timeout, max_bytes):
        requested.append(url)
        if url.startswith("https://cdn.example"):
            return RawResponse(302, {"location": "https://rebind.example/secret"}, b"")
        return RawResponse(200, {"content-type": "image/png"}, b"x")

    f = SafeFetcher(transport, resolver=fake_dns({"cdn.example": ["93.184.216.34"], "rebind.example": ["10.1.2.3"]}))
    with pytest.raises(UnsafeUrl):
        f.fetch("https://cdn.example/img.png")
    assert requested == ["https://cdn.example/img.png"]  # private hop never contacted


def test_fetch_enforces_content_type():
    f = SafeFetcher(lambda u, t, m: RawResponse(200, {"content-type": "text/html"}, b"<script>"),
                    resolver=fake_dns({"cdn.example": ["93.184.216.34"]}))
    with pytest.raises(UnsafeUrl):
        f.fetch("https://cdn.example/x")


def test_checkout_redirect_must_be_registered():  # BM-COM-013
    hosts = ("shop.example",)
    assert validate_redirect("https://shop.example/checkout/abc?state=1", hosts)
    for bad in ("https://evil.example/checkout", "https://shop.example.evil.example/x",
                "http://shop.example/x", "https://shop.example:444/x", "//evil.example"):
        with pytest.raises(UnsafeUrl):
            validate_redirect(bad, hosts)
