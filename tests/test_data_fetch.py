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
