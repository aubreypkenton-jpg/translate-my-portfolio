"""
Turns compute.py's numbers into plain-English explanations.

Deliberately template-based, NOT an LLM. Every sentence is a fixed template
with numbers from compute.py plugged in, and those numbers came from real
fetched prices. Nothing here is generated or guessed; see DECISIONS.md for
why this is the central design choice of the project.
"""
from __future__ import annotations

from typing import Any

from . import config

TAX_DISCLAIMER = (
    "This is general educational information about US federal capital gains rules, "
    "not tax advice. State taxes, your income, and other details change the real answer; "
    "talk to a tax professional before acting on it."
)

BIAS_EXPLAINERS = {
    "recency_bias": (
        "Recency bias: you bought {ticker} after it had already climbed about "
        "{detail}% in the prior month. It's a common trap: a stock looking "
        "exciting because it just went up isn't the same as it being a good buy. "
        "Worth asking: would you buy this today, at this price, if it hadn't just moved?"
    ),
    "loss_aversion": (
        "Loss aversion: {ticker} is down about {detail_abs}% and you've held it a "
        "while. People often keep losing positions hoping to 'get back to even' "
        "rather than judging the stock on its own merits today. Ask: if you didn't "
        "already own this, would you buy it right now at this price?"
    ),
    "concentrated_recent_buy": (
        "Fast, big bet: {ticker} is already {detail}% of this portfolio and you "
        "bought it within the last month. Moving quickly to a large position in "
        "something new is worth a second look: was this a considered decision "
        "or a reaction to excitement?"
    ),
}

FUND_EXPLAINERS = {
    "high_expense_ratio": (
        "{ticker} charges an expense ratio of about {value:.2f}% a year. Fees come out "
        "every year whether the fund does well or not; many broad index funds charge "
        "under 0.10%, so it's worth checking what you get for the extra cost."
    ),
    "high_dividend_yield": (
        "{ticker} shows a dividend yield of about {value:.1f}%. A very high yield can "
        "mean the price has fallen (pushing the yield up) or that payouts may not be "
        "sustainable, and dividends in a taxable account are taxed each year."
    ),
}


def _signed_move(pct: float) -> str:
    """'fallen about 34%' / 'risen about 5%' / 'stayed roughly flat'."""
    if abs(pct) < 0.5:
        return "stayed roughly flat"
    return f"{'fallen' if pct < 0 else 'risen'} about {abs(pct):.0f}%"


def _past_move(pct: float) -> str:
    """'fell 22%' / 'rose 5%' / 'was roughly flat' (for a past-tense clause)."""
    if abs(pct) < 0.5:
        return "was roughly flat"
    return f"{'fell' if pct < 0 else 'rose'} {abs(pct):.0f}%"


def _money(x: float) -> str:
    return f"-${abs(x):,.0f}" if x < 0 else f"${x:,.0f}"


def build_explanations(result: dict[str, Any]) -> dict[str, list[str]]:
    """Build every plain-English section from a compute_portfolio() result.

    Returns {section_name: [sentence, ...]}. Sections with nothing to say are
    empty lists, and the page simply hides them.
    """
    out: dict[str, list[str]] = {
        "overview": [], "risk_score": [], "concentration": [], "funds": [],
        "volatility": [], "correlation": [], "drawdown": [], "benchmark": [],
        "behavioral": [], "tax": [], "reflect": [],
    }
    rows = result["rows"]

    # --- overview ---------------------------------------------------------------
    out["overview"].append(
        f"This portfolio is worth about ${result['total_value']:,.0f} across {len(rows)} holding(s)."
    )
    window = result.get("analysis_window")
    if window:
        out["overview"].append(
            f"History-based numbers below use {window['start']} to {window['end']} "
            f"(about {window['years']:g} years), the period every holding has price data for."
        )

    if result.get("risk_score") is not None:
        out["risk_score"].append(
            f"Overall risk score: {result['risk_score']:.0f}/100 ({result['risk_label']}). "
            f"This blends concentration, sector overlap, volatility, correlation between "
            f"holdings, and historical drawdown into one number. It's a simple heuristic, "
            f"not a formal risk model, meant to give you one thing to watch move over time."
        )

    # --- concentration ------------------------------------------------------------
    if result.get("effective_holdings") is not None and len(rows) > 1:
        hhi = result.get("hhi")
        hhi_note = f" (Herfindahl-Hirschman index {hhi:.2f})" if hhi is not None else ""
        eff, n = result["effective_holdings"], len(rows)
        if eff / n < 0.75:
            out["concentration"].append(
                f"You hold {n} positions, but because they're not sized equally, this portfolio "
                f"behaves like about {eff:g} evenly sized holdings{hhi_note}, not {n}. That gap is "
                f"what concentration risk actually looks like in practice."
            )
        else:
            out["concentration"].append(
                f"Your {n} positions are fairly evenly sized: the portfolio behaves like about "
                f"{eff:g} equal holdings{hhi_note}."
            )

    c = result["concentration"]
    if not c["top_ticker"] and c.get("fund_pct"):
        out["concentration"].append(
            f"Everything here is in diversified funds, so no single company dominates the "
            f"portfolio. The largest position, {c.get('largest_ticker')} at {c.get('largest_pct', 0):.0f}%, "
            f"is itself spread across many underlying holdings."
        )
    elif c["top_ticker"] and c.get("fund_pct", 0) > 0 and c.get("largest_ticker") != c["top_ticker"]:
        out["concentration"].append(
            f"{c['fund_pct']:.0f}% of the portfolio is in diversified funds, which spread risk across "
            f"many companies; the concentration check below looks at individual stocks only."
        )
    if c["top_ticker"]:
        if c["flagged"]:
            out["concentration"].append(
                f"{c['top_ticker']} makes up {c['top_pct']:.0f}% of this portfolio, which is "
                f"concentrated (above {config.CONCENTRATION_FLAG_PCT:.0f}%). If {c['top_ticker']} "
                f"has a bad year, this portfolio has a bad year, almost regardless of anything else in it."
            )
        else:
            out["concentration"].append(
                f"The largest individual stock is {c['top_ticker']} at {c['top_pct']:.0f}%, "
                f"not an alarming concentration on its own."
            )

    for sector, pct in result["flagged_sectors"].items():
        out["concentration"].append(
            f"{pct:.0f}% of this portfolio sits in {sector}. That's less diversified than it "
            f"looks even if the individual companies seem different: a bad year for that "
            f"sector hits most of the portfolio at once."
        )

    asset_mix = result.get("asset_class_pct") or {}
    if asset_mix and set(asset_mix) != {"Other / unknown"}:
        parts = ", ".join(f"{name} {pct:.0f}%" for name, pct in
                          sorted(asset_mix.items(), key=lambda kv: -kv[1]))
        out["concentration"].append(f"By asset class: {parts}.")
        single = result.get("single_stock_pct") or 0.0
        if single >= 99.5 and len(rows) > 1:
            out["concentration"].append(
                "Everything here is individual stocks. Each company's own news (earnings "
                "misses, lawsuits, management changes) can move your money, which funds "
                "spread across hundreds of companies largely avoid."
            )

    # --- funds ---------------------------------------------------------------------
    for flag in result.get("fund_flags", []):
        template = FUND_EXPLAINERS.get(flag["type"])
        if template:
            out["funds"].append(template.format(ticker=flag["ticker"], value=flag["value"]))
    if result.get("weighted_expense_ratio_pct") is not None and result.get("annual_fee_dollars") is not None:
        out["funds"].append(
            f"Across the funds you hold, the value-weighted expense ratio is about "
            f"{result['weighted_expense_ratio_pct']:.2f}%, roughly ${result['annual_fee_dollars']:,.0f} "
            f"a year in fees at today's balances."
        )
    if result.get("portfolio_yield_pct") is not None:
        out["funds"].append(
            f"Based on the yields Yahoo Finance reports, this portfolio's dividend yield is "
            f"about {result['portfolio_yield_pct']:.2f}% a year."
        )

    # --- volatility & risk-adjusted return -----------------------------------------
    if result["portfolio_vol"] is not None:
        out["volatility"].append(
            f"Based on that history, this portfolio's value has swung by roughly "
            f"{result['portfolio_vol']:.0f}% a year (annualized volatility). Bigger swings mean "
            f"bigger paper losses along the way, even if the long-term trend is up."
        )
    if result.get("portfolio_max_drawdown") is not None:
        out["volatility"].append(
            f"The worst peak-to-trough decline in this exact mix over that period "
            f"was about {abs(result['portfolio_max_drawdown']):.0f}%."
        )
    rf_pct = result.get("risk_free_rate_pct", config.RISK_FREE_RATE * 100.0)
    if result.get("sharpe_ratio") is not None:
        out["volatility"].append(
            f"Sharpe ratio: {result['sharpe_ratio']:.2f}. That's the return earned above a "
            f"{rf_pct:.2f}% risk-free rate for each unit of volatility. Higher is better; "
            f"above 1 is generally considered strong, and below 0 means the risk didn't pay "
            f"off over this period."
        )
    if result.get("sortino_ratio") is not None:
        out["volatility"].append(
            f"Sortino ratio: {result['sortino_ratio']:.2f}. Same idea as Sharpe, but it only "
            f"counts downside swings as risk, since most investors don't mind upside surprises."
        )

    # --- correlation --------------------------------------------------------------
    for t1, t2, corr in result["high_corr_pairs"]:
        out["correlation"].append(
            f"{t1} and {t2} have a correlation of {corr:.2f} in their daily returns (on a "
            f"scale from -1 to 1). In practice, when one has a big up or down day, the other "
            f"has usually moved the same way, so holding both is closer to one bet than two."
        )

    # --- crash history -------------------------------------------------------------
    for name, dd in result["drawdown_scenarios"].items():
        pct = dd["estimated_portfolio_change_pct"]
        coverage_note = ""
        if dd["coverage_pct"] < 99:
            coverage_note = (f" (based on the {dd['coverage_pct']:.0f}% of the portfolio with "
                             f"data that far back)")
        line = (f"During the {name}, a portfolio built like this one would have "
                f"{_signed_move(pct)}{coverage_note}, based on what these specific holdings "
                f"actually did over those dates.")
        bench_pct = dd.get("benchmark_change_pct")
        if bench_pct is not None:
            line += f" Over the same dates the S&P 500 (SPY) {_past_move(bench_pct)}."
        out["drawdown"].append(line)
        context = config.CRASH_CONTEXT.get(name)
        if context:
            out["drawdown"].append(f"What happened: {context}")

    # --- benchmark ------------------------------------------------------------------
    bench = result.get("benchmark")
    if bench:
        dates = ""
        if bench.get("start_date") and bench.get("end_date"):
            dates = f" over the same dates ({bench['start_date']} to {bench['end_date']})"
        if bench.get("annualized_vol_pct") is not None and result.get("portfolio_vol") is not None:
            comp = "more" if result["portfolio_vol"] > bench["annualized_vol_pct"] else "less"
            out["benchmark"].append(
                f"This portfolio swings {comp} than the S&P 500{dates}: "
                f"{result['portfolio_vol']:.0f}% vs. the index's {bench['annualized_vol_pct']:.0f}% "
                f"annualized volatility."
            )
        if bench.get("cagr_pct") is not None and result.get("portfolio_cagr") is not None:
            comp = "outpaced" if result["portfolio_cagr"] > bench["cagr_pct"] else "trailed"
            out["benchmark"].append(
                f"It {comp} the S&P 500: {result['portfolio_cagr']:.1f}% vs. "
                f"{bench['cagr_pct']:.1f}% a year (compound annual growth rate)."
            )
        if bench.get("sharpe_ratio") is not None and result.get("sharpe_ratio") is not None:
            out["benchmark"].append(
                f"Risk-adjusted, its Sharpe ratio was {result['sharpe_ratio']:.2f} vs. "
                f"{bench['sharpe_ratio']:.2f} for the index."
            )
        if result.get("beta") is not None:
            b = result["beta"]
            out["benchmark"].append(
                f"Beta vs. the S&P 500: {b:.2f}. Historically, for every 1% move in the index, "
                f"this portfolio tended to move about {b:.2f}%"
                + (" (more sensitive than the market)." if b > 1.05 else
                   " (less sensitive than the market)." if b < 0.95 else " (about in line with it).")
            )

    # --- behavioral --------------------------------------------------------------------
    for flag in result["behavioral_flags"]:
        template = BIAS_EXPLAINERS.get(flag["type"])
        if template:
            out["behavioral"].append(template.format(ticker=flag["ticker"], detail=flag["detail"],
                                                     detail_abs=abs(flag["detail"])))

    # --- tax ------------------------------------------------------------------------------
    for tf in result["tax_flags"]:
        out["tax"].append(_tax_line(tf))
    summary = result.get("tax_summary") or {}
    if summary.get("has_cost_basis"):
        out["tax"].append(
            f"If you sold everything today: short-term {_money(summary['short_term_gain'] + summary['short_term_loss'])} "
            f"net, long-term {_money(summary['long_term_gain'] + summary['long_term_loss'])} net (unrealized, before any tax)."
        )
    if any(tf.get("status") == "loss" for tf in result["tax_flags"]):
        out["tax"].append(
            "Selling at a loss can offset gains, but the wash-sale rule disallows the loss if "
            "you buy the same or a substantially identical investment within 30 days before or after."
        )
    if out["tax"]:
        out["tax"].append(TAX_DISCLAIMER)

    # --- reflection prompts: questions, not advice ----------------------------------
    reflect = []
    if result.get("risk_label") == "Very High":
        reflect.append(
            "This scores as very high risk. If it dropped 30% tomorrow, would you be able "
            "to leave it alone, or would you feel pressure to sell?"
        )
    elif result.get("risk_label") == "High":
        reflect.append(
            "This scores as high risk. Is that level of swings something you chose "
            "deliberately, or did it build up one purchase at a time?"
        )

    worst_dd = None
    for name, dd in result["drawdown_scenarios"].items():
        v = dd["estimated_portfolio_change_pct"]
        if worst_dd is None or v < worst_dd[1]:
            worst_dd = (name, v)
    if worst_dd and worst_dd[1] <= -20:
        reflect.append(
            f"This mix would have lost about {abs(worst_dd[1]):.0f}% during the {worst_dd[0]}. "
            f"If that happened again next month, would you need this money soon, or could you "
            f"leave it alone?"
        )

    if result["behavioral_flags"]:
        reflect.append(
            "A few of your own buying patterns got flagged above. None of them are automatically "
            "wrong, but noticing the pattern is what lets you decide if it's actually serving you."
        )

    out["reflect"] = reflect[:3]
    return out


def _tax_line(tf: dict[str, Any]) -> str:
    """One sentence per position, aware of term AND whether it's a gain or loss."""
    t, days = tf["ticker"], tf["holding_days"]
    status = tf.get("status", "unknown")
    gain = tf.get("unrealized_gain")
    if tf["term"] == "long-term":
        if status == "loss":
            return (f"{t}: held {days} days (more than a year), currently at a {_money(abs(gain))} loss. "
                    f"Selling would realize a long-term capital loss, which can offset gains.")
        amount = f" on about {_money(gain)} of gain" if status == "gain" else ""
        return (f"{t}: held {days} days (more than a year). If you sold today{amount}, the gain "
                f"would be taxed at the lower long-term capital gains rates (0%, 15% or 20% federally, depending on income).")
    wait = tf.get("days_until_long_term")
    wait_note = f" It becomes long-term in {wait} day(s)." if wait else ""
    if status == "loss":
        return (f"{t}: held {days} days (a year or less), currently at a {_money(abs(gain))} loss. "
                f"Selling would realize a short-term capital loss.{wait_note}")
    amount = f" on about {_money(gain)} of gain" if status == "gain" else ""
    return (f"{t}: held {days} days (a year or less). If you sold today{amount}, any gain would be "
            f"taxed as short-term, at your ordinary income tax rate, which is usually higher.{wait_note}")
