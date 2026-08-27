"""
Turns compute.py's numbers into plain-English explanations.

Deliberately template-based, NOT an LLM call. Every sentence is built
directly from a number that came out of compute.py, which in turn came
from real fetched price data. Nothing here is generated or guessed --
see DECISIONS.md for why this is the central design choice of the project.
"""
from . import config

BIAS_EXPLAINERS = {
    "recency_bias": (
        "Recency bias: you bought {ticker} after it had already climbed about "
        "{detail}% in the prior month. It's a common trap -- a stock looking "
        "exciting because it just went up isn't the same as it being a good buy. "
        "Worth asking: would you buy this today, at this price, if it hadn't just moved?"
    ),
    "loss_aversion": (
        "Loss aversion: {ticker} is down about {detail}% and you've held it a "
        "while. People often keep losing positions hoping to 'get back to even' "
        "rather than judging the stock on its own merits today. Ask: if you didn't "
        "already own this, would you buy it right now at this price?"
    ),
    "concentrated_recent_buy": (
        "Fast, big bet: {ticker} is already {detail}% of this portfolio and you "
        "bought it within the last month. Moving quickly to a large position in "
        "something new is worth a second look -- was this a considered decision "
        "or a reaction to excitement?"
    ),
}

TERM_EXPLAINERS = {
    "short-term": (
        "{ticker}: held {holding_days} days. If you sold today, the gain would be taxed "
        "as short-term -- at your regular income tax rate, which is usually higher."
    ),
    "long-term": (
        "{ticker}: held {holding_days} days (over a year). If you sold today, the gain "
        "would qualify for the lower long-term capital gains tax rate."
    ),
}


def build_explanations(result):
    """result: the dict returned by compute.compute_portfolio(). Returns a
    dict of explanation sections (lists of plain-English strings)."""
    out = {
        "overview": [],
        "risk_score": [],
        "concentration": [],
        "volatility": [],
        "correlation": [],
        "drawdown": [],
        "benchmark": [],
        "behavioral": [],
        "tax": [],
        "reflect": [],
    }

    total = result["total_value"]
    out["overview"].append(
        f"This portfolio is worth about ${total:,.0f} across {len(result['rows'])} holding(s)."
    )

    if result.get("risk_score") is not None:
        out["risk_score"].append(
            f"Overall risk score: {result['risk_score']:.0f}/100 ({result['risk_label']}). "
            f"This blends concentration, sector overlap, volatility, correlation between "
            f"holdings, and historical drawdown into one number -- it's a simple heuristic, "
            f"not a formal risk model, meant to give you one thing to watch move over time."
        )

    if result.get("effective_holdings") is not None and len(result["rows"]) > 1:
        out["concentration"].append(
            f"You hold {len(result['rows'])} positions, but because they're not sized "
            f"equally, this portfolio behaves like about {result['effective_holdings']:g} "
            f"evenly-sized holdings, not {len(result['rows'])}. That gap is what "
            f"concentration risk actually looks like in practice."
        )

    c = result["concentration"]
    if c["top_ticker"]:
        if c["flagged"]:
            out["concentration"].append(
                f"{c['top_ticker']} makes up {c['top_pct']:.0f}% of this portfolio -- that's "
                f"concentrated. If {c['top_ticker']} has a bad year, this portfolio has a bad "
                f"year, almost regardless of anything else in it."
            )
        else:
            out["concentration"].append(
                f"The largest single holding is {c['top_ticker']} at {c['top_pct']:.0f}% -- "
                f"not an alarming concentration on its own."
            )

    for sector, pct in result["flagged_sectors"].items():
        out["concentration"].append(
            f"{pct:.0f}% of this portfolio sits in {sector}. That's less diversified than it "
            f"looks even if the individual companies seem different -- a bad year for that "
            f"sector hits most of the portfolio at once."
        )

    if result["portfolio_vol"] is not None:
        out["volatility"].append(
            f"Based on available price history, this portfolio's value has swung by roughly "
            f"{result['portfolio_vol']:.0f}% a year (annualized volatility). Bigger swings mean "
            f"bigger paper losses along the way, even if the long-term trend is up."
        )
    if result.get("portfolio_max_drawdown") is not None:
        out["volatility"].append(
            f"The worst peak-to-trough decline in this exact mix, over the available history, "
            f"was about {result['portfolio_max_drawdown']:.0f}%."
        )
    if result.get("sharpe_ratio") is not None:
        out["volatility"].append(
            f"Sharpe ratio: {result['sharpe_ratio']:.2f} -- roughly how much return you got per "
            f"unit of risk taken, above a ~4% risk-free baseline. Higher is better; above 1 is "
            f"generally considered good, below 0 means you took on risk that didn't pay off "
            f"over this period."
        )

    for t1, t2, corr in result["high_corr_pairs"]:
        out["correlation"].append(
            f"{t1} and {t2} move together {corr*100:.0f}% of the time historically. Holding "
            f"both isn't as diversifying as it might feel -- they're closer to one bet than two."
        )

    for name, dd in result["drawdown_scenarios"].items():
        coverage_note = ""
        if dd["coverage_pct"] < 99:
            coverage_note = f" (based on {dd['coverage_pct']:.0f}% of the portfolio -- some holdings didn't have data that far back)"
        out["drawdown"].append(
            f"During the {name}, a portfolio built like this one would have fallen roughly "
            f"{dd['estimated_portfolio_change_pct']:.0f}%{coverage_note}, based on what these "
            f"specific holdings actually did during that period."
        )
        context = config.CRASH_CONTEXT.get(name)
        if context:
            out["drawdown"].append(f"What happened: {context}")

    bench = result.get("benchmark")
    if bench:
        if bench.get("annualized_vol_pct") is not None and result.get("portfolio_vol") is not None:
            comp = "more" if result["portfolio_vol"] > bench["annualized_vol_pct"] else "less"
            out["benchmark"].append(
                f"This portfolio swings {comp} than the S&P 500 -- "
                f"{result['portfolio_vol']:.0f}% vs. the index's {bench['annualized_vol_pct']:.0f}% "
                f"annualized volatility."
            )
        if bench.get("cagr_pct") is not None and result.get("portfolio_cagr") is not None:
            comp = "outpaced" if result["portfolio_cagr"] > bench["cagr_pct"] else "trailed"
            out["benchmark"].append(
                f"Over the same period, this portfolio {comp} the S&P 500: "
                f"{result['portfolio_cagr']:.1f}% vs. {bench['cagr_pct']:.1f}% annualized."
            )

    for flag in result["behavioral_flags"]:
        template = BIAS_EXPLAINERS.get(flag["type"])
        if template:
            out["behavioral"].append(template.format(ticker=flag["ticker"], detail=flag["detail"]))

    for tf in result["tax_flags"]:
        template = TERM_EXPLAINERS.get(tf["term"])
        if template:
            out["tax"].append(template.format(ticker=tf["ticker"], holding_days=tf["holding_days"]))

    # --- reflection prompts: questions, not advice, tied to the strongest signals ---
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
            "wrong -- but noticing the pattern is what lets you decide if it's actually serving you."
        )

    out["reflect"] = reflect[:3]

    return out
