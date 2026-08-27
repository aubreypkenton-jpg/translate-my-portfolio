from app.normalize import merge_duplicate_tickers


def test_single_row_per_ticker_passes_through_unchanged():
    holdings = [{"ticker": "AAPL", "shares": "10", "purchase_price": "150", "purchase_date": "2022-01-01"}]
    merged, notes = merge_duplicate_tickers(holdings)
    assert merged == holdings
    assert notes == []


def test_duplicate_rows_merge_shares_and_weighted_price():
    holdings = [
        {"ticker": "AAPL", "shares": "10", "purchase_price": "100", "purchase_date": "2021-01-01"},
        {"ticker": "AAPL", "shares": "10", "purchase_price": "200", "purchase_date": "2022-01-01"},
    ]
    merged, notes = merge_duplicate_tickers(holdings)
    assert len(merged) == 1
    assert float(merged[0]["shares"]) == 20.0
    assert float(merged[0]["purchase_price"]) == 150.0  # simple average since shares are equal
    assert merged[0]["purchase_date"] == "2022-01-01"  # most recent lot, conservative for tax
    assert len(notes) == 1
    assert "AAPL" in notes[0]


def test_duplicate_rows_with_missing_price_leaves_cost_basis_blank():
    holdings = [
        {"ticker": "AAPL", "shares": "10", "purchase_price": "100", "purchase_date": "2021-01-01"},
        {"ticker": "AAPL", "shares": "5", "purchase_price": None, "purchase_date": "2022-01-01"},
    ]
    merged, notes = merge_duplicate_tickers(holdings)
    assert merged[0]["purchase_price"] is None
    assert float(merged[0]["shares"]) == 15.0


def test_mixed_tickers_only_merges_actual_duplicates():
    holdings = [
        {"ticker": "AAPL", "shares": "10", "purchase_price": "100", "purchase_date": "2021-01-01"},
        {"ticker": "MSFT", "shares": "5", "purchase_price": "200", "purchase_date": "2021-01-01"},
        {"ticker": "AAPL", "shares": "5", "purchase_price": "150", "purchase_date": "2022-06-01"},
    ]
    merged, notes = merge_duplicate_tickers(holdings)
    tickers = sorted(h["ticker"] for h in merged)
    assert tickers == ["AAPL", "MSFT"]
    assert len(notes) == 1
