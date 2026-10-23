"""
Flask-level smoke tests. Network calls are mocked out (this environment's
sandbox can't reach Yahoo Finance) so these test routing, validation wiring,
and template rendering -- not live data fetching.
"""
import io

import numpy as np
import pandas as pd
import pytest

import app.routes as routes_module
from app import create_app


def make_history(start=100, seed=1, n=1300):
    dates = pd.date_range("2019-06-01", periods=n, freq="B").strftime("%Y-%m-%d")
    rng = np.random.default_rng(seed)
    return pd.Series(start * (1 + rng.normal(0.0005, 0.015, n)).cumprod(), index=dates)


@pytest.fixture
def client(monkeypatch):
    # rate limiting is disabled for these tests -- see tests/test_rate_limit.py
    # for the dedicated test that exercises the real limiter with enforcement on
    app = create_app(rate_limit_enabled=False)
    app.testing = True

    fake_hist = {"AAPL": make_history(100, 1), "MSFT": make_history(200, 2)}
    fake_prices = {t: s.iloc[-1] for t, s in fake_hist.items()}
    fake_sectors = {"AAPL": "Technology", "MSFT": "Technology"}

    monkeypatch.setattr(routes_module, "fetch_holdings_data",
                         lambda tickers: (fake_prices, fake_sectors, fake_hist, []))
    monkeypatch.setattr(routes_module, "fetch_benchmark", lambda: make_history(400, 3))

    return app.test_client()


def test_index_loads(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"Translate My Portfolio" in r.data


def test_index_has_example_button_and_accessibility_basics(client):
    body = client.get("/").get_data(as_text=True)
    assert 'id="fill-example"' in body
    assert 'aria-label="Ticker symbol"' in body
    assert 'class="skip-link"' in body
    assert 'scope="col"' in body


def test_index_has_social_meta_tags(client):
    body = client.get("/").get_data(as_text=True)
    assert 'property="og:title"' in body
    assert 'name="description"' in body


def test_analyze_result_table_uses_row_headers(client):
    r = client.post("/analyze", data={
        "ticker": ["AAPL"], "shares": ["10"], "purchase_price": [""], "purchase_date": [""],
    })
    body = r.get_data(as_text=True)
    assert 'scope="row"' in body


def test_about_loads(client):
    r = client.get("/about")
    assert r.status_code == 200
    assert b"methodology" in r.data.lower()


def test_analyze_happy_path(client):
    r = client.post("/analyze", data={
        "ticker": ["AAPL", "MSFT"],
        "shares": ["10", "5"],
        "purchase_price": ["150", "250"],
        "purchase_date": ["2022-01-15", "2021-05-01"],
    })
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Overview" in body
    assert "AAPL" in body
    assert "risk-badge" in body  # risk score rendered


def test_analyze_includes_checklist_and_export_hooks(client):
    r = client.post("/analyze", data={
        "ticker": ["AAPL", "MSFT"],
        "shares": ["10", "5"],
        "purchase_price": ["150", "250"],
        "purchase_date": ["2022-01-15", "2021-05-01"],
    })
    body = r.get_data(as_text=True)
    assert 'class="checklist"' in body
    assert 'id="copy-summary-btn"' in body
    assert 'id="download-json-btn"' in body
    assert "SUMMARY_TEXT" in body
    assert "EXPORT_JSON" in body


def test_analyze_with_csv_upload_only(client):
    csv_bytes = b"ticker,shares,purchase_price,purchase_date\nAAPL,10,150,2022-01-15\nMSFT,5,250,2021-05-01\n"
    r = client.post("/analyze", data={
        "ticker": [""], "shares": [""], "purchase_price": [""], "purchase_date": [""],
        "csv_file": (io.BytesIO(csv_bytes), "holdings.csv"),
    }, content_type="multipart/form-data")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Overview" in body
    assert "AAPL" in body
    assert "MSFT" in body


def test_analyze_with_csv_plus_manual_rows_combined(client):
    csv_bytes = b"ticker,shares\nMSFT,5\n"
    r = client.post("/analyze", data={
        "ticker": ["AAPL"], "shares": ["10"], "purchase_price": [""], "purchase_date": [""],
        "csv_file": (io.BytesIO(csv_bytes), "holdings.csv"),
    }, content_type="multipart/form-data")
    body = r.get_data(as_text=True)
    assert "AAPL" in body
    assert "MSFT" in body


def test_analyze_with_bad_csv_shows_friendly_error(client):
    csv_bytes = b"not_a_valid_header\nfoo,bar\n"
    r = client.post("/analyze", data={
        "ticker": [""], "shares": [""], "purchase_price": [""], "purchase_date": [""],
        "csv_file": (io.BytesIO(csv_bytes), "holdings.csv"),
    }, content_type="multipart/form-data")
    assert r.status_code == 200
    assert "missing required column" in r.get_data(as_text=True).lower()


def test_analyze_empty_submission_shows_friendly_error(client):
    r = client.post("/analyze", data={"ticker": [""], "shares": [""], "purchase_price": [""], "purchase_date": [""]})
    assert r.status_code == 200
    assert "Add at least one holding" in r.get_data(as_text=True)


def test_analyze_invalid_row_shows_field_error(client):
    r = client.post("/analyze", data={"ticker": ["AAPL"], "shares": ["-5"], "purchase_price": [""], "purchase_date": [""]})
    assert r.status_code == 200
    assert "positive" in r.get_data(as_text=True)


def test_analyze_unresolvable_ticker(client, monkeypatch):
    monkeypatch.setattr(routes_module, "fetch_holdings_data", lambda tickers: ({}, {}, {}, tickers))
    r = client.post("/analyze", data={"ticker": ["ZZZZFAKE"], "shares": ["1"], "purchase_price": [""], "purchase_date": [""]})
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Couldn" in body  # "Couldn't fetch..." (apostrophe gets HTML-escaped)


def test_analyze_partial_failure_still_analyzes_the_resolvable_ticker(client, monkeypatch):
    # user enters two tickers; one resolves, one doesn't -- the analysis
    # should still run on the one that worked, and clearly list the other as failed
    good_hist = make_history(100, 1)

    def partial_fetch(tickers):
        return ({"AAPL": good_hist.iloc[-1]}, {"AAPL": "Technology"}, {"AAPL": good_hist}, ["ZZZZFAKE"])

    monkeypatch.setattr(routes_module, "fetch_holdings_data", partial_fetch)
    r = client.post("/analyze", data={
        "ticker": ["AAPL", "ZZZZFAKE"],
        "shares": ["10", "5"],
        "purchase_price": ["", ""],
        "purchase_date": ["", ""],
    })
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Overview" in body  # analysis still ran
    assert "ZZZZFAKE" in body  # and the failure is surfaced
    assert "AAPL" in body
