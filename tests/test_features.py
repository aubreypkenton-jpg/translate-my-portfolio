"""Web-layer tests for the features added in the improvement pass: risk-free
rate input, rebalance tool, examples, methodology page, chart data, safe
JSON embedding, and template filters."""
import numpy as np
import pandas as pd
import pytest

import app.routes as routes_module
from app import config, create_app
from app.chart_data import _thin, build_chart_data
from app.compute import compute_portfolio
from app.examples import EXAMPLE_PORTFOLIOS
from app.formatting import clean_num, money, num, pct
from app.validation import parse_risk_free_rate, validate_targets


def hist(seed, n=900, vol=0.015):
    dates = pd.date_range("2022-01-03", periods=n, freq="B").strftime("%Y-%m-%d")
    rng = np.random.default_rng(seed)
    return pd.Series(100 * (1 + rng.normal(0.0004, vol, n)).cumprod(), index=dates)


H = {"AAPL": hist(1), "VOO": hist(2, vol=0.01), "SPY": hist(3, vol=0.01)}


@pytest.fixture
def client(monkeypatch):
    app = create_app(rate_limit_enabled=False)
    app.testing = True
    monkeypatch.setattr(routes_module, "fetch_holdings_data", lambda ts: (
        {t: float(H[t].iloc[-1]) for t in ts if t in H},
        {"AAPL": "Technology", "VOO": "Diversified fund (ETF)", "SPY": "Diversified fund (ETF)"},
        {t: H[t] for t in ts if t in H}, [t for t in ts if t not in H]))
    monkeypatch.setattr(routes_module, "fetch_benchmark", lambda: H["SPY"])
    monkeypatch.setattr(routes_module, "get_cached_profiles", lambda ts: {
        "AAPL": {"asset_class": "Individual stock"},
        "VOO": {"asset_class": "ETF", "expense_ratio_pct": 0.03, "dividend_yield_pct": 1.3}})
    return app.test_client()


def post(client, **extra):
    data = {"ticker": ["AAPL", "VOO"], "shares": ["10", "5"], "purchase_price": ["", ""],
            "purchase_date": ["", ""]}
    data.update(extra)
    return client.post("/analyze", data=data)


# ---- risk-free rate ----

def test_custom_risk_free_rate_is_used(client):
    body = post(client, risk_free_rate="5.25").get_data(as_text=True)
    assert "5.25% risk-free rate" in body
    assert 'value="5.25"' in body  # remembered in the form


def test_bad_risk_free_rate_falls_back_with_message(client):
    body = post(client, risk_free_rate="abc").get_data(as_text=True)
    assert "Risk-free rate must be a percent" in body
    assert "Overview" in body  # analysis still ran


@pytest.mark.parametrize("raw,expected", [("", 0.04), ("4.5", 0.045), ("3%", 0.03), ("0", 0.0)])
def test_parse_risk_free_rate(raw, expected):
    rate, err = parse_risk_free_rate(raw, 0.04, 0.20)
    assert err is None and rate == pytest.approx(expected)


@pytest.mark.parametrize("raw", ["-1", "25", "nan", "x"])
def test_parse_risk_free_rate_rejects(raw):
    rate, err = parse_risk_free_rate(raw, 0.04, 0.20)
    assert err and rate == 0.04


# ---- rebalance ----

def test_rebalance_flow_renders_trades_and_comparison(client):
    r = post(client, rebalance="1", target_ticker=["AAPL", "VOO"], target_pct=["50", "50"])
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert 'id="rebalance-results"' in body
    assert "Trades to get there" in body and "Before vs. after" in body


def test_rebalance_sum_not_100_shows_error(client):
    body = post(client, rebalance="1", target_ticker=["AAPL", "VOO"], target_pct=["60", "60"]).get_data(as_text=True)
    assert "add up to 120.0%" in body
    assert 'id="rebalance-results"' not in body
    assert "Overview" in body  # main analysis still shown


def test_rebalance_unknown_ticker_rejected(client):
    body = post(client, rebalance="1", target_ticker=["AAPL", "TSLA"], target_pct=["50", "50"]).get_data(as_text=True)
    assert "not in this portfolio" in body


@pytest.mark.parametrize("pcts,msg", [
    (["-10", "110"], "can't be negative"),
    (["150", "-50"], "can't be negative"),
    (["abc", "100"], "must be a number"),
    (["0", "0"], "at least one holding"),
    (["101", "0"], "more than 100%"),
])
def test_validate_targets_errors(pcts, msg):
    targets, errors = validate_targets(["A", "B"], pcts, 0.5)
    assert targets is None and any(msg in e for e in errors)


def test_validate_targets_ok_with_tolerance_and_blank():
    targets, errors = validate_targets(["A", "B", "C"], ["33.3", "66.4", ""], 0.5)
    assert errors == [] and targets == {"A": 33.3, "B": 66.4, "C": 0.0}


def test_validate_targets_duplicate():
    targets, errors = validate_targets(["A", "a"], ["50", "50"], 0.5)
    assert targets is None and "twice" in errors[0]


# ---- pages, examples, assets ----

def test_examples_rendered_and_embedded(client):
    body = client.get("/").get_data(as_text=True)
    for ex in EXAMPLE_PORTFOLIOS:
        assert f'data-example="{ex["id"]}"' in body
    assert "window.EXAMPLES" in body


def test_example_tickers_pass_validation():
    from app.validation import validate_holdings
    for ex in EXAMPLE_PORTFOLIOS:
        clean, errors = validate_holdings(ex["holdings"])
        assert errors == [] and len(clean) == len(ex["holdings"]), ex["id"]


def test_methodology_page_has_formulas_and_disclaimers(client):
    for path in ("/methodology", "/about"):
        body = client.get(path).get_data(as_text=True)
        for needle in ("Herfindahl", "Sharpe", "Sortino", "beta =", "more than one year",
                       "IRS Publication 550", "not tax advice", "Educational only", "Limitations"):
            assert needle in body, needle


def test_every_page_has_not_advice_footer(client):
    for path in ("/", "/methodology"):
        assert "not investment, tax, or legal advice" in client.get(path).get_data(as_text=True)


def test_vendored_chartjs_served(client):
    r = client.get("/static/vendor/chart-4.4.4.umd.js")
    assert r.status_code == 200 and len(r.data) > 100_000


def test_results_page_loads_charts_locally_not_from_cdn(client):
    body = post(client).get_data(as_text=True)
    assert "vendor/chart-4.4.4.umd.js" in body
    assert "cdn.jsdelivr" not in body


def test_script_injection_in_data_is_escaped(client, monkeypatch):
    # a malicious sector name from the data source must not break out of <script>
    evil = "</script><script>alert(1)</script>"
    monkeypatch.setattr(routes_module, "fetch_holdings_data", lambda ts: (
        {"AAPL": 100.0}, {"AAPL": evil}, {"AAPL": H["AAPL"]}, []))
    body = post(client, ticker=["AAPL"], shares=["1"], purchase_price=[""], purchase_date=[""]).get_data(as_text=True)
    assert "<script>alert(1)</script>" not in body


def test_form_is_refilled_after_analysis(client):
    body = post(client).get_data(as_text=True)
    assert 'value="AAPL"' in body and 'value="10"' in body


# ---- chart data ----

def test_chart_data_growth_and_drawdown_aligned():
    r = compute_portfolio([{"ticker": "AAPL", "shares": 1, "purchase_price": None, "purchase_date": None}],
                          {"AAPL": float(H["AAPL"].iloc[-1])}, {}, {"AAPL": H["AAPL"]},
                          benchmark_series=H["SPY"])
    d = build_chart_data(r)
    g, dd = d["growth"], d["drawdown"]
    assert len(g["dates"]) == len(g["portfolio"]) == len(g["benchmark"]) == len(dd["portfolio"])
    assert len(g["dates"]) <= 401
    assert g["portfolio"][0] == pytest.approx(10000) and g["benchmark"][0] == pytest.approx(10000)
    assert max(dd["portfolio"]) <= 0 and g["dates"][-1] == H["AAPL"].index[-1]


def test_chart_data_without_history_is_empty_but_valid():
    r = compute_portfolio([{"ticker": "X", "shares": 1, "purchase_price": None, "purchase_date": None}],
                          {"X": 10.0}, {}, {})
    d = build_chart_data(r)
    assert d["growth"]["dates"] == [] and d["allocation"]["labels"] == ["X"]


def test_thin_keeps_last_point():
    s = pd.Series(range(1001))
    t = _thin(s, 100)
    assert len(t) <= 101 and t.iloc[-1] == 1000


# ---- filters ----

def test_formatting_filters():
    assert pct(None) == "–" and pct(12.345) == "12.3%" and pct(5, 0, signed=True) == "+5%"
    assert money(-1234.4) == "-$1,234" and money(10, signed=True) == "+$10" and money(None) == "–"
    assert num(1.234, 1) == "1.2" and num(None) == "–"
    assert clean_num("10.0") == "10" and clean_num(None) == "" and clean_num("abc") == "abc"


def test_config_defaults_sane():
    assert 0 <= config.RISK_FREE_RATE <= config.RISK_FREE_RATE_MAX
