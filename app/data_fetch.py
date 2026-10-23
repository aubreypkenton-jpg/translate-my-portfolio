"""
The ONLY module in the app that touches the internet (Yahoo Finance via the
free ``yfinance`` library; no API key).

Everything goes through an in-memory TTL cache, so re-analyzing the same
tickers within a few minutes doesn't re-hit Yahoo. Tickers are fetched in
parallel (a small thread pool) so an 8-ticker portfolio doesn't take 8x as
long as a 1-ticker one.

Failure handling, in plain terms:
  * A ticker Yahoo has no data for (a typo, a delisted company) is reported
    back in ``failed`` and remembered for a few minutes ("negative cache"), so
    a user re-submitting the same typo doesn't trigger fresh network calls.
  * A *provider* problem (Yahoo rate-limiting us, or the network being down)
    is different: it's not the user's fault. If every ticker fails for that
    reason, :class:`DataProviderError` is raised so the web layer can show a
    "try again in a minute" message instead of "check your symbols".

NOTE: the development sandbox this was built in can't reach Yahoo Finance, so
this module is tested against a fake ``yf.Ticker`` (tests/test_data_fetch.py).
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pandas as pd
import yfinance as yf

from . import config
from .cache import TTLCache

logger = logging.getLogger(__name__)

_price_cache = TTLCache(config.CACHE_TTL_SECONDS)
_failure_cache = TTLCache(config.FAILED_TICKER_TTL_SECONDS)

FUND_SECTOR_LABELS = {
    "ETF": "Diversified fund (ETF)",
    "MUTUALFUND": "Diversified fund (mutual fund)",
}

# Maps Yahoo's quoteType to the asset-class label shown to the user.
ASSET_CLASS_LABELS = {
    "EQUITY": "Individual stock",
    "ETF": "ETF",
    "MUTUALFUND": "Mutual fund",
    "CRYPTOCURRENCY": "Crypto",
    "INDEX": "Index",
}


class DataProviderError(Exception):
    """Raised when market data can't be fetched because of the provider
    (rate limit, outage, no network), not because of the user's input."""


def _is_provider_error(exc: BaseException) -> bool:
    """True for errors that mean "Yahoo/network is the problem".

    yfinance raises ``YFRateLimitError`` when Yahoo throttles us; network
    failures surface as ConnectionError/TimeoutError or as a curl/requests
    exception whose class name says so. Anything else (e.g. a malformed
    response for one obscure ticker) is treated as a per-ticker failure.
    """
    rate_limit_cls = getattr(getattr(yf, "exceptions", None), "YFRateLimitError", None)
    if rate_limit_cls is not None and isinstance(exc, rate_limit_cls):
        return True
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return True
    name = type(exc).__name__.lower()
    return any(word in name for word in ("ratelimit", "connection", "timeout", "proxy"))


def _history_with_retry(tk: Any, attempts: int = config.FETCH_ATTEMPTS,
                        backoff_seconds: float = config.FETCH_BACKOFF_SECONDS) -> pd.DataFrame:
    """Fetch daily history, retrying transient errors with exponential backoff.

    Returns an empty DataFrame if Yahoo simply has no data for the symbol.
    Re-raises the last error if every attempt raised.
    """
    last_error: BaseException | None = None
    for attempt in range(attempts):
        try:
            hist = tk.history(period=config.HISTORY_PERIOD, auto_adjust=True)
            if hist is not None and not hist.empty:
                return hist
            last_error = None  # empty, not an error: an unknown ticker
        except Exception as e:  # noqa: BLE001 -- yfinance raises many types
            last_error = e
        if attempt < attempts - 1:
            time.sleep(backoff_seconds * (2 ** attempt))
    if last_error:
        raise last_error
    return pd.DataFrame()


def _safe_float(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f else None  # filters NaN


def _resolve_profile(tk: Any, ticker: str) -> dict[str, Any]:
    """Sector, asset class, and fund facts (dividend yield, expense ratio).

    Funds usually have no 'sector' in Yahoo's data; without the fallback
    label every index fund would show up as 'Unknown', which reads like
    missing data rather than what it is: a diversified holding.

    Yahoo's field names for yield and expense ratio have changed across
    yfinance versions, so several known spellings are tried. Yield fields
    are normalized to a percentage (Yahoo has returned both 0.013 and 1.3).
    """
    try:
        info = tk.get_info() or {}
    except Exception:  # noqa: BLE001
        logger.warning("Could not fetch info for %s", ticker)
        info = {}

    quote_type = (info.get("quoteType") or "").upper()
    sector = info.get("sector") or FUND_SECTOR_LABELS.get(quote_type, "Unknown")

    dividend_yield = None
    for key in ("dividendYield", "yield", "trailingAnnualDividendYield"):
        v = _safe_float(info.get(key))
        if v is not None:
            # Values <= 1 are fractions (0.013 = 1.3%); larger are already %.
            dividend_yield = v * 100.0 if v <= 1 else v
            break

    expense_ratio = None
    for key in ("netExpenseRatio", "annualReportExpenseRatio", "expenseRatio"):
        v = _safe_float(info.get(key))
        if v is not None:
            # netExpenseRatio is already a percent (0.03 = 0.03%); the older
            # annualReportExpenseRatio was a fraction (0.0003).
            expense_ratio = v if key == "netExpenseRatio" else v * 100.0
            break

    return {
        "sector": sector,
        "quote_type": quote_type or None,
        "asset_class": ASSET_CLASS_LABELS.get(quote_type, "Other / unknown"),
        "dividend_yield_pct": dividend_yield,
        "expense_ratio_pct": expense_ratio,
        "name": info.get("shortName") or info.get("longName"),
    }


def _fetch_one(ticker: str) -> dict[str, Any] | None:
    """Fetch (or return cached) data for one ticker; None if Yahoo has none."""
    cached = _price_cache.get(ticker)
    if cached is not None:
        return cached
    if _failure_cache.get(ticker):
        return None

    tk = yf.Ticker(ticker)
    hist = _history_with_retry(tk)
    if hist.empty:
        _failure_cache.set(ticker, True)
        return None

    closes = hist["Close"].copy()
    closes.index = pd.to_datetime(closes.index).strftime("%Y-%m-%d")

    profile = _resolve_profile(tk, ticker)
    result = {"price_history": closes, "current_price": float(closes.iloc[-1]), **profile}
    _price_cache.set(ticker, result)
    return result


def _normalize(tickers: list[str]) -> list[str]:
    seen: list[str] = []
    for raw in tickers:
        t = raw.strip().upper()
        if t and t not in seen:
            seen.append(t)
    return seen


def fetch_holdings_data(
    tickers: list[str],
) -> tuple[dict[str, float], dict[str, str], dict[str, pd.Series], list[str]]:
    """Fetch prices for several tickers in parallel.

    Returns ``(current_prices, sectors, price_histories, failed)``:
      * current_prices: {ticker: latest close}
      * sectors: {ticker: sector or fund label}
      * price_histories: {ticker: Series of daily closes, index 'YYYY-MM-DD'}
      * failed: tickers that couldn't be resolved

    Raises :class:`DataProviderError` if *every* ticker failed because of a
    provider/network problem (as opposed to bad symbols).
    """
    symbols = _normalize(tickers)
    current_prices: dict[str, float] = {}
    sectors: dict[str, str] = {}
    price_histories: dict[str, pd.Series] = {}
    failed: list[str] = []
    provider_errors = 0

    def task(sym: str) -> tuple[str, dict[str, Any] | None, BaseException | None]:
        try:
            return sym, _fetch_one(sym), None
        except Exception as e:  # noqa: BLE001
            return sym, None, e

    if symbols:
        workers = min(config.FETCH_MAX_WORKERS, len(symbols))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            outcomes = list(pool.map(task, symbols))
    else:
        outcomes = []

    for sym, data, err in outcomes:
        if err is not None:
            if _is_provider_error(err):
                provider_errors += 1
                logger.warning("Provider error fetching %s: %s", sym, err)
            else:
                logger.exception("Failed to fetch %s", sym, exc_info=err)
            failed.append(sym)
            continue
        if data is None:
            failed.append(sym)
            continue
        current_prices[sym] = data["current_price"]
        sectors[sym] = data["sector"]
        price_histories[sym] = data["price_history"]

    if symbols and not current_prices:
        if provider_errors > 0 or not _provider_is_healthy():
            # Don't let an outage get remembered as "these tickers don't exist".
            for sym in symbols:
                _failure_cache.delete(sym)
            raise DataProviderError("Market data provider unavailable")

    return current_prices, sectors, price_histories, failed


def _provider_is_healthy() -> bool:
    """Canary check, used only when *every* requested ticker came back empty.

    yfinance often logs network errors and returns an empty table instead of
    raising, which looks identical to a mistyped ticker. The benchmark (SPY)
    always has data, so if it also comes back empty the provider is the
    problem, not the user's input.
    """
    try:
        return _fetch_one(config.BENCHMARK_TICKER) is not None
    except Exception:  # noqa: BLE001
        return False
    finally:
        _failure_cache.delete(config.BENCHMARK_TICKER)


def get_cached_profiles(tickers: list[str]) -> dict[str, dict[str, Any]]:
    """Asset class / fund facts for tickers already fetched. Never hits the
    network: it only reads what :func:`fetch_holdings_data` cached."""
    out: dict[str, dict[str, Any]] = {}
    for t in _normalize(tickers):
        data = _price_cache.get(t)
        if data is not None:
            out[t] = {k: data.get(k) for k in
                      ("asset_class", "quote_type", "dividend_yield_pct", "expense_ratio_pct", "name")}
    return out


def fetch_benchmark() -> pd.Series | None:
    """The configured benchmark (default SPY, an S&P 500 ETF) as a price series."""
    try:
        data = _fetch_one(config.BENCHMARK_TICKER)
        return data["price_history"] if data else None
    except Exception:  # noqa: BLE001
        logger.exception("Failed to fetch benchmark %s", config.BENCHMARK_TICKER)
        return None
