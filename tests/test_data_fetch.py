"""
Tests for the retry/fallback logic in data_fetch.py, using a fake yfinance
Ticker instead of the real network (this sandbox can't reach Yahoo Finance;
see DECISIONS.md). These test OUR code's behavior around the yfinance
interface, not yfinance itself.
"""
import pandas as pd
import pytest

import app.data_fetch as data_fetch


class FakeTicker:
    def __init__(self, hist_df, info, fail_times=0):
        self._hist_df = hist_df
        self._info = info
        self._fail_times = fail_times
        self._calls = 0

    def history(self, period=None, auto_adjust=None):
        self._calls += 1
        if self._calls <= self._fail_times:
            raise ConnectionError("simulated transient failure")
        return self._hist_df

    def get_info(self):
        return self._info


def _sample_hist():
    dates = pd.date_range("2023-01-02", periods=10, freq="B")
    return pd.DataFrame({"Close": range(100, 110)}, index=dates)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    # keep the retry test fast -- we're testing the retry happens, not timing
    monkeypatch.setattr(data_fetch.time, "sleep", lambda *_: None)


@pytest.fixture(autouse=True)
def clear_cache():
    data_fetch._price_cache.clear()
    yield
    data_fetch._price_cache.clear()


def test_etf_with_no_sector_gets_fund_label(monkeypatch):
    fake = FakeTicker(_sample_hist(), {"quoteType": "ETF"})
    monkeypatch.setattr(data_fetch.yf, "Ticker", lambda ticker: fake)
    result = data_fetch._fetch_one("SPY")
    assert result["sector"] == "Diversified fund (ETF)"


def test_mutual_fund_with_no_sector_gets_fund_label(monkeypatch):
    fake = FakeTicker(_sample_hist(), {"quoteType": "MUTUALFUND"})
    monkeypatch.setattr(data_fetch.yf, "Ticker", lambda ticker: fake)
    result = data_fetch._fetch_one("VTSAX")
    assert result["sector"] == "Diversified fund (mutual fund)"


def test_regular_stock_with_sector_is_unaffected(monkeypatch):
    fake = FakeTicker(_sample_hist(), {"sector": "Technology", "quoteType": "EQUITY"})
    monkeypatch.setattr(data_fetch.yf, "Ticker", lambda ticker: fake)
    result = data_fetch._fetch_one("AAPL")
    assert result["sector"] == "Technology"


def test_transient_failure_recovers_on_retry(monkeypatch):
    fake = FakeTicker(_sample_hist(), {"sector": "Technology"}, fail_times=1)
    monkeypatch.setattr(data_fetch.yf, "Ticker", lambda ticker: fake)
    result = data_fetch._fetch_one("AAPL")
    assert result is not None
    assert result["current_price"] == 109.0
    assert fake._calls == 2  # failed once, succeeded on retry


def test_persistent_failure_raises(monkeypatch):
    fake = FakeTicker(_sample_hist(), {"sector": "Technology"}, fail_times=5)
    monkeypatch.setattr(data_fetch.yf, "Ticker", lambda ticker: fake)
    with pytest.raises(ConnectionError):
        data_fetch._fetch_one("AAPL")


def test_fetch_holdings_data_skips_unresolvable_ticker(monkeypatch):
    def fake_ticker(ticker):
        if ticker == "GOOD":
            return FakeTicker(_sample_hist(), {"sector": "Technology"})
        return FakeTicker(pd.DataFrame(), {})  # empty history -> unresolved

    monkeypatch.setattr(data_fetch.yf, "Ticker", fake_ticker)
    prices, sectors, histories, failed = data_fetch.fetch_holdings_data(["GOOD", "BAD"])
    assert "GOOD" in prices
    assert "BAD" in failed


# ---- provider errors, negative cache, profiles (added with the deploy fix) ----

class FakeRateLimitError(Exception):
    """Stands in for yfinance's YFRateLimitError (same class-name pattern)."""


FakeRateLimitError.__name__ = "YFRateLimitError"


@pytest.fixture(autouse=True)
def clear_failure_cache():
    data_fetch._failure_cache.clear()
    yield
    data_fetch._failure_cache.clear()


def test_all_tickers_rate_limited_raises_provider_error(monkeypatch):
    class Limited(FakeTicker):
        def history(self, period=None, auto_adjust=None):
            raise FakeRateLimitError("Too Many Requests")

    monkeypatch.setattr(data_fetch.yf, "Ticker", lambda t: Limited(pd.DataFrame(), {}))
    with pytest.raises(data_fetch.DataProviderError):
        data_fetch.fetch_holdings_data(["AAPL", "MSFT"])


def test_network_down_raises_provider_error(monkeypatch):
    monkeypatch.setattr(data_fetch.yf, "Ticker",
                        lambda t: FakeTicker(_sample_hist(), {}, fail_times=99))
    with pytest.raises(data_fetch.DataProviderError):
        data_fetch.fetch_holdings_data(["AAPL"])


def _spy_ok_others_empty(t):
    # Yahoo is healthy (the SPY canary has data) but the user's symbol doesn't exist
    return FakeTicker(_sample_hist() if t == "SPY" else pd.DataFrame(), {})


def test_bad_symbols_alone_do_not_raise_provider_error(monkeypatch):
    monkeypatch.setattr(data_fetch.yf, "Ticker", _spy_ok_others_empty)
    prices, _, _, failed = data_fetch.fetch_holdings_data(["XXXX"])
    assert prices == {} and failed == ["XXXX"]


def test_swallowed_outage_detected_by_canary(monkeypatch):
    # yfinance often logs network errors and returns EMPTY data instead of
    # raising; if SPY is empty too, the provider is down, not the symbols wrong
    monkeypatch.setattr(data_fetch.yf, "Ticker", lambda t: FakeTicker(pd.DataFrame(), {}))
    with pytest.raises(data_fetch.DataProviderError):
        data_fetch.fetch_holdings_data(["AAPL"])
    assert data_fetch._failure_cache.get("AAPL") is None  # outage not remembered as "bad ticker"


def test_unknown_ticker_is_negatively_cached(monkeypatch):
    calls = {"n": 0}

    def make(t):
        if t != "SPY":
            calls["n"] += 1
        return _spy_ok_others_empty(t)

    monkeypatch.setattr(data_fetch.yf, "Ticker", make)
    data_fetch.fetch_holdings_data(["NOPE"])
    data_fetch.fetch_holdings_data(["NOPE"])
    assert calls["n"] == 1  # second request answered from the failure cache


def test_successful_fetch_is_cached(monkeypatch):
    calls = {"n": 0}

    def make(t):
        calls["n"] += 1
        return FakeTicker(_sample_hist(), {"sector": "Technology"})

    monkeypatch.setattr(data_fetch.yf, "Ticker", make)
    data_fetch.fetch_holdings_data(["AAPL"])
    data_fetch.fetch_holdings_data(["aapl "])  # same ticker, messy input
    assert calls["n"] == 1


def test_duplicate_input_tickers_fetched_once(monkeypatch):
    calls = []
    monkeypatch.setattr(data_fetch.yf, "Ticker",
                        lambda t: calls.append(t) or FakeTicker(_sample_hist(), {}))
    data_fetch.fetch_holdings_data(["AAPL", "AAPL", "MSFT"])
    assert sorted(calls) == ["AAPL", "MSFT"]


def test_profile_reads_fund_fields(monkeypatch):
    info = {"quoteType": "ETF", "yield": 0.0125, "dividendYield": 1.25, "netExpenseRatio": 0.03, "shortName": "Some ETF"}
    monkeypatch.setattr(data_fetch.yf, "Ticker", lambda t: FakeTicker(_sample_hist(), info))
    data_fetch.fetch_holdings_data(["VOO"])
    p = data_fetch.get_cached_profiles(["VOO"])["VOO"]
    assert p["asset_class"] == "ETF"
    assert p["dividend_yield_pct"] == pytest.approx(1.25)
    assert p["expense_ratio_pct"] == pytest.approx(0.03)


def test_profile_handles_old_expense_ratio_field_and_percent_yield(monkeypatch):
    info = {"quoteType": "MUTUALFUND", "trailingAnnualDividendYield": 0.018, "annualReportExpenseRatio": 0.0004}
    monkeypatch.setattr(data_fetch.yf, "Ticker", lambda t: FakeTicker(_sample_hist(), info))
    data_fetch.fetch_holdings_data(["VTSAX"])
    p = data_fetch.get_cached_profiles(["VTSAX"])["VTSAX"]
    assert p["dividend_yield_pct"] == pytest.approx(1.8)
    assert p["expense_ratio_pct"] == pytest.approx(0.04)


def test_profile_survives_info_failure(monkeypatch):
    class NoInfo(FakeTicker):
        def get_info(self):
            raise ValueError("info endpoint broke")

    monkeypatch.setattr(data_fetch.yf, "Ticker", lambda t: NoInfo(_sample_hist(), {}))
    prices, sectors, _, failed = data_fetch.fetch_holdings_data(["AAPL"])
    assert "AAPL" in prices and sectors["AAPL"] == "Unknown" and not failed


def test_get_cached_profiles_never_hits_network(monkeypatch):
    def boom(t):
        raise AssertionError("network should not be touched")

    monkeypatch.setattr(data_fetch.yf, "Ticker", boom)
    assert data_fetch.get_cached_profiles(["AAPL"]) == {}


def test_benchmark_returns_none_on_error(monkeypatch):
    monkeypatch.setattr(data_fetch.yf, "Ticker",
                        lambda t: FakeTicker(_sample_hist(), {}, fail_times=99))
    assert data_fetch.fetch_benchmark() is None


def test_is_provider_error_classification():
    assert data_fetch._is_provider_error(ConnectionError())
    assert data_fetch._is_provider_error(TimeoutError())
    assert data_fetch._is_provider_error(FakeRateLimitError())
    assert not data_fetch._is_provider_error(ValueError())


# ---- dividend yield units (bug found on live Yahoo data: AAPL showed 31%) ----

@pytest.mark.parametrize("info,price,expected", [
    ({"dividendYield": 0.41}, 250.0, 0.41),                       # Yahoo's percent field, used as-is
    ({"dividendRate": 1.04, "dividendYield": 0.41}, 260.0, 0.40),  # dollars / price wins
    ({"yield": 0.0115}, 600.0, 1.15),                              # fund fraction field
    ({"trailingAnnualDividendYield": 0.0071}, None, 0.71),
    ({"dividendYield": 99.0}, None, None),                          # implausible -> dropped
    ({}, 100.0, None),
])
def test_dividend_yield_units(info, price, expected):
    got = data_fetch._dividend_yield_pct(info, price)
    if expected is None:
        assert got is None
    else:
        assert got == pytest.approx(expected, abs=0.01)


def test_low_yield_stock_not_inflated_100x(monkeypatch):
    # live AAPL returned dividendYield=0.31 (percent); v1 logic showed 31%
    info = {"quoteType": "EQUITY", "sector": "Technology", "dividendYield": 0.31}
    monkeypatch.setattr(data_fetch.yf, "Ticker", lambda t: FakeTicker(_sample_hist(), info))
    data_fetch.fetch_holdings_data(["AAPL"])
    assert data_fetch.get_cached_profiles(["AAPL"])["AAPL"]["dividend_yield_pct"] == pytest.approx(0.31)
