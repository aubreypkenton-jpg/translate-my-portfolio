"""
Unit tests for the pure computation layer, using synthetic price data with
known, deliberately-engineered properties -- so we can assert on exact
expected behavior rather than just "it didn't crash".
"""
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from app.compute import _cagr, _max_drawdown_pct, compute_portfolio


def make_dates(start="2019-06-01", end="2024-06-01"):
    return pd.date_range(start, end, freq="B").strftime("%Y-%m-%d")


def make_series(dates, start_price, drift, vol, seed):
    rng = np.random.default_rng(seed)
    rets = rng.normal(drift, vol, len(dates))
    return pd.Series(start_price * (1 + rets).cumprod(), index=dates)


@pytest.fixture
def dates():
    return make_dates()


def test_single_holding_weight_is_100_percent(dates):
    series = make_series(dates, 100, 0.0005, 0.01, seed=1)
    holdings = [{"ticker": "AAA", "shares": 10, "purchase_price": None, "purchase_date": None}]
    result = compute_portfolio(
        holdings,
        current_prices={"AAA": series.iloc[-1]},
        sectors={"AAA": "Technology"},
        price_histories={"AAA": series},
        today=datetime(2024, 6, 1),
    )
    assert len(result["rows"]) == 1
    assert result["rows"][0]["weight_pct"] == pytest.approx(100.0)
    assert result["concentration"]["top_ticker"] == "AAA"
    assert result["concentration"]["flagged"] is True  # 100% is well above the 25% cap


def test_concentration_flagged_for_two_way_split(dates):
    # Even a "balanced" 50/50 split is well above the 25% single-holding cap.
    a = make_series(dates, 100, 0.0003, 0.01, seed=2)
    b = make_series(dates, 100, 0.0003, 0.01, seed=3)
    holdings = [
        {"ticker": "AAA", "shares": 10, "purchase_price": None, "purchase_date": None},
        {"ticker": "BBB", "shares": 10, "purchase_price": None, "purchase_date": None},
    ]
    result = compute_portfolio(
        holdings,
        current_prices={"AAA": a.iloc[-1], "BBB": b.iloc[-1]},
        sectors={"AAA": "Technology", "BBB": "Healthcare"},
        price_histories={"AAA": a, "BBB": b},
        today=datetime(2024, 6, 1),
    )
    assert result["concentration"]["flagged"] is True


def test_concentration_not_flagged_when_well_diversified(dates):
    tickers = ["AAA", "BBB", "CCC", "DDD", "EEE"]  # 5 equal holdings -> exactly 20% each
    series = {t: make_series(dates, 100, 0.0003, 0.01, seed=i) for i, t in enumerate(tickers)}
    holdings = [{"ticker": t, "shares": 10, "purchase_price": None, "purchase_date": None} for t in tickers]
    result = compute_portfolio(
        holdings,
        # fix current prices to be exactly equal, independent of each ticker's
        # random walk -- concentration only depends on current value, and this
        # keeps the test deterministic rather than relying on 5 random walks
        # happening to end up close together after 5 years.
        current_prices={t: 100.0 for t in tickers},
        sectors={t: "Technology" if i % 2 == 0 else "Healthcare" for i, t in enumerate(tickers)},
        price_histories=series,
        today=datetime(2024, 6, 1),
    )
    assert result["concentration"]["top_pct"] == pytest.approx(20.0)
    assert result["concentration"]["flagged"] is False


def test_highly_correlated_pair_is_detected(dates):
    a = make_series(dates, 100, 0.0005, 0.02, seed=4)
    # b is a near-copy of a -> should show up as a high-correlation pair
    b = a * (1 + np.random.default_rng(5).normal(0, 0.001, len(a)))
    b = pd.Series(b.values, index=dates)
    holdings = [
        {"ticker": "AAA", "shares": 5, "purchase_price": None, "purchase_date": None},
        {"ticker": "BBB", "shares": 5, "purchase_price": None, "purchase_date": None},
    ]
    result = compute_portfolio(
        holdings,
        current_prices={"AAA": a.iloc[-1], "BBB": b.iloc[-1]},
        sectors={"AAA": "Technology", "BBB": "Technology"},
        price_histories={"AAA": a, "BBB": b},
        today=datetime(2024, 6, 1),
    )
    pairs = {(p[0], p[1]) for p in result["high_corr_pairs"]}
    assert ("AAA", "BBB") in pairs


def test_uncorrelated_holdings_do_not_flag(dates):
    rng_a = np.random.default_rng(10)
    rng_b = np.random.default_rng(99)
    a = pd.Series(100 * (1 + rng_a.normal(0.0003, 0.015, len(dates))).cumprod(), index=dates)
    b = pd.Series(100 * (1 + rng_b.normal(0.0001, 0.005, len(dates))).cumprod(), index=dates)
    holdings = [
        {"ticker": "AAA", "shares": 5, "purchase_price": None, "purchase_date": None},
        {"ticker": "BBB", "shares": 5, "purchase_price": None, "purchase_date": None},
    ]
    result = compute_portfolio(
        holdings,
        current_prices={"AAA": a.iloc[-1], "BBB": b.iloc[-1]},
        sectors={"AAA": "Technology", "BBB": "Fixed Income"},
        price_histories={"AAA": a, "BBB": b},
        today=datetime(2024, 6, 1),
    )
    assert result["high_corr_pairs"] == []


def test_known_crash_window_is_measured_from_real_prices(dates):
    rng = np.random.default_rng(6)
    series = pd.Series(100 * (1 + rng.normal(0.0004, 0.015, len(dates))).cumprod(), index=dates)
    # force an exact, known -40% move across the 2022 bear market window
    mask = (series.index >= "2022-01-03") & (series.index <= "2022-10-12")
    idx = np.where(mask)[0]
    start_val = series.iloc[idx[0]]
    series.iloc[idx] = np.linspace(start_val, start_val * 0.6, len(idx))

    holdings = [{"ticker": "AAA", "shares": 1, "purchase_price": None, "purchase_date": None}]
    result = compute_portfolio(
        holdings,
        current_prices={"AAA": series.iloc[-1]},
        sectors={"AAA": "Technology"},
        price_histories={"AAA": series},
        today=datetime(2024, 6, 1),
    )
    dd = result["drawdown_scenarios"]["2022 bear market"]
    assert dd["estimated_portfolio_change_pct"] == pytest.approx(-40.0, abs=1.0)
    assert dd["coverage_pct"] == pytest.approx(100.0)


def test_recency_bias_flagged_when_bought_after_runup(dates):
    series = pd.Series(100.0, index=dates)
    # flat, then a sharp run-up in the ~35 trading days right before the purchase
    # date, then flat again after -- isolates the run-up instead of ramping
    # across the whole remaining history.
    purchase_idx = dates.get_loc("2021-12-01")
    runup_start_idx = purchase_idx - 35
    series.iloc[runup_start_idx:purchase_idx + 1] = np.linspace(
        100, 130, purchase_idx + 1 - runup_start_idx
    )
    series.iloc[purchase_idx + 1:] = 130.0

    holdings = [{
        "ticker": "AAA", "shares": 1,
        "purchase_price": float(series.loc["2021-12-01"]),
        "purchase_date": "2021-12-01",
    }]
    result = compute_portfolio(
        holdings,
        current_prices={"AAA": series.iloc[-1]},
        sectors={"AAA": "Technology"},
        price_histories={"AAA": series},
        today=datetime(2024, 6, 1),
    )
    flags = [f for f in result["behavioral_flags"] if f["type"] == "recency_bias"]
    assert len(flags) == 1
    assert flags[0]["ticker"] == "AAA"


def test_loss_aversion_flagged_for_old_large_loss():
    holdings = [{
        "ticker": "AAA", "shares": 1, "purchase_price": 100.0, "purchase_date": "2020-01-01",
    }]
    result = compute_portfolio(
        holdings,
        current_prices={"AAA": 70.0},  # -30%
        sectors={"AAA": "Technology"},
        price_histories={"AAA": pd.Series(dtype=float)},
        today=datetime(2024, 6, 1),
    )
    flags = [f for f in result["behavioral_flags"] if f["type"] == "loss_aversion"]
    assert len(flags) == 1


def test_tax_term_short_vs_long():
    holdings = [
        {"ticker": "AAA", "shares": 1, "purchase_price": 100.0, "purchase_date": "2024-05-01"},
        {"ticker": "BBB", "shares": 1, "purchase_price": 100.0, "purchase_date": "2020-01-01"},
    ]
    result = compute_portfolio(
        holdings,
        current_prices={"AAA": 105.0, "BBB": 105.0},
        sectors={"AAA": "Technology", "BBB": "Technology"},
        price_histories={"AAA": pd.Series(dtype=float), "BBB": pd.Series(dtype=float)},
        today=datetime(2024, 6, 1),
    )
    terms = {t["ticker"]: t["term"] for t in result["tax_flags"]}
    assert terms["AAA"] == "short-term"
    assert terms["BBB"] == "long-term"


def test_unresolvable_ticker_is_silently_skipped():
    holdings = [{"ticker": "GHOST", "shares": 1, "purchase_price": None, "purchase_date": None}]
    result = compute_portfolio(
        holdings, current_prices={}, sectors={}, price_histories={}, today=datetime(2024, 6, 1),
    )
    assert result["rows"] == []
    assert result["total_value"] == 0.0


def test_max_drawdown_known_series():
    s = pd.Series([100, 120, 60, 90], index=["a", "b", "c", "d"])
    assert _max_drawdown_pct(s) == pytest.approx(-50.0)


def test_cagr_known_series():
    # exactly doubles over exactly 1 year of trading days -> ~100% CAGR
    dates = pd.date_range("2023-01-01", periods=252, freq="B").strftime("%Y-%m-%d")
    s = pd.Series(np.linspace(100, 200, 252), index=dates)
    assert _cagr(s) == pytest.approx(100.0, rel=0.05)


def test_risk_score_present_and_bounded(dates):
    series = make_series(dates, 100, 0.0005, 0.02, seed=7)
    holdings = [{"ticker": "AAA", "shares": 1, "purchase_price": None, "purchase_date": None}]
    result = compute_portfolio(
        holdings,
        current_prices={"AAA": series.iloc[-1]},
        sectors={"AAA": "Technology"},
        price_histories={"AAA": series},
        today=datetime(2024, 6, 1),
    )
    assert result["risk_score"] is not None
    assert 0 <= result["risk_score"] <= 100
    assert result["risk_label"] in {"Low", "Moderate", "High", "Very High"}


def test_effective_holdings_equal_split_matches_holding_count():
    holdings = [{"ticker": t, "shares": 1, "purchase_price": None, "purchase_date": None} for t in ["A", "B", "C", "D"]]
    result = compute_portfolio(
        holdings,
        current_prices={t: 100.0 for t in ["A", "B", "C", "D"]},
        sectors={t: "Technology" for t in ["A", "B", "C", "D"]},
        price_histories={},
        today=datetime(2024, 6, 1),
    )
    assert result["effective_holdings"] == pytest.approx(4.0)


def test_effective_holdings_drops_when_concentrated():
    # 90/10 split -> HHI = 0.81 + 0.01 = 0.82 -> effective N ~= 1.22
    holdings = [
        {"ticker": "BIG", "shares": 90, "purchase_price": None, "purchase_date": None},
        {"ticker": "SMALL", "shares": 10, "purchase_price": None, "purchase_date": None},
    ]
    result = compute_portfolio(
        holdings,
        current_prices={"BIG": 1.0, "SMALL": 1.0},
        sectors={"BIG": "Technology", "SMALL": "Healthcare"},
        price_histories={},
        today=datetime(2024, 6, 1),
    )
    assert result["effective_holdings"] == pytest.approx(1.22, abs=0.05)
    # sanity check: effective holdings should always be <= actual holdings count
    assert result["effective_holdings"] <= len(result["rows"])
