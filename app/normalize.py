"""
Combines duplicate ticker rows a user might submit (e.g. they bought AAPL
twice on different dates and entered two rows for it) into one position per
ticker, so compute.py never has to reason about the same ticker appearing
twice.

Kept separate from validation.py: validation asks "is each row well-formed,"
this asks "should these rows actually be one position." Different concerns.
"""
from collections import defaultdict


def merge_duplicate_tickers(clean_holdings):
    """clean_holdings: output of validation.validate_holdings (already
    well-formed rows). Returns (merged_holdings, notes) where notes are
    user-facing informational strings (not errors) about what was combined.
    """
    groups = defaultdict(list)
    for h in clean_holdings:
        groups[h["ticker"]].append(h)

    merged = []
    notes = []

    for ticker, rows in groups.items():
        if len(rows) == 1:
            merged.append(rows[0])
            continue

        total_shares = sum(float(r["shares"]) for r in rows)

        priced_rows = [r for r in rows if r.get("purchase_price")]
        weighted_price = None
        if len(priced_rows) == len(rows):
            # every lot has a price -> a real weighted-average cost basis
            weighted_price = sum(
                float(r["shares"]) * float(r["purchase_price"]) for r in priced_rows
            ) / total_shares
        # else: mixed known/unknown cost basis -- don't fabricate one, leave blank

        dated_rows = [r["purchase_date"] for r in rows if r.get("purchase_date")]
        # use the MOST RECENT lot date for tax/behavioral purposes: it's the
        # conservative choice -- if any shares were bought recently, the
        # combined position hasn't fully "aged" into long-term status yet
        latest_date = max(dated_rows) if dated_rows else None

        merged.append({
            "ticker": ticker,
            "shares": str(total_shares),
            "purchase_price": f"{weighted_price:.4f}" if weighted_price is not None else None,
            "purchase_date": latest_date,
        })
        notes.append(
            f"Combined {len(rows)} rows for {ticker} into one position "
            f"({total_shares:g} shares total)."
            + ("" if weighted_price is not None else
               " Cost basis left blank since not every row had a purchase price.")
        )

    return merged, notes
