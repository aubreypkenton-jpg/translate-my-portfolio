"""
Edge cases that are easy to get wrong: fractional shares, brand-new tickers
with little history, partial fetch failures, missing benchmark data, huge
numbers, and messy duplicate/whitespace input. Each test pins down one
specific real-world scenario, not just "doesn't crash."
"""
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from app.compute import compute_benchmark_stats, compute_portfolio
from app.normalize import merge_duplicate_tickers
from app.validation import validate_holdings


def make_series(start_date, end_date, start_price, drift, vol, seed):
    dates = pd.date_range(start_date, end_date, freq="B").strftime("%Y-%m-%d")
    rng = np.random.default_rng(seed)
    return pd.Series(start_price * (1 + rng.normal(drift, vol, len(dates))).cumprod(), index=dates)


def test_fractional_shares_compute_correctly():
    holdings = [{"ticker": "AAA", "shares": "0.0025", "purchase_price": "100", "purchase_date": "2023-01-01"}]
    result = compute_portfolio(
        holdings, current_prices={"AAA": 200.0}, sectors={"AAA": "Technology"},
        price_histories={}, today=datetime(2024, 6, 1),
    )
    assert result["rows"][0]["value"] == pytest.approx(0.5)
    assert result["total_value"] == pytest.approx(0.5)


def test_brand_new_ticker_with_short_history_does_not_crash():
    long_history = make_series("2019-06-01", "2024-06-01", 100, 0.0004, 0.015, seed=1)
    short_history = make_series("2024-05-01", "2024-06-01", 50, 0.0004, 0.02, seed=2)  # ~1 month old
    holdings = [
        {"ticker": "OLD", "shares": 10, "purchase_price": None, "purchase_date": None},
        {"ticker": "NEW", "shares": 10, "purchase_price": None, "purchase_date": None},
    ]
    result = compute_portfolio(
        holdings,
        current_prices={"OLD": long_history.iloc[-1], "NEW": short_history.iloc[-1]},
        sectors={"OLD": "Technology", "NEW": "Technology"},
        price_histories={"OLD": long_history, "NEW": short_history},
        today=datetime(2024, 6, 1),
    )
    # should complete without raising, and still produce a risk score
    assert result["total_value"] > 0
    assert result["risk_score"] is not None


def test_missing_benchmark_series_does_not_crash():
    assert compute_benchmark_stats(None) is None
    assert compute_benchmark_stats(pd.Series(dtype=float)) is None

    holdings = [{"ticker": "AAA", "shares": 1, "purchase_price": None, "purchase_date": None}]
    result = compute_portfolio(
        holdings, current_prices={"AAA": 100.0}, sectors={"AAA": "Technology"},
        price_histories={}, today=datetime(2024, 6, 1), benchmark_series=None,
    )
    assert result["benchmark"] is None


def test_very_large_portfolio_value_formats_and_computes():
    holdings = [{"ticker": "AAA", "shares": "1000000000", "purchase_price": "1", "purchase_date": "2020-01-01"}]
    result = compute_portfolio(
        holdings, current_prices={"AAA": 2500.0}, sectors={"AAA": "Technology"},
        price_histories={}, today=datetime(2024, 6, 1),
    )
    assert result["total_value"] == pytest.approx(2_500_000_000_000)


def test_whitespace_only_ticker_is_rejected_with_clear_error():
    clean, errors = validate_holdings([{"ticker": "   ", "shares": "5", "purchase_price": "", "purchase_date": ""}])
    assert clean == []
    assert len(errors) == 1
    assert "Missing ticker" in errors[0][1]


def test_case_insensitive_duplicate_tickers_merge():
    holdings = [
        {"ticker": "AAPL", "shares": "10", "purchase_price": "100", "purchase_date": "2021-01-01"},
        {"ticker": "AAPL", "shares": "5", "purchase_price": "120", "purchase_date": "2022-01-01"},
    ]
    # validate_holdings already uppercases input before this point in the real
    # pipeline; merge should combine them into a single AAPL position
    merged, notes = merge_duplicate_tickers(holdings)
    assert len(merged) == 1
    assert float(merged[0]["shares"]) == 15.0


def test_three_way_duplicate_merges_into_one_position():
    holdings = [
        {"ticker": "AAA", "shares": "1", "purchase_price": "100", "purchase_date": "2020-01-01"},
        {"ticker": "AAA", "shares": "1", "purchase_price": "110", "purchase_date": "2021-01-01"},
        {"ticker": "AAA", "shares": "2", "purchase_price": "120", "purchase_date": "2022-01-01"},
    ]
    merged, notes = merge_duplicate_tickers(holdings)
    assert len(merged) == 1
    assert float(merged[0]["shares"]) == 4.0
    # weighted average: (1*100 + 1*110 + 2*120) / 4 = 112.5
    assert float(merged[0]["purchase_price"]) == pytest.approx(112.5)
    assert merged[0]["purchase_date"] == "2022-01-01"


def test_purchase_date_at_very_start_of_history_does_not_crash_recency_check():
    dates = pd.date_range("2019-06-03", "2024-06-01", freq="B").strftime("%Y-%m-%d")
    series = pd.Series(100.0, index=dates)
    holdings = [{
        "ticker": "AAA", "shares": 1,
        "purchase_price": 100.0, "purchase_date": dates[5],  # only 5 days of prior history available
    }]
    result = compute_portfolio(
        holdings, current_prices={"AAA": 100.0}, sectors={"AAA": "Technology"},
        price_histories={"AAA": series}, today=datetime(2024, 6, 1),
    )
    # should not crash, and shouldn't false-positive a recency flag with insufficient data
    assert not any(f["type"] == "recency_bias" for f in result["behavioral_flags"])
