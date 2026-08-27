"""
All network/yfinance calls live here, isolated from compute.py.

NOTE: this sandbox's outbound network is locked down and can't reach Yahoo
Finance, so this module is untested against live data in this environment.
It uses the standard, widely-used yfinance library (no API key required),
which will work normally once deployed to Replit/Vercel/etc, which have
normal outbound internet access. See DECISIONS.md.
"""
import pandas as pd
import yfinance as yf

HISTORY_PERIOD = "5y"  # covers both the COVID and 2022 crash windows


def fetch_holdings_data(tickers):
    """
    tickers: list of ticker strings
    Returns (current_prices, sectors, price_histories) where:
      current_prices: {ticker: float}
      sectors: {ticker: str}
      price_histories: {ticker: pd.Series of daily close, index = 'YYYY-MM-DD' strings}
    Tickers that fail to fetch are simply omitted (caller should tell the
    user which ones didn't resolve).
    """
    current_prices = {}
    sectors = {}
    price_histories = {}
    failed = []

    for raw in tickers:
        ticker = raw.strip().upper()
        if not ticker:
            continue
        try:
            tk = yf.Ticker(ticker)
            hist = tk.history(period=HISTORY_PERIOD, auto_adjust=True)
            if hist.empty:
                failed.append(ticker)
                continue
            closes = hist["Close"]
            closes.index = closes.index.strftime("%Y-%m-%d")
            price_histories[ticker] = closes
            current_prices[ticker] = float(closes.iloc[-1])

            info = {}
            try:
                info = tk.get_info()
            except Exception:
                pass
            sectors[ticker] = info.get("sector", "Unknown")
        except Exception:
            failed.append(ticker)

    return current_prices, sectors, price_histories, failed
