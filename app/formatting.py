"""Jinja template filters so every number on the page is formatted the same
way, and a missing value always shows as an en dash instead of 'None'."""
from __future__ import annotations

DASH = "–"


def pct(value: float | None, digits: int = 1, signed: bool = False) -> str:
    """12.345 -> '12.3%'; signed=True adds '+' to positives."""
    if value is None:
        return DASH
    sign = "+" if signed and value > 0 else ""
    return f"{sign}{value:,.{digits}f}%"


def money(value: float | None, signed: bool = False) -> str:
    """1234.5 -> '$1,235'; negatives -> '-$1,235'."""
    if value is None:
        return DASH
    if value < 0:
        return f"-${abs(value):,.0f}"
    return f"{'+' if signed and value > 0 else ''}${value:,.0f}"


def num(value: float | None, digits: int = 2) -> str:
    if value is None:
        return DASH
    return f"{value:,.{digits}f}"


def clean_num(value) -> str:
    """'10.0' -> '10', None -> '' (for re-filling form inputs)."""
    if value in (None, ""):
        return ""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{f:g}" if abs(f) < 1e15 else str(value)


FILTERS = {"pct": pct, "money": money, "num": num, "clean_num": clean_num}
