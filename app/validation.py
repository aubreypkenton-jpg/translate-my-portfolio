"""Server-side validation for submitted holdings.

Never trust the browser: the HTML form has client-side checks too, but this
is what actually protects compute.py from bad input. Returns per-row error
messages so the UI can point at exactly what's wrong instead of one generic
"something's wrong" message.
"""
from __future__ import annotations

import math
import re
from datetime import date, datetime, timezone

# Letters, digits, and the punctuation real symbols use: BRK.B, BTC-USD,
# 0700.HK, ^GSPC (index), EURUSD=X (currency). 1-15 characters.
TICKER_RE = re.compile(r"^\^?[A-Z0-9][A-Z0-9.\-=]{0,14}$")

MAX_HOLDINGS = 50          # keeps one request from hammering the free data source
MAX_SHARES = 1e9           # anything above this is almost certainly a typo
MAX_PRICE = 1e7
EARLIEST_DATE = date(1970, 1, 1)


def today_utc() -> date:
    """Today's date in UTC (one helper so tests and code agree)."""
    return datetime.now(timezone.utc).date()


def parse_number(raw: str) -> float | None:
    """Parse a user-typed number, forgiving "$1,250.50" style input.

    Returns None for anything that isn't a finite number (this is what
    rejects "nan" and "inf", which Python's float() would otherwise accept).
    """
    cleaned = raw.replace(",", "").replace("$", "").strip()
    if not cleaned:
        return None
    try:
        value = float(cleaned)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def validate_holdings(raw_holdings: list[dict]) -> tuple[list[dict], list[tuple[int, str]]]:
    """Check each submitted row.

    ``raw_holdings`` is a list of dicts with string values straight from the
    form or CSV. Returns ``(clean_holdings, row_errors)``, where row_errors
    is a list of ``(row_index, message)`` tuples.
    """
    clean: list[dict] = []
    errors: list[tuple[int, str]] = []
    today = today_utc()

    for i, h in enumerate(raw_holdings):
        ticker = (h.get("ticker") or "").strip().upper()
        shares_raw = (h.get("shares") or "").strip()
        price_raw = (h.get("purchase_price") or "").strip()
        date_raw = (h.get("purchase_date") or "").strip()
        row = f"Row {i + 1}"

        if not ticker and not shares_raw:
            continue  # a genuinely blank row: skip silently, not an error

        if not ticker:
            errors.append((i, f"{row}: Missing ticker symbol."))
            continue
        if not TICKER_RE.match(ticker):
            errors.append((i, f"{row}: '{ticker}' doesn't look like a valid ticker symbol."))
            continue

        shares = parse_number(shares_raw)
        if shares is None or shares <= 0:
            errors.append((i, f"{row} ({ticker}): shares must be a positive number."))
            continue
        if shares > MAX_SHARES:
            errors.append((i, f"{row} ({ticker}): {shares:,.0f} shares looks like a typo."))
            continue

        purchase_price = None
        if price_raw:
            purchase_price = parse_number(price_raw)
            if purchase_price is None or purchase_price <= 0 or purchase_price > MAX_PRICE:
                errors.append((i, f"{row} ({ticker}): purchase price must be a positive number."))
                continue

        purchase_date = None
        if date_raw:
            try:
                parsed = datetime.strptime(date_raw, "%Y-%m-%d").date()
            except ValueError:
                errors.append((i, f"{row} ({ticker}): purchase date must be a valid date (YYYY-MM-DD)."))
                continue
            if parsed > today:
                errors.append((i, f"{row} ({ticker}): purchase date can't be in the future."))
                continue
            if parsed < EARLIEST_DATE:
                errors.append((i, f"{row} ({ticker}): purchase date looks too early to be right."))
                continue
            purchase_date = date_raw

        clean.append({
            "ticker": ticker,
            "shares": repr(shares),
            "purchase_price": repr(purchase_price) if purchase_price is not None else None,
            "purchase_date": purchase_date,
        })

    if len(clean) > MAX_HOLDINGS:
        errors.append((MAX_HOLDINGS, f"Only the first {MAX_HOLDINGS} holdings were analyzed; "
                                     f"the free data source can't handle more in one go."))
        clean = clean[:MAX_HOLDINGS]

    return clean, errors
