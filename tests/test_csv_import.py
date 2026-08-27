import io

from app.csv_import import parse_csv


def make_stream(text):
    return io.BytesIO(text.encode("utf-8"))


def test_basic_valid_csv():
    csv_text = "ticker,shares,purchase_price,purchase_date\nAAPL,10,150,2022-01-15\nMSFT,5,250,2021-05-01\n"
    holdings, errors = parse_csv(make_stream(csv_text))
    assert errors == []
    assert len(holdings) == 2
    assert holdings[0]["ticker"] == "AAPL"
    assert holdings[0]["shares"] == "10"


def test_only_required_columns():
    csv_text = "ticker,shares\nAAPL,10\n"
    holdings, errors = parse_csv(make_stream(csv_text))
    assert errors == []
    assert holdings[0]["purchase_price"] == ""
    assert holdings[0]["purchase_date"] == ""


def test_missing_required_column_reports_error():
    csv_text = "symbol_only,shares\nAAPL,10\n"
    # "symbol_only" isn't a recognized alias for ticker -> ticker column missing
    holdings, errors = parse_csv(make_stream(csv_text))
    assert holdings == []
    assert len(errors) == 1
    assert "ticker" in errors[0]


def test_column_aliases_recognized():
    csv_text = "Symbol,Qty,Price Paid,Date Purchased\nAAPL,10,150,2022-01-15\n"
    holdings, errors = parse_csv(make_stream(csv_text))
    assert errors == []
    assert holdings[0]["ticker"] == "AAPL"
    assert holdings[0]["shares"] == "10"
    assert holdings[0]["purchase_price"] == "150"


def test_empty_file():
    holdings, errors = parse_csv(make_stream(""))
    assert holdings == []
    assert "empty" in errors[0].lower()


def test_header_only_no_data_rows():
    csv_text = "ticker,shares\n"
    holdings, errors = parse_csv(make_stream(csv_text))
    assert holdings == []
    assert errors == []  # not an error, just nothing to import


def test_blank_rows_are_skipped():
    csv_text = "ticker,shares\nAAPL,10\n,\nMSFT,5\n"
    holdings, errors = parse_csv(make_stream(csv_text))
    assert len(holdings) == 2


def test_row_limit_enforced():
    rows = "\n".join(f"TICK{i},1" for i in range(250))
    csv_text = f"ticker,shares\n{rows}\n"
    holdings, errors = parse_csv(make_stream(csv_text), max_rows=200)
    assert len(holdings) == 200
    assert len(errors) == 1
    assert "200" in errors[0]


def test_bom_prefixed_csv_still_parses():
    csv_text = "﻿ticker,shares\nAAPL,10\n"
    holdings, errors = parse_csv(make_stream(csv_text))
    assert errors == []
    assert holdings[0]["ticker"] == "AAPL"
