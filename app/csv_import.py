"""
Turns an uploaded CSV into the same raw-holdings rows the form produces, so a
CSV and typed rows go through exactly the same validation afterward.

Two kinds of file are understood:

1. **Positions or purchase lots** (one row per holding or per purchase):
   ``ticker, shares, purchase_price, purchase_date`` plus the column names
   brokerages commonly use ("Symbol", "Quantity", "Average Cost", "Cost Basis
   Total", "Acquired", ...). A *total* cost column is converted to per share.

2. **Transaction history** (one row per buy/sell, e.g. a Robinhood account
   activity report with "Activity Date, Instrument, Trans Code, Quantity,
   Price"). Buys become purchase lots; sells are matched to the oldest
   remaining shares first (FIFO) so what's left is what you still own.

Dates like 3/15/2024 are converted to 2024-03-15. Nothing here touches the
network; everything is plain text processing.
"""
from __future__ import annotations

import csv
import io
import re
from collections import defaultdict
from datetime import datetime
from typing import IO

REQUIRED_COLUMNS = {"ticker", "shares"}

# Keys are headers after _normalize_header(): lowercase, non-letters -> "_".
COLUMN_ALIASES = {
    # ticker
    "symbol": "ticker", "instrument": "ticker", "security": "ticker",
    # shares
    "qty": "shares", "quantity": "shares", "units": "shares", "shares_owned": "shares",
    # cost per share
    "cost": "purchase_price", "cost_basis": "purchase_price", "price": "purchase_price",
    "price_paid": "purchase_price", "average_cost": "purchase_price", "avg_cost": "purchase_price",
    "average_cost_basis": "purchase_price", "cost_basis_per_share": "purchase_price",
    "cost_per_share": "purchase_price", "unit_cost": "purchase_price", "average_price": "purchase_price",
    "avg_price": "purchase_price", "purchase_price_per_share": "purchase_price",
    # TOTAL cost for the whole row (converted to per share below)
    "cost_basis_total": "total_cost", "total_cost": "total_cost", "total_cost_basis": "total_cost",
    # date
    "date": "purchase_date", "date_purchased": "purchase_date", "acquired": "purchase_date",
    "date_acquired": "purchase_date", "open_date": "purchase_date", "trade_date": "purchase_date",
    "activity_date": "purchase_date", "purchase_date": "purchase_date",
    # transaction type (presence means "transaction history")
    "trans_code": "action", "transaction_type": "action", "action": "action",
}

BUY_WORDS = {"buy", "bought", "you_bought", "purchase", "reinvestment", "dividend_reinvestment"}
SELL_WORDS = {"sell", "sold", "you_sold", "sale"}
SPLIT_CODES = {"spl", "spr", "split", "stock_split", "reverse_split"}
SPLIT_WORD = re.compile(r"\bsplit\b", re.IGNORECASE)

MAX_HISTORY_ROWS = 5000


def _normalize_header(raw: str) -> str:
    """'Price ($)' -> 'price', 'Cost Basis Total' -> 'cost_basis_total', then aliases."""
    key = re.sub(r"[^a-z0-9]+", "_", raw.strip().lower()).strip("_")
    return COLUMN_ALIASES.get(key, key)


def _clean_number(raw: str | None) -> str:
    """'$1,234.50' -> '1234.50'; '(5)' -> '-5'. Returns '' for blanks."""
    s = (raw or "").strip()
    if not s:
        return ""
    negative = s.startswith("(") and s.endswith(")")
    s = s.strip("()").replace("$", "").replace(",", "").strip()
    return f"-{s}" if negative and s else s


def _to_float(raw: str | None) -> float | None:
    try:
        return float(_clean_number(raw))
    except ValueError:
        return None


def normalize_date(raw: str | None) -> str:
    """Accept 2024-03-15, 3/15/2024, 03/15/24, 2024/03/15; return ISO or the input unchanged."""
    s = (raw or "").strip()
    if not s:
        return ""
    s = s.split(" ")[0].split("T")[0]
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d", "%m-%d-%Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return s  # validation will report it clearly


def _ticker_from(raw: str | None) -> str:
    """Some exports wrap symbols ('AAPL ', 'Apple Inc (AAPL)'); keep just the symbol."""
    s = (raw or "").strip()
    m = re.search(r"\(([A-Za-z0-9.\-^=]{1,15})\)\s*$", s)
    return m.group(1) if m else s


def parse_csv(file_stream: IO, max_rows: int = 200) -> tuple[list[dict], list[str]]:
    """Backward-compatible wrapper: returns ``(holdings, errors)``."""
    holdings, errors, _notes = parse_csv_with_notes(file_stream, max_rows=max_rows)
    return holdings, errors


def parse_csv_with_notes(file_stream: IO, max_rows: int = 200) -> tuple[list[dict], list[str], list[str]]:
    """Parse an uploaded CSV.

    Returns ``(holdings, errors, notes)``: holdings are raw rows (strings) in
    the shape validation.validate_holdings() expects; errors are problems the
    user must fix; notes are informational (what was imported and how).
    """
    try:
        raw_bytes = file_stream.read()
        text = raw_bytes.decode("utf-8-sig") if isinstance(raw_bytes, bytes) else raw_bytes
    except UnicodeDecodeError:
        return [], ["Couldn't read that CSV file. Please save it as UTF-8 or plain CSV and try again."], []

    if not text.strip():
        return [], ["The CSV file appears to be empty."], []

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return [], ["Couldn't find a header row in that CSV. Expected columns: "
                    "ticker, shares, purchase_price, purchase_date."], []

    columns: dict[str, str] = {}
    for f in reader.fieldnames:
        if f and _normalize_header(f) not in columns:
            columns[_normalize_header(f)] = f

    if "action" in columns and "ticker" in columns and "shares" in columns:
        return _parse_transactions(reader, columns)

    missing = REQUIRED_COLUMNS - set(columns)
    if missing:
        return [], [f"CSV is missing required column(s): {', '.join(sorted(missing))}. "
                    f"Expected at least 'ticker' and 'shares' (or a brokerage transaction history)."], []

    def col(row: dict, key: str) -> str:
        return (row.get(columns[key]) or "") if key in columns else ""

    holdings: list[dict] = []
    errors: list[str] = []
    for i, row in enumerate(reader):
        if i >= max_rows:
            errors.append(f"Only the first {max_rows} rows were read; split larger files into batches.")
            break
        if not any((v or "").strip() for v in row.values() if isinstance(v, str)):
            continue  # skip fully blank rows
        price = col(row, "purchase_price")
        if not price.strip() and "total_cost" in columns:
            total, qty = _to_float(col(row, "total_cost")), _to_float(col(row, "shares"))
            if total and qty:
                price = f"{total / qty:.6f}"
        holdings.append({
            "ticker": _ticker_from(col(row, "ticker")),
            "shares": col(row, "shares"),
            "purchase_price": price,
            "purchase_date": normalize_date(col(row, "purchase_date")),
        })

    return holdings, errors, []


def _parse_transactions(reader: csv.DictReader, columns: dict[str, str]
                        ) -> tuple[list[dict], list[str], list[str]]:
    """Rebuild current purchase lots from a buy/sell history using FIFO."""
    def col(row: dict, key: str) -> str:
        return (row.get(columns[key]) or "") if key in columns else ""

    trades: list[tuple[str, int, str, str, float, float | None]] = []
    split_rows = 0
    for i, row in enumerate(reader):
        if i >= MAX_HISTORY_ROWS:
            break
        action = re.sub(r"[^a-z]+", "_", col(row, "action").strip().lower()).strip("_")
        ticker = _ticker_from(col(row, "ticker")).upper()
        description = row.get(columns["description"]) if "description" in columns else ""
        if action in SPLIT_CODES or SPLIT_WORD.search(description or ""):
            split_rows += 1
        if not ticker or action not in BUY_WORDS | SELL_WORDS:
            continue  # dividends, deposits, fees, etc. don't change share counts here
        qty = _to_float(col(row, "shares"))
        if not qty:
            continue
        date = normalize_date(col(row, "purchase_date"))
        price = _to_float(col(row, "purchase_price"))
        kind = "buy" if action in BUY_WORDS else "sell"
        trades.append((date, i, ticker, kind, abs(qty), price))

    # Exports are often newest-first; process oldest-first. For same-day rows,
    # later file rows are older in newest-first files, so sort them descending.
    newest_first = len(trades) > 1 and trades[0][0] > trades[-1][0]
    trades.sort(key=lambda x: (x[0], -x[1] if newest_first else x[1]))

    open_lots: dict[str, list[list]] = defaultdict(list)  # ticker -> [[date, shares, price], ...]
    unmatched: set[str] = set()
    for date, _i, ticker, kind, qty, price in trades:
        if kind == "buy":
            open_lots[ticker].append([date, qty, price])
            continue
        remaining = qty
        lots = open_lots[ticker]
        while remaining > 1e-9 and lots:
            take = min(remaining, lots[0][1])
            lots[0][1] -= take
            remaining -= take
            if lots[0][1] <= 1e-9:
                lots.pop(0)
        if remaining > 1e-6:
            unmatched.add(ticker)

    holdings = [
        {"ticker": t, "shares": f"{shares:.6f}".rstrip("0").rstrip("."),
         "purchase_price": f"{price:.4f}" if price else "", "purchase_date": date}
        for t in sorted(open_lots) for date, shares, price in open_lots[t] if shares > 1e-9
    ]
    n_buys = sum(1 for tr in trades if tr[3] == "buy")
    n_sells = len(trades) - n_buys
    notes = [f"Read a transaction history: {n_buys} buy(s) and {n_sells} sell(s), leaving "
             f"{len(holdings)} purchase lot(s) across {len({h['ticker'] for h in holdings})} holding(s). "
             f"Sales were matched to the oldest shares first (FIFO)."]
    errors: list[str] = []
    if unmatched:
        notes.append(f"Sold more {', '.join(sorted(unmatched))} than this file shows being bought "
                     f"(the shares may have been transferred in or bought before the file's date range). "
                     f"Double-check those share counts.")
    if split_rows:
        notes.append("This history includes stock splits, which aren't applied automatically. "
                     "Check share counts against your brokerage for the affected holdings.")
    if not holdings and not errors:
        errors.append("That transaction history didn't leave any shares currently held "
                      "(everything bought was also sold, or no buy/sell rows were found).")
    return holdings, errors, notes
