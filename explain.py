"""
Turns compute.py's numbers into plain-English explanations.

Deliberately template-based, NOT an LLM call. Every sentence is built
directly from a number that came out of compute.py, which in turn came
from real fetched price data. Nothing here is generated/guessed -- see
DECISIONS.md for why this matters for a finance-literacy tool.
"""

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
        "concentration": [],
        "volatility": [],
        "correlation": [],
        "drawdown": [],
        "behavioral": [],
        "tax": [],
    }

    total = result["total_value"]
    out["overview"].append(
        f"This portfolio is worth about ${total:,.0f} across {len(result['rows'])} holding(s)."
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
            f"Based on the last several years of price history, this portfolio's value has "
            f"swung by roughly {result['portfolio_vol']:.0f}% a year (annualized volatility). "
            f"Bigger swings mean bigger paper losses along the way, even if the long-term "
            f"trend is up."
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

    for flag in result["behavioral_flags"]:
        template = BIAS_EXPLAINERS.get(flag["type"])
        if template:
            out["behavioral"].append(template.format(ticker=flag["ticker"], detail=flag["detail"]))

    for tf in result["tax_flags"]:
        template = TERM_EXPLAINERS.get(tf["term"])
        if template:
            out["tax"].append(template.format(ticker=tf["ticker"], holding_days=tf["holding_days"]))

    return out
