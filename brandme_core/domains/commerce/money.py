"""Exact money arithmetic for commerce (ch.03 §4, contracts README invariant 6).

Amounts are integer minor units paired with an ISO 4217 code. Wire format is a
decimal string (``Money`` in contracts/domain.schema.json). There is no float
path anywhere in this module, and no implicit FX conversion.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Mapping

# ISO 4217 minor-unit exponents for the currencies this build supports. An
# unknown code is rejected rather than guessed. Source: ISO 4217 list one
# (SIX), checked 2026-10-05 for these entries.
CURRENCY_EXPONENTS: Mapping[str, int] = {
    "USD": 2, "EUR": 2, "GBP": 2, "CAD": 2, "AUD": 2, "CHF": 2,
    "SEK": 2, "NOK": 2, "DKK": 2, "NZD": 2, "SGD": 2, "HKD": 2,
    "JPY": 0, "KRW": 0, "CLP": 0,
    "KWD": 3, "BHD": 3, "JOD": 3,
}

# Matches the domain schema: nonnegative, no leading zeros, at most 18 digits.
_AMOUNT_RE = re.compile(r"^(0|[1-9][0-9]{0,17})$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
MAX_MINOR = 10**18 - 1


class MoneyError(ValueError):
    """Invalid amount, currency or cross-currency operation."""


def exponent(currency: str) -> int:
    if not _CURRENCY_RE.match(currency or ""):
        raise MoneyError(f"invalid currency code: {currency!r}")
    try:
        return CURRENCY_EXPONENTS[currency]
    except KeyError:
        raise MoneyError(f"unsupported currency: {currency}") from None


@dataclass(frozen=True, order=False)
class Money:
    amount_minor: int
    currency: str

    def __post_init__(self) -> None:
        if isinstance(self.amount_minor, bool) or not isinstance(self.amount_minor, int):
            raise MoneyError("amount_minor must be an integer")
        if self.amount_minor < 0 or self.amount_minor > MAX_MINOR:
            raise MoneyError("amount_minor out of range")
        exponent(self.currency)

    # -- wire ---------------------------------------------------------------
    @classmethod
    def from_wire(cls, value: Mapping[str, object]) -> "Money":
        if not isinstance(value, Mapping) or set(value.keys()) != {"amount_minor", "currency"}:
            raise MoneyError("money must be exactly {amount_minor, currency}")
        amount = value["amount_minor"]
        if not isinstance(amount, str) or not _AMOUNT_RE.match(amount):
            raise MoneyError("amount_minor must be a nonnegative decimal string")
        currency = value["currency"]
        if not isinstance(currency, str):
            raise MoneyError("currency must be a string")
        return cls(int(amount), currency)

    def to_wire(self) -> dict:
        return {"amount_minor": str(self.amount_minor), "currency": self.currency}

    # -- arithmetic ---------------------------------------------------------
    @classmethod
    def zero(cls, currency: str) -> "Money":
        return cls(0, currency)

    def _same(self, other: "Money") -> None:
        if not isinstance(other, Money):
            raise MoneyError("operand is not Money")
        if other.currency != self.currency:
            raise MoneyError(f"currency mismatch: {self.currency} vs {other.currency}")

    def __add__(self, other: "Money") -> "Money":
        self._same(other)
        return Money(self.amount_minor + other.amount_minor, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._same(other)
        if other.amount_minor > self.amount_minor:
            raise MoneyError("subtraction would go negative")
        return Money(self.amount_minor - other.amount_minor, self.currency)

    def times(self, quantity: int) -> "Money":
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 0:
            raise MoneyError("quantity must be a nonnegative integer")
        return Money(self.amount_minor * quantity, self.currency)

    def __le__(self, other: "Money") -> bool:
        self._same(other)
        return self.amount_minor <= other.amount_minor

    def __lt__(self, other: "Money") -> bool:
        self._same(other)
        return self.amount_minor < other.amount_minor

    def __ge__(self, other: "Money") -> bool:
        self._same(other)
        return self.amount_minor >= other.amount_minor

    def __gt__(self, other: "Money") -> bool:
        self._same(other)
        return self.amount_minor > other.amount_minor

    def display(self) -> str:
        """Human display only; never parsed back."""
        exp = exponent(self.currency)
        if exp == 0:
            return f"{self.amount_minor} {self.currency}"
        whole, frac = divmod(self.amount_minor, 10**exp)
        return f"{whole}.{frac:0{exp}d} {self.currency}"


def sum_money(values: Iterable[Money], currency: str) -> Money:
    total = Money.zero(currency)
    for v in values:
        total = total + v
    return total
