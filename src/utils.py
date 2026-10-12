"""Small reusable helpers shared by every module."""
from __future__ import annotations

from typing import Optional

from contextvars import ContextVar

from src.config import CURRENCIES, CURRENCY_SYMBOL


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Divide without ever raising ZeroDivisionError (or returning NaN/inf)."""
    try:
        if denominator is None or denominator == 0 or denominator != denominator:
            return default
        result = numerator / denominator
        return default if result != result else float(result)
    except (TypeError, ZeroDivisionError):
        return default


def growth_pct(current: float, previous: float) -> Optional[float]:
    """((current - previous) / previous) * 100, safely.

    - previous == 0 and current == 0 -> 0.0 (nothing changed)
    - previous == 0 and current != 0 -> None (growth is undefined: it is a 'new' value)
    """
    if previous is None or current is None:
        return None
    if previous == 0:
        return 0.0 if current == 0 else None
    return float((current - previous) / abs(previous) * 100)


def format_inr(value: float, decimals: int = 0) -> str:
    """Format a number in the Indian digit-grouping style: 1120000 -> ₹11,20,000."""
    if value is None:
        return "N/A"
    sign = "-" if value < 0 else ""
    value = abs(float(value))
    whole, _, frac = f"{value:.{decimals}f}".partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts + [tail])
    out = f"{CURRENCY_SYMBOL}{whole}"
    return f"{sign}{out}.{frac}" if frac else f"{sign}{out}"


def fmt_pct(value: Optional[float], decimals: int = 1, signed: bool = True) -> str:
    if value is None:
        return "N/A"
    return f"{value:+.{decimals}f}%" if signed else f"{value:.{decimals}f}%"


# ------------------------------------------------------------------ currency handling
# The active currency is stored in a ContextVar (safe for threads/web requests) so every
# module formats money consistently without passing "currency" through every function.
_active_currency: ContextVar = ContextVar("active_currency", default="INR")


def set_currency(code: Optional[str]) -> str:
    code = (code or "INR").upper()
    if code not in CURRENCIES:
        raise ValueError(f"Unsupported currency '{code}'. Choose from: {', '.join(CURRENCIES)}")
    _active_currency.set(code)
    return code


def get_currency() -> str:
    return _active_currency.get()


def format_money(value: Optional[float], decimals: int = 0) -> str:
    """Format money in the ACTIVE currency: INR -> Indian grouping (11,20,000), others -> 1,120,000."""
    code = get_currency()
    if code == "INR":
        return format_inr(value, decimals)
    if value is None:
        return "N/A"
    sign = "-" if value < 0 else ""
    return f"{sign}{CURRENCIES[code]}{abs(float(value)):,.{decimals}f}"
