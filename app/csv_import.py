"""
Parses an uploaded CSV of holdings into the same raw-holdings shape
validation.py expects, so a CSV upload and manually-typed rows go through
the exact same validation path afterward -- no separate rules for the two
input methods.

Expected columns (header row, case-insensitive, any order):
  ticker, shares, purchase_price (optional), purchase_date (optional)
"""
import csv
import io

REQUIRED_COLUMNS = {"ticker", "shares"}
OPTIONAL_COLUMNS = {"purchase_price", "purchase_date"}
KNOWN_COLUMNS = REQUIRED_COLUMNS | OPTIONAL_COLUMNS

# common alternate spellings people actually use in spreadsheets. Keys here
# are matched AFTER _normalize_header() has already lowercased and swapped
# spaces for underscores, so every key must be in that underscore form.
COLUMN_ALIASES = {
    "symbol": "ticker",
    "qty": "shares",
    "quantity": "shares",
    "cost": "purchase_price",
    "cost_basis": "purchase_price",
    "price": "purchase_price",
    "price_paid": "purchase_price",
    "date": "purchase_date",
    "date_purchased": "purchase_date",
}


def _normalize_header(raw):
    key = raw.strip().lower().replace(" ", "_")
    return COLUMN_ALIASES.get(key, key)


def parse_csv(file_stream, max_rows=200):
    """
    file_stream: a file-like object opened in binary or text mode (Flask
    gives us a werkzeug FileStorage stream).
    Returns (holdings, errors) -- same shape as validation.validate_holdings
    expects as input, plus a list of human-readable error strings.
    """
    errors = []

    try:
        raw_bytes = file_stream.read()
        text = raw_bytes.decode("utf-8-sig") if isinstance(raw_bytes, bytes) else raw_bytes
    except UnicodeDecodeError:
        return [], ["Couldn't read that CSV file -- please save it as UTF-8 or plain CSV and try again."]

    if not text.strip():
        return [], ["The CSV file appears to be empty."]

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return [], ["Couldn't find a header row in that CSV. Expected columns: ticker, shares, purchase_price, purchase_date."]

    normalized_fields = {_normalize_header(f): f for f in reader.fieldnames if f}
    missing = REQUIRED_COLUMNS - set(normalized_fields.keys())
    if missing:
        errors.append(
            f"CSV is missing required column(s): {', '.join(sorted(missing))}. "
            f"Expected at least 'ticker' and 'shares'."
        )
        return [], errors

    holdings = []
    for i, row in enumerate(reader):
        if i >= max_rows:
            errors.append(f"Only the first {max_rows} rows were read -- split larger files into batches.")
            break
        if not any((row.get(v) or "").strip() for v in normalized_fields.values()):
            continue  # skip fully blank rows
        holdings.append({
            "ticker": row.get(normalized_fields.get("ticker"), ""),
            "shares": row.get(normalized_fields.get("shares"), ""),
            "purchase_price": row.get(normalized_fields.get("purchase_price"), "") if "purchase_price" in normalized_fields else "",
            "purchase_date": row.get(normalized_fields.get("purchase_date"), "") if "purchase_date" in normalized_fields else "",
        })

    return holdings, errors
