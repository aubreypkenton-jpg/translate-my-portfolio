"""Tests for the finance-correctness pass: each one pins down a specific
formula or rule with an answer worked out by hand."""
import math
from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest

from app.compute import (
    _beta,
    _cagr,
    _daily_risk_free,
    _sharpe,
    _sortino,
    compute_portfolio,
    compute_rebalance,
    holding_term,
)
from app.explain import build_explanations


def bdays(start, n):
    return pd.date_range(start, periods=n, freq="B").strftime("%Y-%m-%d")


def series(start, n, seed, drift=0.0004, vol=0.012, base=100.0):
    rng = np.random.default_rng(seed)
    return pd.Series(base * (1 + rng.normal(drift, vol, n)).cumprod(), index=bdays(start, n))


def holding(t, shares=1, price=None, d=None):
    return {"ticker": t, "shares": shares, "purchase_price": price, "purchase_date": d}


# ---------------- tax: IRS "more than one year" rule ----------------

def test_exactly_one_year_is_still_short_term():
    assert holding_term(date(2023, 1, 10), date(2024, 1, 10))[0] == "short-term"


def test_one_year_and_one_day_is_long_term():
    assert holding_term(date(2023, 1, 10), date(2024, 1, 11)) == ("long-term", None)


def test_days_until_long_term_counts_down():
    term, days = holding_term(date(2024, 1, 10), date(2024, 12, 31))
    assert term == "short-term" and days == 11  # long-term starting 2025-01-11


def test_leap_day_purchase():
    assert holding_term(date(2024, 2, 29), date(2025, 2, 28))[0] == "short-term"
    assert holding_term(date(2024, 2, 29), date(2025, 3, 1))[0] == "long-term"


def test_365_days_in_non_leap_year_is_short_term():
    # the old code used ">= 365 days", which got this wrong
    r = compute_portfolio([holding("A", 1, 100.0, "2023-03-01")], {"A": 120.0}, {}, {},
                          today=datetime(2024, 2, 29))
    assert r["tax_flags"][0]["holding_days"] == 365
    assert r["tax_flags"][0]["term"] == "short-term"


def test_tax_flags_know_gain_vs_loss_and_totals():
    r = compute_portfolio(
        [holding("UP", 10, 100.0, "2020-01-02"), holding("DOWN", 10, 100.0, "2024-05-01")],
        {"UP": 150.0, "DOWN": 80.0}, {}, {}, today=datetime(2024, 6, 1))
    flags = {f["ticker"]: f for f in r["tax_flags"]}
    assert flags["UP"]["status"] == "gain" and flags["UP"]["unrealized_gain"] == pytest.approx(500)
    assert flags["DOWN"]["status"] == "loss" and flags["DOWN"]["unrealized_gain"] == pytest.approx(-200)
    assert r["tax_summary"]["long_term_gain"] == pytest.approx(500)
    assert r["tax_summary"]["short_term_loss"] == pytest.approx(-200)


def test_tax_text_for_loss_does_not_talk_about_gains():
    r = compute_portfolio([holding("DOWN", 10, 100.0, "2024-05-01")], {"DOWN": 80.0}, {}, {},
                          today=datetime(2024, 6, 1))
    tax = " ".join(build_explanations(r)["tax"])
    assert "short-term capital loss" in tax
    assert "wash-sale" in tax
    assert "$200 loss" in tax and "-$" not in tax.split("If you sold everything")[0]
    assert "not tax advice" in tax


# ---------------- Sharpe / Sortino / beta ----------------

def test_daily_risk_free_compounds_to_annual():
    assert (1 + _daily_risk_free(0.05)) ** 252 == pytest.approx(1.05)


def test_sharpe_matches_textbook_formula():
    rng = np.random.default_rng(0)
    r = rng.normal(0.0006, 0.01, 1000)
    rf = 0.03
    expected = (r - _daily_risk_free(rf)).mean() / r.std(ddof=1) * math.sqrt(252)
    assert _sharpe(r, rf) == pytest.approx(expected)


def test_higher_risk_free_rate_lowers_sharpe():
    r = np.random.default_rng(1).normal(0.0005, 0.01, 500)
    assert _sharpe(r, 0.0) > _sharpe(r, 0.05)


def test_sharpe_none_for_flat_or_short_series():
    assert _sharpe(np.zeros(100), 0.04) is None
    assert _sharpe(np.array([0.01, 0.02]), 0.04) is None


def test_sortino_ignores_upside_volatility():
    # same mean; second series has much bigger UP days only -> Sortino unchanged-ish, Sharpe drops
    base = np.array([0.01, -0.01] * 200)
    spiky = base.copy()
    spiky[::2] = 0.03
    spiky[1::2] = -0.01
    assert _sortino(spiky, 0.0) > _sortino(base, 0.0)


def test_beta_of_levered_copy_is_two():
    b = series("2022-01-03", 300, seed=3).pct_change().dropna()
    assert _beta(2 * b, b) == pytest.approx(2.0)


def test_beta_needs_enough_overlap():
    b = series("2022-01-03", 10, seed=3).pct_change().dropna()
    assert _beta(b, b) is None


# ---------------- CAGR / benchmark alignment ----------------

def test_portfolio_index_starts_at_one_so_no_day_is_lost():
    s = pd.Series([100.0, 110.0], index=["2024-01-02", "2024-01-03"])
    r = compute_portfolio([holding("A")], {"A": 110.0}, {}, {"A": s}, today=datetime(2024, 1, 4))
    assert r["portfolio_index"].iloc[0] == 1.0
    assert r["portfolio_index"].iloc[-1] == pytest.approx(1.10)


def test_cagr_doubling_over_two_trading_years():
    s = pd.Series(np.linspace(100, 200, 505), index=bdays("2020-01-01", 505))
    assert _cagr(s) == pytest.approx((2 ** 0.5 - 1) * 100, rel=1e-6)


def test_benchmark_compared_over_same_window_as_portfolio():
    spy = series("2019-01-02", 1500, seed=10)
    young = series("2023-06-01", 200, seed=11)  # recent IPO: only ~200 days of history
    r = compute_portfolio([holding("NEW", 1)], {"NEW": young.iloc[-1]}, {}, {"NEW": young},
                          today=datetime(2024, 6, 1), benchmark_series=spy)
    assert r["benchmark"]["start_date"] == r["analysis_window"]["start"] == "2023-06-01"
    assert r["benchmark"]["end_date"] == r["analysis_window"]["end"]


def test_portfolio_identical_to_benchmark_matches_it():
    spy = series("2021-01-04", 600, seed=12)
    r = compute_portfolio([holding("SPY", 3)], {"SPY": spy.iloc[-1]}, {}, {"SPY": spy},
                          today=datetime(2024, 6, 1), benchmark_series=spy)
    assert r["portfolio_cagr"] == pytest.approx(r["benchmark"]["cagr_pct"])
    assert r["portfolio_vol"] == pytest.approx(r["benchmark"]["annualized_vol_pct"])
    assert r["beta"] == pytest.approx(1.0)


def test_risk_free_rate_input_flows_through():
    s = series("2021-01-04", 600, seed=13)
    lo = compute_portfolio([holding("A")], {"A": s.iloc[-1]}, {}, {"A": s}, risk_free_rate=0.0)
    hi = compute_portfolio([holding("A")], {"A": s.iloc[-1]}, {}, {"A": s}, risk_free_rate=0.08)
    assert lo["sharpe_ratio"] > hi["sharpe_ratio"]
    assert hi["risk_free_rate_pct"] == pytest.approx(8.0)
    assert "8.00% risk-free rate" in " ".join(build_explanations(hi)["volatility"])


# ---------------- crash wording / correlation wording ----------------

def _with_scenario(pct, bench=None):
    r = compute_portfolio([holding("A")], {"A": 1.0}, {}, {})
    r["drawdown_scenarios"] = {"2022 bear market": {"estimated_portfolio_change_pct": pct,
                                                    "coverage_pct": 100.0, "details": [],
                                                    "benchmark_change_pct": bench}}
    return " ".join(build_explanations(r)["drawdown"])


def test_crash_text_says_risen_when_portfolio_went_up():
    text = _with_scenario(7.0)
    assert "risen about 7%" in text and "fallen" not in text.split("What happened")[0]


def test_crash_text_says_fallen_and_compares_to_spy():
    text = _with_scenario(-30.0, bench=-25.0)
    assert "fallen about 30%" in text and "S&P 500 (SPY) fell 25%." in text


def test_crash_scenario_includes_spy_change():
    dates = bdays("2021-06-01", 600)
    s = pd.Series(np.linspace(100, 50, 600), index=dates)
    r = compute_portfolio([holding("A")], {"A": 50.0}, {}, {"A": s}, benchmark_series=s)
    sc = r["drawdown_scenarios"]["2022 bear market"]
    assert sc["benchmark_change_pct"] == pytest.approx(sc["estimated_portfolio_change_pct"])


def test_correlation_text_does_not_claim_percent_of_time():
    r = compute_portfolio([holding("A")], {"A": 1.0}, {}, {})
    r["high_corr_pairs"] = [("AAA", "BBB", 0.85)]
    text = " ".join(build_explanations(r)["correlation"])
    assert "of the time" not in text
    assert "correlation of 0.85" in text


# ---------------- concentration / funds ----------------

def test_index_fund_is_not_flagged_as_sector_concentration():
    r = compute_portfolio([holding("VOO")], {"VOO": 500.0}, {"VOO": "Diversified fund (ETF)"}, {})
    assert r["flagged_sectors"] == {}


def test_asset_class_mix_and_fund_flags():
    profiles = {
        "AAPL": {"asset_class": "Individual stock"},
        "VOO": {"asset_class": "ETF", "expense_ratio_pct": 0.03, "dividend_yield_pct": 1.3},
        "PRICY": {"asset_class": "Mutual fund", "expense_ratio_pct": 1.10},
        "JUNK": {"asset_class": "ETF", "expense_ratio_pct": 0.4, "dividend_yield_pct": 9.0},
    }
    r = compute_portfolio([holding(t) for t in profiles], {t: 100.0 for t in profiles}, {}, {},
                          profiles=profiles)
    assert r["asset_class_pct"] == {"Individual stock": 25.0, "ETF": 50.0, "Mutual fund": 25.0}
    types = {(f["ticker"], f["type"]) for f in r["fund_flags"]}
    assert ("PRICY", "high_expense_ratio") in types
    assert ("JUNK", "high_dividend_yield") in types
    assert ("VOO", "high_expense_ratio") not in types
    # value-weighted ER across the three funds: (0.03 + 1.10 + 0.40) / 3
    assert r["weighted_expense_ratio_pct"] == pytest.approx(0.51)
    assert r["annual_fee_dollars"] == pytest.approx(1.53)
    funds_text = " ".join(build_explanations(r)["funds"])
    assert "PRICY" in funds_text and "expense ratio" in funds_text


def test_all_single_stocks_gets_a_note():
    profiles = {t: {"asset_class": "Individual stock"} for t in ("A", "B")}
    r = compute_portfolio([holding("A"), holding("B")], {"A": 1.0, "B": 1.0}, {}, {}, profiles=profiles)
    assert any("individual stocks" in line for line in build_explanations(r)["concentration"])


def test_hhi_reported():
    r = compute_portfolio([holding("A", 3), holding("B", 1)], {"A": 1.0, "B": 1.0}, {}, {})
    assert r["hhi"] == pytest.approx(0.625)  # .75^2 + .25^2


# ---------------- rebalance ----------------

def _two_asset():
    a = series("2019-06-03", 1300, seed=21, vol=0.03)   # volatile stock
    b = series("2019-06-03", 1300, seed=22, vol=0.004)  # calm bond-like fund
    prices = {"A": a.iloc[-1], "B": b.iloc[-1]}
    hist = {"A": a, "B": b}
    current = compute_portfolio([holding("A", 900 / prices["A"]), holding("B", 100 / prices["B"])],
                                prices, {}, hist, today=datetime(2024, 6, 1))
    return current, prices, hist


def test_rebalance_trades_add_up():
    current, prices, hist = _two_asset()
    rb = compute_rebalance(current, {"A": 50.0, "B": 50.0}, prices, {}, hist, today=datetime(2024, 6, 1))
    trades = {t["ticker"]: t for t in rb["trades"]}
    assert trades["A"]["action"] == "sell" and trades["A"]["amount"] == pytest.approx(400, rel=1e-6)
    assert trades["B"]["action"] == "buy" and trades["B"]["amount"] == pytest.approx(400, rel=1e-6)
    assert rb["target"]["total_value"] == pytest.approx(current["total_value"])


def test_rebalance_toward_calm_asset_lowers_volatility():
    current, prices, hist = _two_asset()
    rb = compute_rebalance(current, {"A": 50.0, "B": 50.0}, prices, {}, hist)
    vol = rb["comparison"]["portfolio_vol"]
    assert vol["target"] < vol["current"]
    assert rb["comparison"]["top_pct"]["target"] == pytest.approx(50.0)


def test_rebalance_warns_on_selling_short_term_gain():
    s = series("2023-01-02", 400, seed=30)
    prices = {"A": s.iloc[-1], "B": 50.0}
    hist = {"A": s, "B": pd.Series(50.0, index=s.index)}
    current = compute_portfolio([holding("A", 10, float(s.iloc[-1]) * 0.5, "2024-04-01"), holding("B", 1)],
                                prices, {}, hist, today=datetime(2024, 6, 1))
    rb = compute_rebalance(current, {"A": 10.0, "B": 90.0}, prices, {}, hist, today=datetime(2024, 6, 1))
    sell_a = next(t for t in rb["trades"] if t["ticker"] == "A")
    assert sell_a["short_term_gain_warning"] is True


def test_rebalance_can_drop_a_holding():
    current, prices, hist = _two_asset()
    rb = compute_rebalance(current, {"A": 0.0, "B": 100.0}, prices, {}, hist)
    assert [r["ticker"] for r in rb["target"]["rows"]] == ["B"]
