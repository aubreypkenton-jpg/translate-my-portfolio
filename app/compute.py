"""
Pure computation for the portfolio report. No network, no prose.

Deliberately separated from data fetching (data_fetch.py) and from wording
(explain.py) so that:
  1. Every number shown to the user traces back to real fetched prices; no
     LLM and no hand-wavy estimate invents a statistic.
  2. This module can be unit-tested with synthetic price data whose answers
     are known in advance (see tests/test_compute*.py).

Conventions used throughout:
  * Percentages are stored as percent numbers (12.5 means 12.5%).
  * "Annualized" uses 252 trading days per year.
  * Portfolio history replays TODAY's weights over the past, rebalanced daily
    (a standard simplification; see the methodology page).
All tunable thresholds live in config.py.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from . import config

TRADING_DAYS_PER_YEAR = 252


# --------------------------------------------------------------------------
# small building blocks (each is unit-tested on its own)
# --------------------------------------------------------------------------

def _annualized_vol(returns_series: pd.Series) -> float | None:
    """Annualized standard deviation of daily returns, in percent."""
    if len(returns_series) < 6:
        return None
    return float(returns_series.std() * math.sqrt(TRADING_DAYS_PER_YEAR) * 100.0)


def _max_drawdown_pct(price_series: pd.Series) -> float | None:
    """Largest peak-to-trough decline over the series, as a negative percent."""
    s = price_series.dropna()
    if len(s) < 2:
        return None
    cummax = s.cummax()
    drawdown = (s - cummax) / cummax
    return float(drawdown.min() * 100.0)


def _drawdown_curve(price_series: pd.Series) -> pd.Series:
    """Percent below the running peak on each day (0 at a new high)."""
    s = price_series.dropna()
    return (s / s.cummax() - 1.0) * 100.0


def _years_between(index: pd.Index) -> float:
    """Elapsed years, counted in trading days: n prices span n-1 trading days.

    252 trading days per year is the market convention, and it matches how
    volatility is annualized, so return and risk use the same clock.
    """
    return (len(index) - 1) / TRADING_DAYS_PER_YEAR


def _calendar_years(index: pd.Index) -> float | None:
    """Calendar years between first and last date (for display only)."""
    try:
        return (pd.Timestamp(index[-1]) - pd.Timestamp(index[0])).days / 365.25
    except (ValueError, TypeError):
        return None


def _cagr(price_series: pd.Series) -> float | None:
    """Compound annual growth rate, in percent: (end/start)^(1/years) - 1."""
    s = price_series.dropna()
    if len(s) < 2:
        return None
    total_return = s.iloc[-1] / s.iloc[0]
    years = _years_between(s.index)
    if years <= 0 or total_return <= 0:
        return None
    return float(total_return ** (1 / years) - 1) * 100.0


def _daily_risk_free(annual_rate: float) -> float:
    """Convert an annual rate (0.04 = 4%) to the equivalent daily rate."""
    return (1.0 + annual_rate) ** (1.0 / TRADING_DAYS_PER_YEAR) - 1.0


def _sharpe(daily_returns: pd.Series | np.ndarray, annual_rf: float) -> float | None:
    """Annualized Sharpe ratio: mean daily excess return / stdev, times sqrt(252).

    This is the textbook ex-post Sharpe (Sharpe, 1994). Both numerator and
    denominator come from the same daily returns, so they're consistent.
    """
    r = np.asarray(daily_returns, dtype=float)
    if len(r) < 6:
        return None
    sd = r.std(ddof=1)
    if not sd or not math.isfinite(sd):
        return None
    excess = r - _daily_risk_free(annual_rf)
    return float(excess.mean() / sd * math.sqrt(TRADING_DAYS_PER_YEAR))


def _sortino(daily_returns: pd.Series | np.ndarray, annual_rf: float) -> float | None:
    """Like Sharpe, but only *downside* volatility counts as risk.

    Downside deviation = sqrt(mean(min(excess, 0)^2)), annualized.
    """
    r = np.asarray(daily_returns, dtype=float)
    if len(r) < 6:
        return None
    excess = r - _daily_risk_free(annual_rf)
    downside = np.sqrt(np.mean(np.minimum(excess, 0.0) ** 2))
    if not downside:
        return None
    return float(excess.mean() / downside * math.sqrt(TRADING_DAYS_PER_YEAR))


def _beta(port_returns: pd.Series, bench_returns: pd.Series) -> float | None:
    """Sensitivity to the market: cov(portfolio, S&P 500) / var(S&P 500).

    A beta of 1.2 means the portfolio has tended to move ~1.2% for every 1%
    move in the index. Computed only on dates both series share.
    """
    df = pd.concat([port_returns, bench_returns], axis=1, join="inner").dropna()
    if len(df) < 20:
        return None
    var = df.iloc[:, 1].var()
    if not var:
        return None
    return float(df.iloc[:, 0].cov(df.iloc[:, 1]) / var)


def _add_one_year(d: date) -> date:
    """Same calendar day next year (Feb 29 maps to Feb 28)."""
    try:
        return d.replace(year=d.year + 1)
    except ValueError:
        return d.replace(year=d.year + 1, day=28)


def holding_term(purchase: date, as_of: date) -> tuple[str, int | None]:
    """IRS holding-period rule: long-term if held MORE than one year.

    The holding period starts the day after purchase, so shares bought on
    2023-01-10 become long-term when sold on 2024-01-11 or later; selling on
    2024-01-10 is still short-term (IRS Publication 550).

    Returns ``(term, days_until_long_term)``; the second value is None once
    the position is already long-term.
    """
    first_long_term_day = _add_one_year(purchase).toordinal() + 1
    if as_of.toordinal() >= first_long_term_day:
        return "long-term", None
    return "short-term", first_long_term_day - as_of.toordinal()


def _to_date(value: datetime | date) -> date:
    return value.date() if isinstance(value, datetime) else value


def _slice(series: pd.Series, start: str, end: str) -> pd.Series:
    s = series.dropna()
    return s[(s.index >= start) & (s.index <= end)]


# --------------------------------------------------------------------------
# benchmark
# --------------------------------------------------------------------------

def compute_benchmark_stats(benchmark_series: pd.Series | None,
                            risk_free_rate: float | None = None) -> dict[str, Any] | None:
    """Stats for the S&P 500 (or whichever benchmark is configured).

    compute_portfolio() passes a series already cut to the SAME dates as the
    portfolio, so the "vs. the market" comparison is apples to apples.
    """
    if benchmark_series is None or benchmark_series.dropna().empty:
        return None
    rf = config.RISK_FREE_RATE if risk_free_rate is None else risk_free_rate
    s = benchmark_series.dropna()
    rets = s.pct_change().dropna()
    sharpe = _sharpe(rets, rf)
    return {
        "annualized_vol_pct": _annualized_vol(rets),
        "max_drawdown_pct": _max_drawdown_pct(s),
        "cagr_pct": _cagr(s),
        "sharpe_ratio": round(sharpe, 2) if sharpe is not None else None,
        "start_date": str(s.index[0]),
        "end_date": str(s.index[-1]),
    }


# --------------------------------------------------------------------------
# risk score (a deliberately simple heuristic; see DECISIONS.md)
# --------------------------------------------------------------------------

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


# --------------------------------------------------------------------------
# main entry point
# --------------------------------------------------------------------------

def compute_portfolio(
    holdings: list[dict[str, Any]],
    current_prices: dict[str, float],
    sectors: dict[str, str],
    price_histories: dict[str, pd.Series],
    today: datetime | date | None = None,
    benchmark_series: pd.Series | None = None,
    risk_free_rate: float | None = None,
    profiles: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compute every metric in the report.

    Args:
        holdings: dicts with ticker, shares, purchase_price, purchase_date (YYYY-MM-DD).
        current_prices: {ticker: latest price}.
        sectors: {ticker: sector label}.
        price_histories: {ticker: Series of daily closes, index 'YYYY-MM-DD'}.
        today: "as of" date (defaults to now, UTC).
        benchmark_series: S&P 500 proxy (SPY) closes, same format.
        risk_free_rate: annual rate as a decimal (0.04 = 4%); default in config.
        profiles: optional {ticker: {asset_class, dividend_yield_pct, expense_ratio_pct}}.

    Returns a dict of numbers; explain.py turns it into sentences.
    """
    as_of = _to_date(today or datetime.now(timezone.utc))
    rf = config.RISK_FREE_RATE if risk_free_rate is None else risk_free_rate
    profiles = profiles or {}

    # --- positions -------------------------------------------------------
    rows: list[dict[str, Any]] = []
    total_value = 0.0
    for h in holdings:
        ticker = h["ticker"].upper()
        shares = float(h["shares"])
        price = current_prices.get(ticker)
        if price is None:
            continue
        value = shares * price
        total_value += value
        purchase_date = (datetime.strptime(h["purchase_date"], "%Y-%m-%d").date()
                         if h.get("purchase_date") else None)
        holding_days = (as_of - purchase_date).days if purchase_date else None
        purchase_price = float(h["purchase_price"]) if h.get("purchase_price") else None
        gain_loss_pct = None
        unrealized_gain = None
        if purchase_price:
            gain_loss_pct = (price - purchase_price) / purchase_price * 100.0
            unrealized_gain = (price - purchase_price) * shares
        profile = profiles.get(ticker, {})
        rows.append({
            "ticker": ticker,
            "shares": shares,
            "current_price": price,
            "value": value,
            "sector": sectors.get(ticker, "Unknown"),
            "asset_class": profile.get("asset_class") or "Other / unknown",
            "purchase_price": purchase_price,
            "purchase_date": h.get("purchase_date"),
            "holding_days": holding_days,
            "gain_loss_pct": gain_loss_pct,
            "unrealized_gain": unrealized_gain,
            "max_drawdown_pct": _max_drawdown_pct(price_histories.get(ticker, pd.Series(dtype=float))),
        })

    for r in rows:
        r["weight_pct"] = (r["value"] / total_value * 100.0) if total_value else 0.0

    weights = {r["ticker"]: r["weight_pct"] / 100.0 for r in rows}

    # --- diversification: Herfindahl-Hirschman Index -----------------------
    # HHI = sum of squared weights; effective N = 1/HHI. Ten holdings where
    # one is 91% of the money behave like ~1.2 holdings, not 10.
    hhi = None
    effective_holdings = None
    if rows:
        hhi = sum((r["weight_pct"] / 100.0) ** 2 for r in rows)
        if hhi > 0:
            effective_holdings = round(1.0 / hhi, 1)

    # --- concentration: single holding, sector, asset class --------------------
    top = max(rows, key=lambda r: r["weight_pct"]) if rows else None
    concentration = {
        "top_ticker": top["ticker"] if top else None,
        "top_pct": top["weight_pct"] if top else 0.0,
        "flagged": bool(top and top["weight_pct"] > config.CONCENTRATION_FLAG_PCT),
    }

    sector_pct: dict[str, float] = {}
    asset_class_pct: dict[str, float] = {}
    for r in rows:
        sector_pct[r["sector"]] = sector_pct.get(r["sector"], 0.0) + r["weight_pct"]
        asset_class_pct[r["asset_class"]] = asset_class_pct.get(r["asset_class"], 0.0) + r["weight_pct"]
    flagged_sectors = {s: p for s, p in sector_pct.items()
                       if p > config.SECTOR_FLAG_PCT and not s.startswith("Diversified fund")}
    max_sector_pct = max((p for s, p in sector_pct.items() if not s.startswith("Diversified fund")),
                         default=0.0)
    single_stock_pct = asset_class_pct.get("Individual stock", 0.0)

    # --- fund facts (ETFs / mutual funds) ----------------------------------
    fund_flags: list[dict[str, Any]] = []
    weighted_expense_ratio = None
    annual_fee_dollars = 0.0
    fund_weight = 0.0
    for r in rows:
        p = profiles.get(r["ticker"], {})
        er = p.get("expense_ratio_pct")
        dy = p.get("dividend_yield_pct")
        if er is not None:
            annual_fee_dollars += r["value"] * er / 100.0
            fund_weight += r["value"]
            if er > config.HIGH_EXPENSE_RATIO_PCT:
                fund_flags.append({"ticker": r["ticker"], "type": "high_expense_ratio", "value": er})
        if dy is not None:
            r["dividend_yield_pct"] = dy
            if dy > config.HIGH_DIVIDEND_YIELD_PCT:
                fund_flags.append({"ticker": r["ticker"], "type": "high_dividend_yield", "value": dy})
        if er is not None:
            r["expense_ratio_pct"] = er
    if fund_weight:
        weighted_expense_ratio = annual_fee_dollars / fund_weight * 100.0
    yields = [(r["value"], r["dividend_yield_pct"]) for r in rows if r.get("dividend_yield_pct") is not None]
    portfolio_yield = (sum(v * y for v, y in yields) / total_value) if yields and total_value else None

    # --- per-holding volatility (each over its own history) -------------------
    volatility = {}
    for t, series in price_histories.items():
        s = series.dropna()
        if len(s) > 6:
            v = _annualized_vol(s.pct_change().dropna())
            if v is not None:
                volatility[t] = v

    # --- portfolio history on dates ALL holdings share ----------------------
    held = [r["ticker"] for r in rows if r["ticker"] in price_histories
            and not price_histories[r["ticker"]].dropna().empty]
    portfolio_vol = portfolio_cagr = portfolio_max_drawdown = None
    sharpe_ratio = sortino_ratio = beta = None
    port_index: pd.Series | None = None
    port_rets: pd.Series | None = None
    ret_df: pd.DataFrame | None = None
    if held:
        prices_df = pd.DataFrame({t: price_histories[t] for t in held}).dropna()
        if len(prices_df) > 1:
            ret_df = prices_df.pct_change().dropna()
            w = np.array([weights.get(t, 0.0) for t in ret_df.columns])
            if w.sum() > 0:
                w = w / w.sum()  # renormalize if some holding has no history
            port_rets = pd.Series(ret_df.values @ w, index=ret_df.index)
            port_index = pd.Series(
                np.concatenate([[1.0], (1.0 + port_rets.values).cumprod()]),
                index=prices_df.index,
            )
            portfolio_vol = _annualized_vol(port_rets)
            if portfolio_vol == 0:
                portfolio_vol = None
            portfolio_cagr = _cagr(port_index)
            portfolio_max_drawdown = _max_drawdown_pct(port_index)
            s = _sharpe(port_rets, rf)
            sharpe_ratio = round(s, 2) if s is not None else None
            so = _sortino(port_rets, rf)
            sortino_ratio = round(so, 2) if so is not None else None

    analysis_window = None
    if port_index is not None:
        analysis_window = {"start": str(port_index.index[0]), "end": str(port_index.index[-1]),
                           "years": round(_calendar_years(port_index.index) or _years_between(port_index.index), 1)}

    # --- correlation between holdings ------------------------------------------
    high_corr_pairs: list[tuple[str, str, float]] = []
    max_corr = None
    corr_matrix = None
    if ret_df is not None and ret_df.shape[1] > 1:
        corr_matrix = ret_df.corr()
        cols = list(corr_matrix.columns)
        pair_corrs = []
        for i in range(len(cols)):
            for j in range(i + 1, len(cols)):
                c = float(corr_matrix.iloc[i, j])
                pair_corrs.append(c)
                if c > config.HIGH_CORRELATION:
                    high_corr_pairs.append((cols[i], cols[j], c))
        if pair_corrs:
            max_corr = max(pair_corrs)

    # --- benchmark over the SAME dates as the portfolio -------------------------
    benchmark = None
    benchmark_index = None
    if benchmark_series is not None and not benchmark_series.dropna().empty:
        bench = benchmark_series.dropna()
        if analysis_window:
            bench = _slice(bench, analysis_window["start"], analysis_window["end"])
        benchmark = compute_benchmark_stats(bench, rf)
        if benchmark and port_rets is not None:
            b = _beta(port_rets, bench.pct_change().dropna())
            beta = round(b, 2) if b is not None else None
        if len(bench) > 1:
            benchmark_index = bench / bench.iloc[0]

    # --- historical crash windows, using REAL price moves of held tickers ---
    drawdown_scenarios: dict[str, dict[str, Any]] = {}
    for name, (start, end) in config.CRASH_WINDOWS.items():
        weighted_return = 0.0
        covered_weight = 0.0
        details = []
        for r in rows:
            t = r["ticker"]
            series = price_histories.get(t)
            if series is None or series.empty:
                continue
            s = _slice(series, start, end)
            if len(s) < 2:
                continue
            change_pct = (s.iloc[-1] - s.iloc[0]) / s.iloc[0] * 100.0
            w = weights.get(t, 0.0)
            weighted_return += change_pct * w
            covered_weight += w
            details.append({"ticker": t, "change_pct": change_pct})
        if covered_weight > 0:
            scenario = {
                # weighted by covered holdings only, so missing data isn't counted as 0%
                "estimated_portfolio_change_pct": weighted_return / covered_weight,
                "coverage_pct": covered_weight * 100.0,
                "details": details,
                "benchmark_change_pct": None,
            }
            if benchmark_series is not None:
                b = _slice(benchmark_series, start, end)
                if len(b) >= 2:
                    scenario["benchmark_change_pct"] = float((b.iloc[-1] - b.iloc[0]) / b.iloc[0] * 100.0)
            drawdown_scenarios[name] = scenario

    # --- behavioral flags ----------------------------------------------------------
    behavioral_flags: list[dict[str, Any]] = []
    for r in rows:
        t = r["ticker"]
        series = price_histories.get(t)
        if series is not None and not series.empty and r["purchase_date"] and r["purchase_price"]:
            s = series.dropna()
            s_before = s[s.index <= r["purchase_date"]]
            if len(s_before) > 30:
                price_30d_before = s_before.iloc[-31]
                runup_pct = (r["purchase_price"] - price_30d_before) / price_30d_before * 100.0
                if runup_pct > config.RECENCY_BIAS_RUNUP_PCT:
                    behavioral_flags.append({"ticker": t, "type": "recency_bias", "detail": round(runup_pct, 1)})

        if (r["gain_loss_pct"] is not None and r["gain_loss_pct"] < config.LOSS_AVERSION_LOSS_PCT
                and r["holding_days"] is not None and r["holding_days"] > config.LOSS_AVERSION_MIN_HOLD_DAYS):
            behavioral_flags.append({"ticker": t, "type": "loss_aversion", "detail": round(r["gain_loss_pct"], 1)})

        if (r["holding_days"] is not None and r["holding_days"] <= config.CONCENTRATED_RECENT_BUY_DAYS
                and r["weight_pct"] > config.CONCENTRATED_RECENT_BUY_PCT):
            behavioral_flags.append({"ticker": t, "type": "concentrated_recent_buy",
                                     "detail": round(r["weight_pct"], 1)})

    # --- capital gains (federal, US) ----------------------------------------------
    tax_flags: list[dict[str, Any]] = []
    tax_summary = {"short_term_gain": 0.0, "short_term_loss": 0.0,
                   "long_term_gain": 0.0, "long_term_loss": 0.0, "has_cost_basis": False}
    for r in rows:
        if not r["purchase_date"]:
            continue
        purchased = datetime.strptime(r["purchase_date"], "%Y-%m-%d").date()
        term, days_to_lt = holding_term(purchased, as_of)
        g = r["unrealized_gain"]
        status = "unknown" if g is None else ("gain" if g > 0 else ("loss" if g < 0 else "flat"))
        tax_flags.append({
            "ticker": r["ticker"], "term": term, "holding_days": r["holding_days"],
            "days_until_long_term": days_to_lt, "unrealized_gain": g, "status": status,
        })
        if g is not None:
            tax_summary["has_cost_basis"] = True
            key = ("short_term_" if term == "short-term" else "long_term_") + ("gain" if g >= 0 else "loss")
            tax_summary[key] += g

    # --- risk score -------------------------------------------------------------------
    risk_score, risk_label = _risk_score(
        concentration.get("top_pct"), max_sector_pct, portfolio_vol, max_corr, portfolio_max_drawdown
    )

    return {
        "as_of": as_of.isoformat(),
        "risk_free_rate_pct": rf * 100.0,
        "total_value": total_value,
        "rows": rows,
        "hhi": round(hhi, 4) if hhi is not None else None,
        "effective_holdings": effective_holdings,
        "concentration": concentration,
        "sector_pct": sector_pct,
        "flagged_sectors": flagged_sectors,
        "asset_class_pct": asset_class_pct,
        "single_stock_pct": single_stock_pct,
        "fund_flags": fund_flags,
        "weighted_expense_ratio_pct": weighted_expense_ratio,
        "annual_fee_dollars": annual_fee_dollars if fund_weight else None,
        "portfolio_yield_pct": portfolio_yield,
        "volatility": volatility,
        "analysis_window": analysis_window,
        "portfolio_vol": portfolio_vol,
        "portfolio_cagr": portfolio_cagr,
        "portfolio_max_drawdown": portfolio_max_drawdown,
        "sharpe_ratio": sharpe_ratio,
        "sortino_ratio": sortino_ratio,
        "beta": beta,
        "high_corr_pairs": high_corr_pairs,
        "drawdown_scenarios": drawdown_scenarios,
        "behavioral_flags": behavioral_flags,
        "tax_flags": tax_flags,
        "tax_summary": tax_summary,
        "risk_score": risk_score,
        "risk_label": risk_label,
        "benchmark": benchmark,
        "correlation_matrix": corr_matrix.round(2).to_dict() if corr_matrix is not None else None,
        # series for charts (not part of the JSON export)
        "portfolio_index": port_index,
        "benchmark_index": benchmark_index,
    }


# --------------------------------------------------------------------------
# "what if I rebalance?"
# --------------------------------------------------------------------------

def compute_rebalance(
    current: dict[str, Any],
    targets_pct: dict[str, float],
    current_prices: dict[str, float],
    sectors: dict[str, str],
    price_histories: dict[str, pd.Series],
    today: datetime | date | None = None,
    benchmark_series: pd.Series | None = None,
    risk_free_rate: float | None = None,
    profiles: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compare the current portfolio with the same dollars at target weights.

    ``targets_pct`` maps ticker -> target percent (must sum to ~100; the web
    layer validates that). The target portfolio is analyzed with exactly the
    same code as the real one, so the comparison is like for like.

    Returns trades needed (dollars to buy/sell per ticker), the before/after
    metrics, and which sales would realize a short-term gain.
    """
    total = current["total_value"]
    target_holdings = []
    for t, pct in targets_pct.items():
        price = current_prices.get(t)
        if price and pct > 0:
            target_holdings.append({"ticker": t, "shares": pct / 100.0 * total / price,
                                    "purchase_price": None, "purchase_date": None})
    target = compute_portfolio(target_holdings, current_prices, sectors, price_histories,
                               today=today, benchmark_series=benchmark_series,
                               risk_free_rate=risk_free_rate, profiles=profiles)

    current_values = {r["ticker"]: r["value"] for r in current["rows"]}
    tax_by_ticker = {f["ticker"]: f for f in current.get("tax_flags", [])}
    trades = []
    for t in sorted(set(current_values) | set(targets_pct)):
        now_v = current_values.get(t, 0.0)
        new_v = targets_pct.get(t, 0.0) / 100.0 * total
        delta = new_v - now_v
        if abs(delta) < 0.005 * max(total, 1):
            continue
        tf = tax_by_ticker.get(t)
        trades.append({
            "ticker": t,
            "action": "buy" if delta > 0 else "sell",
            "amount": abs(delta),
            "current_pct": now_v / total * 100.0 if total else 0.0,
            "target_pct": targets_pct.get(t, 0.0),
            "short_term_gain_warning": bool(delta < 0 and tf and tf["term"] == "short-term"
                                            and tf["status"] == "gain"),
        })

    keys = ["effective_holdings", "portfolio_vol", "portfolio_cagr", "portfolio_max_drawdown",
            "sharpe_ratio", "beta", "risk_score"]
    comparison = {k: {"current": current.get(k), "target": target.get(k)} for k in keys}
    comparison["top_pct"] = {"current": current["concentration"]["top_pct"],
                             "target": target["concentration"]["top_pct"]}
    for name in current.get("drawdown_scenarios", {}):
        comparison[f"crash:{name}"] = {
            "current": current["drawdown_scenarios"][name]["estimated_portfolio_change_pct"],
            "target": target["drawdown_scenarios"].get(name, {}).get("estimated_portfolio_change_pct"),
        }
    return {"trades": trades, "comparison": comparison, "target": target}
