"""
Pure computation functions for the portfolio-literacy app.

Deliberately separated from data-fetching (yfinance) so that:
  1. Every number shown to the user traces back to real fetched data (no LLM
     invents a stat) -- see DECISIONS.md.
  2. This module can be unit-tested with synthetic price data, without a
     network call.

Inputs are plain Python/pandas structures, not yfinance objects, so this file
has zero network dependency.
"""
import math
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252

# Known historical drawdown windows we can measure real holdings against.
CRASH_WINDOWS = {
    "2022 bear market": ("2022-01-03", "2022-10-12"),
    "COVID crash (2020)": ("2020-02-19", "2020-03-23"),
}

CONCENTRATION_FLAG_PCT = 25.0       # single holding above this % is "concentrated"
SECTOR_FLAG_PCT = 50.0              # single sector above this % is "concentrated"
HIGH_CORRELATION = 0.7              # holdings moving together above this
RECENCY_BIAS_RUNUP_PCT = 15.0       # bought this much above 30-trading-day-ago price
LOSS_AVERSION_LOSS_PCT = -20.0      # underwater by this much...
LOSS_AVERSION_MIN_HOLD_DAYS = 180   # ...for at least this long


def compute_portfolio(holdings, current_prices, sectors, price_histories, today=None):
    """
    holdings: list of dicts: {ticker, shares, purchase_price, purchase_date (YYYY-MM-DD)}
    current_prices: {ticker: float}
    sectors: {ticker: str}
    price_histories: {ticker: pd.Series of daily close prices, indexed by date string}
    today: optional datetime for deterministic testing

    Returns a dict of computed metrics. No prose here -- explain.py turns
    this into plain English.
    """
    today = today or datetime.utcnow()

    rows = []
    total_value = 0.0
    for h in holdings:
        ticker = h["ticker"].upper()
        shares = float(h["shares"])
        price = current_prices.get(ticker)
        if price is None:
            continue
        value = shares * price
        total_value += value
        purchase_date = datetime.strptime(h["purchase_date"], "%Y-%m-%d") if h.get("purchase_date") else None
        holding_days = (today - purchase_date).days if purchase_date else None
        purchase_price = float(h["purchase_price"]) if h.get("purchase_price") else None
        gain_loss_pct = None
        if purchase_price:
            gain_loss_pct = (price - purchase_price) / purchase_price * 100.0
        rows.append({
            "ticker": ticker,
            "shares": shares,
            "current_price": price,
            "value": value,
            "sector": sectors.get(ticker, "Unknown"),
            "purchase_price": purchase_price,
            "purchase_date": h.get("purchase_date"),
            "holding_days": holding_days,
            "gain_loss_pct": gain_loss_pct,
        })

    for r in rows:
        r["weight_pct"] = (r["value"] / total_value * 100.0) if total_value else 0.0

    # --- concentration ---
    top = max(rows, key=lambda r: r["weight_pct"]) if rows else None
    concentration = {
        "top_ticker": top["ticker"] if top else None,
        "top_pct": top["weight_pct"] if top else 0.0,
        "flagged": bool(top and top["weight_pct"] > CONCENTRATION_FLAG_PCT),
    }

    # --- sector concentration ---
    sector_pct = {}
    for r in rows:
        sector_pct[r["sector"]] = sector_pct.get(r["sector"], 0.0) + r["weight_pct"]
    flagged_sectors = {s: p for s, p in sector_pct.items() if p > SECTOR_FLAG_PCT}

    # --- daily returns per ticker (for volatility & correlation) ---
    returns = {}
    for t, series in price_histories.items():
        s = series.dropna()
        if len(s) > 1:
            returns[t] = s.pct_change().dropna()

    # --- volatility (annualized stdev of daily returns) ---
    volatility = {}
    for t, r in returns.items():
        if len(r) > 5:
            volatility[t] = float(r.std() * math.sqrt(TRADING_DAYS_PER_YEAR) * 100.0)

    weights = {r["ticker"]: r["weight_pct"] / 100.0 for r in rows}
    portfolio_vol = None
    if returns:
        ret_df = pd.DataFrame(returns).dropna()
        if not ret_df.empty:
            w = np.array([weights.get(t, 0.0) for t in ret_df.columns])
            port_daily_returns = ret_df.values @ w
            if port_daily_returns.std() > 0:
                portfolio_vol = float(port_daily_returns.std() * math.sqrt(TRADING_DAYS_PER_YEAR) * 100.0)

    # --- correlation matrix + high-correlation pairs ---
    high_corr_pairs = []
    corr_matrix = None
    if len(returns) > 1:
        ret_df = pd.DataFrame(returns).dropna()
        if not ret_df.empty and ret_df.shape[1] > 1:
            corr_matrix = ret_df.corr()
            cols = corr_matrix.columns
            for i in range(len(cols)):
                for j in range(i + 1, len(cols)):
                    c = corr_matrix.iloc[i, j]
                    if c > HIGH_CORRELATION:
                        high_corr_pairs.append((cols[i], cols[j], float(c)))

    # --- historical drawdown scenarios, using REAL price moves of held tickers ---
    drawdown_scenarios = {}
    for name, (start, end) in CRASH_WINDOWS.items():
        weighted_return = 0.0
        covered_weight = 0.0
        details = []
        for r in rows:
            t = r["ticker"]
            series = price_histories.get(t)
            if series is None or series.empty:
                continue
            s = series.dropna()
            s = s[(s.index >= start) & (s.index <= end)]
            if len(s) < 2:
                continue  # ticker didn't exist / no data for this window
            change_pct = (s.iloc[-1] - s.iloc[0]) / s.iloc[0] * 100.0
            w = weights.get(t, 0.0)
            weighted_return += change_pct * w
            covered_weight += w
            details.append({"ticker": t, "change_pct": change_pct})
        if covered_weight > 0:
            drawdown_scenarios[name] = {
                # weighted_return is already scaled by actual weights; report
                # as-is plus how much of the portfolio that estimate covers
                "estimated_portfolio_change_pct": weighted_return,
                "coverage_pct": covered_weight * 100.0,
                "details": details,
            }

    # --- behavioral flags ---
    behavioral_flags = []
    for r in rows:
        t = r["ticker"]
        series = price_histories.get(t)
        if series is not None and r["purchase_date"] and r["purchase_price"]:
            s = series.dropna()
            s = s[s.index <= r["purchase_date"]]
            if len(s) > 30:
                price_30d_before = s.iloc[-31]
                runup_pct = (r["purchase_price"] - price_30d_before) / price_30d_before * 100.0
                if runup_pct > RECENCY_BIAS_RUNUP_PCT:
                    behavioral_flags.append({
                        "ticker": t,
                        "type": "recency_bias",
                        "detail": round(runup_pct, 1),
                    })
        if (r["gain_loss_pct"] is not None and r["gain_loss_pct"] < LOSS_AVERSION_LOSS_PCT
                and r["holding_days"] is not None and r["holding_days"] > LOSS_AVERSION_MIN_HOLD_DAYS):
            behavioral_flags.append({
                "ticker": t,
                "type": "loss_aversion",
                "detail": round(r["gain_loss_pct"], 1),
            })

    # --- tax flags ---
    tax_flags = []
    for r in rows:
        if r["holding_days"] is not None:
            term = "long-term" if r["holding_days"] >= 365 else "short-term"
            tax_flags.append({"ticker": r["ticker"], "term": term, "holding_days": r["holding_days"]})

    return {
        "total_value": total_value,
        "rows": rows,
        "concentration": concentration,
        "sector_pct": sector_pct,
        "flagged_sectors": flagged_sectors,
        "volatility": volatility,
        "portfolio_vol": portfolio_vol,
        "high_corr_pairs": high_corr_pairs,
        "drawdown_scenarios": drawdown_scenarios,
        "behavioral_flags": behavioral_flags,
        "tax_flags": tax_flags,
    }
