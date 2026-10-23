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
    "hhi": (
        "Herfindahl-Hirschman index (HHI): the sum of each holding's squared weight. It runs "
        "from near 0 (many tiny holdings) to 1 (everything in one); 1/HHI is the 'effective' number of holdings."
    ),
    "asset_class": (
        "Asset class: the broad kind of investment (individual stock, ETF, mutual fund, crypto). "
        "Funds hold many companies at once; an individual stock is a bet on one."
    ),
    "sortino_ratio": (
        "Sortino ratio: like the Sharpe ratio, but only downside swings count as risk, "
        "so a fund isn't penalized for big up days."
    ),
    "beta": (
        "Beta: how much a portfolio has tended to move when the market moves. 1.0 moves with "
        "the S&P 500; 1.3 moves about 30% more; 0.7 about 30% less."
    ),
    "expense_ratio": (
        "Expense ratio: the yearly fee a fund charges, as a percent of what you have invested. "
        "0.50% means $5 a year for every $1,000."
    ),
    "dividend_yield": (
        "Dividend yield: a year of dividends divided by the current price. Higher isn't automatically "
        "better; a falling price pushes the yield up."
    ),
    "wash_sale": (
        "Wash-sale rule: if you sell at a loss and buy the same or a substantially identical "
        "investment within 30 days before or after, the IRS disallows that loss for now."
    ),
    "risk_score": (
        "Risk score: this app's own 0-100 blend of concentration, volatility, correlation, "
        "and drawdown into one number, meant to give you something simple to track over time."
    ),
}

# maps an explanation section (from explain.py) to the glossary terms it can surface
SECTION_TERMS = {
    "concentration": ["concentration", "diversification", "hhi", "asset_class"],
    "funds": ["expense_ratio", "dividend_yield"],
    "volatility": ["volatility", "max_drawdown", "sharpe_ratio", "sortino_ratio"],
    "benchmark": ["cagr", "beta"],
    "correlation": ["correlation"],
    "behavioral": ["recency_bias", "loss_aversion"],
    "tax": ["capital_gains", "wash_sale"],
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
