"""
Photo try-on provider interface (ch.02 §6.3).

A provider is usable only when it is *approved*: account, region, permitted
use and processing/retention terms reviewed. None is approved in this
repository. The first candidate named by the spec is Google's Virtual Try-On
(`virtual-try-on-001`); no adapter is shipped for it because no account,
region or terms exist here to verify one against.

``SimulatedTryOnProvider`` is a test/demo double. Everything it produces is
labelled simulated; it is never an approved provider.

Calibrated fit is not a provider capability: it needs a validated
measurement/material pipeline that does not exist, so it stays unavailable.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol, Tuple

GENERATED_LABEL = "generated_visual_preview"


@dataclass(frozen=True)
class ProviderTerms:
    provider_id: str
    terms_version: str
    region: str
    retention_disclosure: str
    supports_deletion: bool


class TryOnProvider(Protocol):
    terms: ProviderTerms
    approved: bool
    simulated: bool

    def submit(self, job_id: str, person_image: bytes, product_ref: str) -> str: ...
    def poll(self, provider_job_ref: str) -> Tuple[str, Optional[bytes], Optional[str]]: ...  # (state, output, error_code)
    def delete(self, provider_job_ref: str) -> bool: ...


@dataclass
class SimulatedTryOnProvider:
    """Deterministic stand-in. Records every upload so tests can prove none happened."""

    terms: ProviderTerms = field(default_factory=lambda: ProviderTerms(
        "simulated-tryon", "sim-2026-10", "local", "Simulated provider: nothing leaves this process.", True))
    approved: bool = True
    simulated: bool = True
    fail_with: Optional[str] = None
    uploads: List[Tuple[str, int]] = field(default_factory=list)
    deleted: List[str] = field(default_factory=list)
    _jobs: Dict[str, bytes] = field(default_factory=dict)

    def submit(self, job_id: str, person_image: bytes, product_ref: str) -> str:
        self.uploads.append((job_id, len(person_image)))
        ref = f"sim-{job_id}"
        self._jobs[ref] = b"\x89PNG\r\n\x1a\n" + hashlib.sha256(person_image + product_ref.encode()).digest()
        return ref

    def poll(self, provider_job_ref: str) -> Tuple[str, Optional[bytes], Optional[str]]:
        if self.fail_with:
            return "failed", None, self.fail_with
        out = self._jobs.get(provider_job_ref)
        return ("succeeded", out, None) if out is not None else ("failed", None, "unknown_job")

    def delete(self, provider_job_ref: str) -> bool:
        self.deleted.append(provider_job_ref)
        return self._jobs.pop(provider_job_ref, None) is not None


class ProviderRegistry:
    def __init__(self, providers: Optional[List[TryOnProvider]] = None):
        self._p = {p.terms.provider_id: p for p in (providers or [])}

    def active(self) -> Optional[TryOnProvider]:
        """The approved provider, if exactly one is approved."""
        approved = [p for p in self._p.values() if p.approved]
        return approved[0] if len(approved) == 1 else None

    def get(self, provider_id: Optional[str]) -> Optional[TryOnProvider]:
        return self._p.get(provider_id or "")
