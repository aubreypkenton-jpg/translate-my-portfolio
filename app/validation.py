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

MAX_HOLDINGS = 50          # distinct tickers; keeps one request from hammering the free data source
MAX_LOTS = 2000            # individual purchase rows (monthly investing for decades fits)
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

    # Cap distinct tickers (each one is a network fetch), not rows: a monthly
    # investor can have hundreds of purchase lots of just a few funds.
    kept: list[dict] = []
    seen: set[str] = set()
    dropped: set[str] = set()
    for row in clean:
        if row["ticker"] not in seen and len(seen) >= MAX_HOLDINGS:
            dropped.add(row["ticker"])
            continue
        seen.add(row["ticker"])
        kept.append(row)
    if dropped or len(kept) > MAX_LOTS:
        errors.append((MAX_HOLDINGS, f"Only the first {MAX_HOLDINGS} different holdings (and {MAX_LOTS} "
                                     f"purchases) were analyzed; the free data source can't handle more in one go."))
    clean = kept[:MAX_LOTS]

    return clean, errors


def parse_risk_free_rate(raw: str | None, default: float, maximum: float) -> tuple[float, str | None]:
    """Parse the risk-free-rate box (a percent like "4.25") into a decimal.

    Blank means "use the default". Returns ``(rate, error_message_or_None)``;
    on error the default is returned so the analysis still runs.
    """
    raw = (raw or "").strip().rstrip("%")
    if not raw:
        return default, None
    value = parse_number(raw)
    if value is None or value < 0 or value > maximum * 100:
        return default, (f"Risk-free rate must be a percent between 0 and {maximum * 100:.0f} "
                         f"(e.g. 4.25). Used the default {default * 100:.2f}% instead.")
    return value / 100.0, None


def validate_targets(tickers: list[str], raw_pcts: list[str], tolerance_pct: float
                     ) -> tuple[dict[str, float] | None, list[str]]:
    """Validate "what if I rebalance" target weights.

    Rules: every box must be a number from 0 to 100 (blank counts as 0), no
    ticker may appear twice, and the total must be 100% (within
    ``tolerance_pct``). Returns ``(targets_or_None, errors)``.
    """
    errors: list[str] = []
    targets: dict[str, float] = {}
    for t, raw in zip(tickers, raw_pcts, strict=False):
        t = (t or "").strip().upper()
        if not t:
            continue
        if t in targets:
            errors.append(f"{t} appears twice in the target weights.")
            continue
        value = parse_number((raw or "").rstrip("%")) if (raw or "").strip() else 0.0
        if value is None:
            errors.append(f"{t}: target weight must be a number.")
            continue
        if value < 0:
            errors.append(f"{t}: target weight can't be negative (this tool doesn't model short selling).")
            continue
        if value > 100:
            errors.append(f"{t}: target weight can't be more than 100%.")
            continue
        targets[t] = value
    if not errors:
        total = sum(targets.values())
        if total <= 0:
            errors.append("Give at least one holding a target weight above 0%.")
        elif abs(total - 100.0) > tolerance_pct:
            errors.append(f"Target weights add up to {total:.1f}%; they need to total 100%.")
    return (None if errors else targets), errors
