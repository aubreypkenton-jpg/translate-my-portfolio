"""Server-side validation for submitted holdings.

Never trust the browser: the HTML form has client-side constraints too, but
this is what actually protects compute.py from bad input. Returns per-row
error messages so the UI can point at exactly what's wrong, rather than one
generic "something's wrong" message.
"""
import re
from datetime import datetime

TICKER_RE = re.compile(r"^[A-Za-z.\-]{1,10}$")


def validate_holdings(raw_holdings):
    """raw_holdings: list of dicts with string values straight from the form.
    Returns (clean_holdings, row_errors) where row_errors is a list of
    (row_index, message) tuples for anything that failed validation."""
    clean = []
    errors = []

    for i, h in enumerate(raw_holdings):
        ticker = (h.get("ticker") or "").strip().upper()
        shares_raw = (h.get("shares") or "").strip()
        price_raw = (h.get("purchase_price") or "").strip()
        date_raw = (h.get("purchase_date") or "").strip()

        if not ticker and not shares_raw:
            continue  # a genuinely blank row -- skip silently, not an error

        if not ticker:
            errors.append((i, "Missing ticker symbol."))
            continue
        if not TICKER_RE.match(ticker):
            errors.append((i, f"'{ticker}' doesn't look like a valid ticker symbol."))
            continue

        try:
            shares = float(shares_raw)
            if shares <= 0:
                raise ValueError
        except ValueError:
            errors.append((i, f"{ticker}: shares must be a positive number."))
            continue

        purchase_price = None
        if price_raw:
            try:
                purchase_price = float(price_raw)
                if purchase_price <= 0:
                    raise ValueError
            except ValueError:
                errors.append((i, f"{ticker}: purchase price must be a positive number."))
                continue

        purchase_date = None
        if date_raw:
            try:
                parsed = datetime.strptime(date_raw, "%Y-%m-%d")
                if parsed > datetime.utcnow():
                    errors.append((i, f"{ticker}: purchase date can't be in the future."))
                    continue
                purchase_date = date_raw
            except ValueError:
                errors.append((i, f"{ticker}: purchase date must be a valid date."))
                continue

        clean.append({
            "ticker": ticker,
            "shares": shares_raw,
            "purchase_price": price_raw or None,
            "purchase_date": purchase_date,
        })

    return clean, errors
