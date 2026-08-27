"""
All network/yfinance calls live here, isolated from compute.py, and go
through a TTL cache so re-analyzing the same tickers within a few minutes
doesn't re-hit Yahoo Finance for every request.

NOTE: this development sandbox's outbound network can't reach Yahoo Finance,
so this module's live-data path is untested in this environment (see
DECISIONS.md). It uses the standard, widely-used yfinance library (no API
key required), which works normally on Replit/Render/etc, which have normal
outbound internet access. The pure-logic layer (compute.py) is fully tested
against synthetic data instead.
"""
import logging
import time

import pandas as pd
import yfinance as yf

from . import config
from .cache import TTLCache

logger = logging.getLogger(__name__)

_price_cache = TTLCache(config.CACHE_TTL_SECONDS)

FUND_SECTOR_LABELS = {
    "ETF": "Diversified fund (ETF)",
    "MUTUALFUND": "Diversified fund (mutual fund)",
}


def _history_with_retry(tk, attempts=2, backoff_seconds=0.75):
    """Yahoo Finance occasionally has transient blips. One retry is enough
    for a personal-scale tool -- this isn't trying to survive a real outage,
    just a flaky single request."""
    last_error = None
    for attempt in range(attempts):
        try:
            hist = tk.history(period=config.HISTORY_PERIOD, auto_adjust=True)
            if not hist.empty:
                return hist
        except Exception as e:  # noqa: BLE001 -- yfinance raises various types
            last_error = e
        if attempt < attempts - 1:
            time.sleep(backoff_seconds)
    if last_error:
        raise last_error
    return pd.DataFrame()


def _resolve_sector(tk, ticker):
    """Returns a human-readable sector/category label. Funds (ETFs, mutual
    funds) usually have no 'sector' in yfinance's info -- without this,
    every index fund shows up as 'Unknown', which reads like missing data
    rather than what it actually is: a diversified holding."""
    try:
        info = tk.get_info()
    except Exception:
        logger.warning("Could not fetch info for %s", ticker)
        return "Unknown"

    sector = info.get("sector")
    if sector:
        return sector

    quote_type = (info.get("quoteType") or "").upper()
    return FUND_SECTOR_LABELS.get(quote_type, "Unknown")


def _fetch_one(ticker):
    cached = _price_cache.get(ticker)
    if cached is not None:
        return cached

    tk = yf.Ticker(ticker)
    hist = _history_with_retry(tk)
    if hist.empty:
        return None

    closes = hist["Close"]
    closes.index = closes.index.strftime("%Y-%m-%d")

    sector = _resolve_sector(tk, ticker)

    result = {"price_history": closes, "current_price": float(closes.iloc[-1]), "sector": sector}
    _price_cache.set(ticker, result)
    return result


def fetch_holdings_data(tickers):
    """
    tickers: list of ticker strings
    Returns (current_prices, sectors, price_histories, failed) where:
      current_prices: {ticker: float}
      sectors: {ticker: str}
      price_histories: {ticker: pd.Series of daily close, index = 'YYYY-MM-DD' strings}
      failed: [ticker, ...] tickers that couldn't be resolved
    """
    current_prices, sectors, price_histories, failed = {}, {}, {}, []

    for raw in tickers:
        ticker = raw.strip().upper()
        if not ticker:
            continue
        try:
            data = _fetch_one(ticker)
            if data is None:
                failed.append(ticker)
                continue
            current_prices[ticker] = data["current_price"]
            sectors[ticker] = data["sector"]
            price_histories[ticker] = data["price_history"]
        except Exception:
            logger.exception("Failed to fetch %s", ticker)
            failed.append(ticker)

    return current_prices, sectors, price_histories, failed


def fetch_benchmark():
    """Fetch the configured benchmark (default: SPY) as a plain price series."""
    try:
        data = _fetch_one(config.BENCHMARK_TICKER)
        return data["price_history"] if data else None
    except Exception:
        logger.exception("Failed to fetch benchmark %s", config.BENCHMARK_TICKER)
        return None
