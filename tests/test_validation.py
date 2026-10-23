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


# ---- hardening added in the reliability pass ----
import pytest  # noqa: E402

from app.validation import MAX_HOLDINGS, parse_number  # noqa: E402


def _row(ticker="AAPL", shares="5", price="", date=""):
    return {"ticker": ticker, "shares": shares, "purchase_price": price, "purchase_date": date}


@pytest.mark.parametrize("bad", ["nan", "NaN", "inf", "-inf", "infinity", "0", "-0", "abc", "1e400"])
def test_non_finite_or_zero_shares_rejected(bad):
    clean, errors = validate_holdings([_row(shares=bad)])
    assert clean == [] and len(errors) == 1


@pytest.mark.parametrize("bad", ["nan", "inf", "0", "-3"])
def test_non_finite_purchase_price_rejected(bad):
    clean, errors = validate_holdings([_row(price=bad)])
    assert clean == [] and "purchase price" in errors[0][1]


@pytest.mark.parametrize("ticker", ["BRK.B", "BTC-USD", "0700.HK", "^GSPC", "EURUSD=X", "voo"])
def test_real_world_ticker_formats_accepted(ticker):
    clean, errors = validate_holdings([_row(ticker=ticker)])
    assert errors == [] and clean[0]["ticker"] == ticker.upper()


@pytest.mark.parametrize("ticker", ["AAPL;DROP", "<script>", "A B", "-AAPL", "TOOLONGTICKERSYMBOL"])
def test_suspicious_tickers_rejected(ticker):
    clean, errors = validate_holdings([_row(ticker=ticker)])
    assert clean == []


def test_friendly_number_formats_accepted():
    clean, errors = validate_holdings([_row(shares="1,000", price="$150.25")])
    assert errors == []
    assert float(clean[0]["shares"]) == 1000
    assert float(clean[0]["purchase_price"]) == 150.25


def test_absurd_share_count_flagged_as_typo():
    clean, errors = validate_holdings([_row(shares="5e12")])
    assert clean == [] and "typo" in errors[0][1]


def test_invalid_date_format_rejected():
    clean, errors = validate_holdings([_row(date="03/15/2022")])
    assert clean == [] and "YYYY-MM-DD" in errors[0][1]


def test_ancient_date_rejected():
    clean, errors = validate_holdings([_row(date="1901-01-01")])
    assert clean == []


def test_error_messages_name_the_row():
    _, errors = validate_holdings([_row(), _row(shares="-1")])
    assert errors[0][1].startswith("Row 2")


def test_holdings_capped():
    rows = [_row(ticker=f"T{i}") for i in range(MAX_HOLDINGS + 5)]
    clean, errors = validate_holdings(rows)
    assert len(clean) == MAX_HOLDINGS
    assert any("first" in m for _, m in errors)


def test_parse_number_edge_cases():
    assert parse_number("") is None
    assert parse_number("  $2,500 ") == 2500
    assert parse_number("nan") is None
