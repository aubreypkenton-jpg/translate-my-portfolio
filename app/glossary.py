"""
A plain-English glossary, shown on the results page but ONLY for terms that
actually appear in that specific analysis -- no point defining "Sharpe
ratio" for someone whose result didn't compute one. This is the main
mechanism by which the app teaches vocabulary, not just numbers.
"""

GLOSSARY = {
    "concentration": (
        "Concentration: how much of your money sits in one holding or one sector. "
        "High concentration means one bad outcome can hurt the whole portfolio."
    ),
    "diversification": (
        "Diversification: spreading money across holdings that don't all move for the "
        "same reason, so no single bad outcome sinks the whole portfolio."
    ),
    "volatility": (
        "Volatility: how much a price swings up and down over time. Higher volatility "
        "means bigger paper gains and losses along the way, even if the long-term trend is up."
    ),
    "max_drawdown": (
        "Max drawdown: the largest drop from a peak to a low point in the available "
        "history. It answers 'what's the worst this has actually done, top to bottom.'"
    ),
    "sharpe_ratio": (
        "Sharpe ratio: return earned per unit of risk taken, above a safe baseline. "
        "Higher is better -- it rewards steady gains more than a wild ride to the same place."
    ),
    "correlation": (
        "Correlation: how closely two holdings' prices move together, from -1 (opposite) "
        "to 1 (identical). High correlation means owning both isn't as diversifying as it looks."
    ),
    "cagr": (
        "CAGR (compound annual growth rate): the smoothed, per-year return that would "
        "get you from the starting value to the ending value, ignoring the bumps along the way."
    ),
    "recency_bias": (
        "Recency bias: judging something mainly by what it did most recently, like buying "
        "a stock because it just went up -- rather than on its own current merits."
    ),
    "loss_aversion": (
        "Loss aversion: the tendency to hold onto a losing investment hoping to 'get back "
        "to even,' rather than judging it fresh at today's price."
    ),
    "capital_gains": (
        "Capital gains tax: tax on profit when you sell. Short-term (held under a year) "
        "is taxed as regular income; long-term (a year or more) gets a lower rate."
    ),
    "risk_score": (
        "Risk score: this app's own 0-100 blend of concentration, volatility, correlation, "
        "and drawdown into one number, meant to give you something simple to track over time."
    ),
}

# maps an explanation section (from explain.py) to the glossary terms it can surface
SECTION_TERMS = {
    "concentration": ["concentration", "diversification"],
    "volatility": ["volatility", "max_drawdown", "sharpe_ratio"],
    "correlation": ["correlation"],
    "behavioral": ["recency_bias", "loss_aversion"],
    "tax": ["capital_gains"],
    "risk_score": ["risk_score"],
}


def relevant_glossary(explanations):
    """explanations: the dict from explain.build_explanations(). Returns an
    ordered list of (term_key, definition) for terms actually relevant to
    this specific result, so the glossary never lists something unused."""
    seen = []
    for section, terms in SECTION_TERMS.items():
        if explanations.get(section):
            for t in terms:
                if t not in seen:
                    seen.append(t)
    return [(t, GLOSSARY[t]) for t in seen]
