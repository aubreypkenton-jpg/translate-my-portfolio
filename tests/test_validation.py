from app.validation import validate_holdings


def test_valid_row_passes():
    clean, errors = validate_holdings([
        {"ticker": "aapl", "shares": "10", "purchase_price": "150", "purchase_date": "2022-01-01"},
    ])
    assert errors == []
    assert clean[0]["ticker"] == "AAPL"


def test_blank_row_is_skipped_silently():
    clean, errors = validate_holdings([{"ticker": "", "shares": "", "purchase_price": "", "purchase_date": ""}])
    assert clean == []
    assert errors == []


def test_missing_shares_is_an_error():
    clean, errors = validate_holdings([{"ticker": "AAPL", "shares": "", "purchase_price": "", "purchase_date": ""}])
    assert clean == []
    assert len(errors) == 1


def test_negative_shares_rejected():
    clean, errors = validate_holdings([{"ticker": "AAPL", "shares": "-5", "purchase_price": "", "purchase_date": ""}])
    assert clean == []
    assert "positive" in errors[0][1]  # errors are (row_index, message) tuples


def test_bad_ticker_format_rejected():
    clean, errors = validate_holdings([{"ticker": "!!!", "shares": "5", "purchase_price": "", "purchase_date": ""}])
    assert clean == []
    assert len(errors) == 1


def test_future_purchase_date_rejected():
    clean, errors = validate_holdings([{"ticker": "AAPL", "shares": "5", "purchase_price": "", "purchase_date": "2099-01-01"}])
    assert clean == []
    assert "future" in errors[0][1]


def test_multiple_rows_mixed_validity():
    clean, errors = validate_holdings([
        {"ticker": "AAPL", "shares": "10", "purchase_price": "", "purchase_date": ""},
        {"ticker": "BAD", "shares": "-1", "purchase_price": "", "purchase_date": ""},
    ])
    assert len(clean) == 1
    assert len(errors) == 1
