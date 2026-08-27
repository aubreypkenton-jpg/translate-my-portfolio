"""
Pure computation functions for the portfolio-literacy app.

Deliberately separated from data-fetching (yfinance) so that:
  1. Every number shown to the user traces back to real fetched data -- no
     LLM and no hand-wavy estimate invents a stat.
  2. This module has zero network dependency and can be fully unit-tested
     with synthetic price data (see tests/test_compute.py).

All tunable thresholds live in config.py, not here.
"""
import math
from datetime import datetime

import numpy as np
import pandas as pd

from . import config

TRADING_DAYS_PER_YEAR = 252


def _annualized_vol(returns_series):
    if len(returns_series) < 6:
        return None
    return float(returns_series.std() * math.sqrt(TRADING_DAYS_PER_YEAR) * 100.0)


def _max_drawdown_pct(price_series):
    """Peak-to-trough decline over the full given series, as a negative %."""
    s = price_series.dropna()
    if len(s) < 2:
        return None
    cummax = s.cummax()
    drawdown = (s - cummax) / cummax
    return float(drawdown.min() * 100.0)


def _cagr(price_series):
    s = price_series.dropna()
    if len(s) < 2:
        return None
    total_return = s.iloc[-1] / s.iloc[0]
    years = len(s) / TRADING_DAYS_PER_YEAR
    if years <= 0 or total_return <= 0:
        return None
    return float(total_return ** (1 / years) - 1) * 100.0


def compute_benchmark_stats(benchmark_series):
    """Independent of any portfolio -- stats for the S&P 500 (or whatever
    benchmark is configured), so the UI can say 'vs. the market'."""
    if benchmark_series is None or benchmark_series.dropna().empty:
        return None
    s = benchmark_series.dropna()
    rets = s.pct_change().dropna()
    return {
        "annualized_vol_pct": _annualized_vol(rets),
        "max_drawdown_pct": _max_drawdown_pct(s),
        "cagr_pct": _cagr(s),
    }


def _risk_score(concentration_pct, sector_pct, portfolio_vol, max_corr, max_drawdown_pct):
    caps = config.RISK_SCORE_CAPS
    subscores = []

    def scaled(value, cap):
        if value is None:
            return None
        return min(100.0, max(0.0, (abs(value) / cap) * 100.0))

    for value, cap in [
        (concentration_pct, caps["concentration"]),
        (sector_pct, caps["sector"]),
        (portfolio_vol, caps["volatility"]),
        (max_corr, caps["correlation"]),
        (max_drawdown_pct, caps["drawdown"]),
    ]:
        s = scaled(value, cap)
        if s is not None:
            subscores.append(s)

    if not subscores:
        return None, None
    score = sum(subscores) / len(subscores)
    label = next(label for threshold, label in config.RISK_SCORE_BANDS if score < threshold)
    return round(score, 1), label


def compute_portfolio(holdings, current_prices, sectors, price_histories, today=None,
                       benchmark_series=None):
    """
    holdings: list of dicts: {ticker, shares, purchase_price, purchase_date (YYYY-MM-DD)}
    current_prices: {ticker: float}
    sectors: {ticker: str}
    price_histories: {ticker: pd.Series of daily close, index = 'YYYY-MM-DD' strings}
    benchmark_series: optional pd.Series for the benchmark (e.g. SPY), same format

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
            "max_drawdown_pct": _max_drawdown_pct(price_histories.get(ticker, pd.Series(dtype=float))),
        })

    for r in rows:
        r["weight_pct"] = (r["value"] / total_value * 100.0) if total_value else 0.0

    weights = {r["ticker"]: r["weight_pct"] / 100.0 for r in rows}

    # --- diversification (Herfindahl-Hirschman based "effective number of holdings") ---
    # HHI = sum of squared weights; effective_N = 1/HHI. A portfolio of 10 holdings
    # where one is 91% of the money behaves like ~1.2 holdings, not 10 -- this
    # captures that in a way a simple holdings count can't.
    effective_holdings = None
    if rows:
        hhi = sum((r["weight_pct"] / 100.0) ** 2 for r in rows)
        if hhi > 0:
            effective_holdings = round(1.0 / hhi, 1)

    # --- concentration ---
    top = max(rows, key=lambda r: r["weight_pct"]) if rows else None
    concentration = {
        "top_ticker": top["ticker"] if top else None,
        "top_pct": top["weight_pct"] if top else 0.0,
        "flagged": bool(top and top["weight_pct"] > config.CONCENTRATION_FLAG_PCT),
    }

    # --- sector concentration ---
    sector_pct = {}
    for r in rows:
        sector_pct[r["sector"]] = sector_pct.get(r["sector"], 0.0) + r["weight_pct"]
    flagged_sectors = {s: p for s, p in sector_pct.items() if p > config.SECTOR_FLAG_PCT}
    max_sector_pct = max(sector_pct.values()) if sector_pct else 0.0

    # --- daily returns per ticker (for volatility, correlation, portfolio-level stats) ---
    returns = {}
    for t, series in price_histories.items():
        s = series.dropna()
        if len(s) > 1:
            returns[t] = s.pct_change().dropna()

    # --- volatility (annualized stdev of daily returns) ---
    volatility = {t: _annualized_vol(r) for t, r in returns.items()}
    volatility = {t: v for t, v in volatility.items() if v is not None}

    portfolio_vol = None
    portfolio_cagr = None
    portfolio_max_drawdown = None
    ret_df = None
    if returns:
        ret_df = pd.DataFrame(returns).dropna()
        if not ret_df.empty:
            w = np.array([weights.get(t, 0.0) for t in ret_df.columns])
            port_daily_returns = ret_df.values @ w
            if port_daily_returns.std() > 0:
                portfolio_vol = float(port_daily_returns.std() * math.sqrt(TRADING_DAYS_PER_YEAR) * 100.0)
            # build a synthetic portfolio value index from the weighted daily returns
            port_index = pd.Series((1 + port_daily_returns).cumprod(), index=ret_df.index)
            portfolio_cagr = _cagr(port_index)
            portfolio_max_drawdown = _max_drawdown_pct(port_index)

    # --- correlation matrix + high-correlation pairs ---
    high_corr_pairs = []
    max_corr = None
    if ret_df is not None and ret_df.shape[1] > 1:
        corr_matrix = ret_df.corr()
        cols = corr_matrix.columns
        pair_corrs = []
        for i in range(len(cols)):
            for j in range(i + 1, len(cols)):
                c = float(corr_matrix.iloc[i, j])
                pair_corrs.append(c)
                if c > config.HIGH_CORRELATION:
                    high_corr_pairs.append((cols[i], cols[j], c))
        if pair_corrs:
            max_corr = max(pair_corrs)

    # --- Sharpe ratio (uses portfolio CAGR over the overlapping data window) ---
    sharpe_ratio = None
    if portfolio_cagr is not None and portfolio_vol:
        sharpe_ratio = round((portfolio_cagr - config.RISK_FREE_RATE * 100.0) / portfolio_vol, 2)

    # --- historical drawdown scenarios, using REAL price moves of held tickers ---
    drawdown_scenarios = {}
    for name, (start, end) in config.CRASH_WINDOWS.items():
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
                continue
            change_pct = (s.iloc[-1] - s.iloc[0]) / s.iloc[0] * 100.0
            w = weights.get(t, 0.0)
            weighted_return += change_pct * w
            covered_weight += w
            details.append({"ticker": t, "change_pct": change_pct})
        if covered_weight > 0:
            drawdown_scenarios[name] = {
                "estimated_portfolio_change_pct": weighted_return,
                "coverage_pct": covered_weight * 100.0,
                "details": details,
            }

    # --- behavioral flags ---
    behavioral_flags = []
    for r in rows:
        t = r["ticker"]
        series = price_histories.get(t)
        if series is not None and not series.empty and r["purchase_date"] and r["purchase_price"]:
            try:
                s = series.dropna()
                s_before = s[s.index <= r["purchase_date"]]
                if len(s_before) > 30:
                    price_30d_before = s_before.iloc[-31]
                    runup_pct = (r["purchase_price"] - price_30d_before) / price_30d_before * 100.0
                    if runup_pct > config.RECENCY_BIAS_RUNUP_PCT:
                        behavioral_flags.append({"ticker": t, "type": "recency_bias", "detail": round(runup_pct, 1)})
            except TypeError:
                # defensive: an unexpected index type on a malformed/empty series
                # shouldn't take down the whole analysis
                pass

        if (r["gain_loss_pct"] is not None and r["gain_loss_pct"] < config.LOSS_AVERSION_LOSS_PCT
                and r["holding_days"] is not None and r["holding_days"] > config.LOSS_AVERSION_MIN_HOLD_DAYS):
            behavioral_flags.append({"ticker": t, "type": "loss_aversion", "detail": round(r["gain_loss_pct"], 1)})

        if (r["holding_days"] is not None and r["holding_days"] <= config.CONCENTRATED_RECENT_BUY_DAYS
                and r["weight_pct"] > config.CONCENTRATED_RECENT_BUY_PCT):
            behavioral_flags.append({"ticker": t, "type": "concentrated_recent_buy", "detail": round(r["weight_pct"], 1)})

    # --- tax flags ---
    tax_flags = []
    for r in rows:
        if r["holding_days"] is not None:
            term = "long-term" if r["holding_days"] >= 365 else "short-term"
            tax_flags.append({"ticker": r["ticker"], "term": term, "holding_days": r["holding_days"]})

    # --- risk score ---
    risk_score, risk_label = _risk_score(
        concentration.get("top_pct"), max_sector_pct, portfolio_vol, max_corr, portfolio_max_drawdown
    )

    # --- benchmark comparison ---
    benchmark = compute_benchmark_stats(benchmark_series)

    return {
        "total_value": total_value,
        "rows": rows,
        "effective_holdings": effective_holdings,
        "concentration": concentration,
        "sector_pct": sector_pct,
        "flagged_sectors": flagged_sectors,
        "volatility": volatility,
        "portfolio_vol": portfolio_vol,
        "portfolio_cagr": portfolio_cagr,
        "portfolio_max_drawdown": portfolio_max_drawdown,
        "sharpe_ratio": sharpe_ratio,
        "high_corr_pairs": high_corr_pairs,
        "drawdown_scenarios": drawdown_scenarios,
        "behavioral_flags": behavioral_flags,
        "tax_flags": tax_flags,
        "risk_score": risk_score,
        "risk_label": risk_label,
        "benchmark": benchmark,
        "correlation_matrix": (ret_df.corr().round(2).to_dict() if ret_df is not None and ret_df.shape[1] > 1 else None),
    }
