"""
Beginner lessons for the /learn page, plus a pure function that recommends
lessons based on what a specific report flagged.

Same rule as the rest of the app: fixed, human-written text and numbers
computed by code; nothing is generated. Lessons explain concepts; they are
not advice. Sources are official investor-education sites (SEC, FINRA, IRS).
"""
from __future__ import annotations

from typing import Any

from . import config


def _fee_example(start: float = 10_000.0, gross_return: float = 0.07, years: int = 30,
                 fees: tuple[float, ...] = (0.0003, 0.0050, 0.0100)) -> list[dict[str, float]]:
    """Ending balance of the same investment under different yearly fees.

    Simple illustration: fee subtracted from an assumed constant return each
    year. Real returns vary; the point is how a small yearly fee compounds.
    """
    return [{"fee_pct": f * 100, "ending": start * (1 + gross_return - f) ** years} for f in fees]


FEE_EXAMPLE = _fee_example()

SOURCES = {
    "investor_gov": ("Investor.gov (U.S. Securities and Exchange Commission)", "https://www.investor.gov/"),
    "finra": ("FINRA investor education", "https://www.finra.org/investors"),
    "irs_550": ("IRS Publication 550: Investment Income and Expenses", "https://www.irs.gov/publications/p550"),
    "irs_590a": ("IRS Publication 590-A: Contributions to IRAs", "https://www.irs.gov/publications/p590a"),
}

# Each lesson: id (URL anchor), title, one-line "why it matters", body
# paragraphs, optional "watch out" callout, the report section it maps to,
# and the source keys above.
LESSONS: list[dict[str, Any]] = [
    {
        "id": "what-you-own",
        "title": "What you actually own: stocks, ETFs, and funds",
        "why": "The same $1,000 can be one company or five hundred, depending on the ticker.",
        "body": [
            "A stock is a slice of one company. If that company has a bad year, so does your money.",
            "An ETF (exchange-traded fund) or mutual fund is a basket. An S&P 500 index fund holds about 500 large "
            "US companies, so one company's bad news barely moves it. ETFs trade during the day like stocks; mutual "
            "funds are priced once a day after the market closes.",
            "Index funds simply copy an index instead of paying a manager to pick stocks, which is why they are "
            "usually much cheaper.",
        ],
        "in_report": "The Holdings table's Type column and the Asset class mix chart.",
        "sources": ["investor_gov"],
    },
    {
        "id": "diversification",
        "title": "Diversification and concentration",
        "why": "Owning many tickers isn't the same as being diversified.",
        "body": [
            "Diversification means owning things that don't all go down for the same reason. Five tech stocks are "
            "five tickers but close to one bet on tech.",
            "This app measures it two ways: the largest single stock as a percent of your money, and the "
            "Herfindahl-Hirschman index (HHI), which turns your position sizes into an \"effective number of holdings.\" "
            f"It flags any single stock above {config.CONCENTRATION_FLAG_PCT:.0f}% and any sector above "
            f"{config.SECTOR_FLAG_PCT:.0f}%.",
        ],
        "watch_out": "Your employer's stock, or a stock you love, is where concentration usually sneaks in.",
        "in_report": "Concentration section, Sector mix chart, and the effective holdings number.",
        "sources": ["investor_gov", "finra"],
    },
    {
        "id": "risk",
        "title": "Risk you can feel: volatility and drawdowns",
        "why": "The average return hides how bumpy the ride was.",
        "body": [
            "Volatility is how much a price swings, measured as the standard deviation of daily returns, scaled to a "
            "year. Higher volatility means bigger paper gains and losses along the way.",
            "Maximum drawdown is the worst fall from a peak to a low point. It answers a very practical question: "
            "how much would you have had to watch disappear before it came back?",
            "Many investors lose money not because the market fell, but because they sold near the bottom. Knowing "
            "your portfolio's real drawdown history ahead of time makes it easier to sit through the next one.",
        ],
        "in_report": "Volatility section and the Drawdown chart compared with the S&P 500.",
        "sources": ["investor_gov"],
    },
    {
        "id": "risk-adjusted",
        "title": "Return per unit of risk: Sharpe, Sortino, and beta",
        "why": "Two portfolios with the same return aren't equally good if one was twice as bumpy.",
        "body": [
            "The Sharpe ratio is the return above a risk-free rate (like a Treasury bill) divided by volatility. "
            "Above 1 is generally considered strong; below 0 means you'd have done better in cash.",
            "The Sortino ratio is similar but only counts downside swings as risk.",
            "Beta compares your portfolio's moves with the market's. A beta of 1.3 means it has tended to move about "
            "1.3% when the S&P 500 moves 1%, in both directions.",
        ],
        "in_report": "Overview tiles and the Vs. the S&P 500 section.",
        "sources": ["investor_gov"],
    },
    {
        "id": "correlation",
        "title": "Hidden overlap: correlation",
        "why": "Two holdings that rise and fall together don't protect each other.",
        "body": [
            "Correlation runs from -1 to +1. Near +1 means two holdings' daily moves line up closely; near 0 means "
            "they're unrelated; negative means they tend to move opposite ways.",
            f"This app flags pairs above {config.HIGH_CORRELATION}. A common surprise: an S&P 500 fund and big tech "
            "stocks are highly correlated, because those stocks are a large part of the index.",
        ],
        "in_report": "Hidden overlap section and the correlation heatmap.",
        "sources": ["finra"],
    },
    {
        "id": "fees",
        "title": "Fees: the small number that compounds",
        "why": "A 1% yearly fee sounds tiny and can cost a large share of your ending balance.",
        "body": [
            "A fund's expense ratio is its yearly fee as a percent of what you invest; it comes out automatically, "
            "whether the fund does well or not.",
            "The illustration below assumes $10,000, a steady 7% yearly return before fees, and 30 years. Real "
            "returns vary year to year; the point is how the fee compounds.",
        ],
        "fee_example": True,
        "in_report": "Fund fees and dividends section.",
        "sources": ["investor_gov", "finra"],
    },
    {
        "id": "dividends",
        "title": "Dividends and the yield trap",
        "why": "A very high yield is often a warning sign, not a bargain.",
        "body": [
            "Dividend yield is a year of dividends divided by today's price. When a stock's price falls, its yield "
            "rises automatically, so an unusually high yield can mean the market expects the dividend to be cut.",
            "Dividends are also taxed in the year you receive them in a regular (taxable) account, even if you "
            "reinvest them.",
        ],
        "in_report": "Fund fees and dividends section.",
        "sources": ["investor_gov", "irs_550"],
    },
    {
        "id": "taxes",
        "title": "Cost basis, tax lots, and short vs. long term",
        "why": "When you sell, and which shares you sell, changes your tax bill.",
        "body": [
            "Cost basis is what you paid. Every purchase is its own tax lot with its own price and date, so if you "
            "invest every month you own many lots of the same fund.",
            "A lot held more than one year is long-term when sold; federal long-term rates are 0%, 15% or 20% "
            "depending on income. A year or less is short-term and taxed like regular income.",
            "Selling at a loss can offset gains, but the wash-sale rule disallows the loss if you buy the same or a "
            "substantially identical investment within 30 days before or after.",
        ],
        "watch_out": "This is general education about US federal rules, not tax advice. State taxes and your "
                     "situation change the real answer.",
        "in_report": "Capital gains basics table (one row per purchase).",
        "sources": ["irs_550"],
    },
    {
        "id": "dca",
        "title": "Investing regularly and your own biases",
        "why": "A plan you follow beats a perfect plan you abandon.",
        "body": [
            "Investing a fixed amount on a schedule (dollar-cost averaging) means you automatically buy more shares "
            "when prices are low and fewer when they're high, and it takes the \"is now the right time?\" question "
            "off the table.",
            "Common traps: recency bias (buying because something just went up), loss aversion (holding a loser "
            "just to get back to even), and making a big bet quickly on something new and exciting.",
        ],
        "in_report": "Your buying patterns section (needs purchase prices and dates).",
        "sources": ["investor_gov", "finra"],
    },
    {
        "id": "brokerage-app",
        "title": "Inside a brokerage app: the buttons that matter",
        "why": "Most beginner mistakes happen on the order screen, not in the portfolio.",
        "body": [
            "Market vs. limit orders: a market order buys right away at whatever the current price is; a limit order "
            "only fills at your price or better. Limit orders protect you in fast-moving or thinly traded stocks.",
            "Fractional shares let you invest a dollar amount instead of buying whole shares, which makes "
            "diversifying with small amounts much easier.",
            "Recurring investments automate dollar-cost averaging; this is often the single most useful feature "
            "for a beginner.",
            "Account type matters: a regular brokerage account is taxable each year, while retirement accounts like "
            "a Roth IRA have tax advantages and rules about contributions and withdrawals. A Roth IRA generally "
            "requires earned income (for example, from a job), and the yearly contribution limit changes, so check "
            "the IRS for the current numbers.",
        ],
        "watch_out": "Margin (borrowing from your broker) and options can lose more than you expected, quickly. "
                     "They are worth understanding well before using, not features to try out.",
        "in_report": "Not a report section: this is about how you place trades.",
        "sources": ["finra", "investor_gov", "irs_590a"],
    },
]

LESSON_IDS = {lesson["id"] for lesson in LESSONS}


def recommend_lessons(result: dict[str, Any], limit: int = 3) -> list[dict[str, str]]:
    """Pick the lessons most relevant to THIS report, each with the reason.

    Pure function over compute.py's output: every reason quotes a number the
    report already shows, so recommendations are as traceable as the metrics.
    """
    recs: list[dict[str, str]] = []

    def add(lesson_id: str, reason: str) -> None:
        if lesson_id in LESSON_IDS and all(r["id"] != lesson_id for r in recs):
            title = next(lesson["title"] for lesson in LESSONS if lesson["id"] == lesson_id)
            recs.append({"id": lesson_id, "title": title, "reason": reason})

    c = result.get("concentration") or {}
    if c.get("flagged"):
        add("diversification", f"{c['top_ticker']} is {c['top_pct']:.0f}% of your portfolio.")
    for sector, pct in (result.get("flagged_sectors") or {}).items():
        add("diversification", f"{pct:.0f}% of your money is in {sector}.")
        break
    if result.get("high_corr_pairs"):
        a, b, v = result["high_corr_pairs"][0]
        add("correlation", f"{a} and {b} have a {v:.2f} correlation.")
    fee_flags = [f for f in result.get("fund_flags", []) if f["type"] == "high_expense_ratio"]
    if fee_flags:
        add("fees", f"{fee_flags[0]['ticker']} charges about {fee_flags[0]['value']:.2f}% a year.")
    yield_flags = [f for f in result.get("fund_flags", []) if f["type"] == "high_dividend_yield"]
    if yield_flags:
        add("dividends", f"{yield_flags[0]['ticker']} shows a {yield_flags[0]['value']:.1f}% yield.")
    dd = result.get("portfolio_max_drawdown")
    if dd is not None and dd <= -30:
        add("risk", f"This mix has fallen as much as {abs(dd):.0f}% from a peak.")
    if result.get("behavioral_flags"):
        add("dca", "Some of your own purchases were flagged in Your buying patterns.")
    if any(f.get("term") == "short-term" and f.get("status") == "gain" for f in result.get("tax_flags", [])):
        add("taxes", "Some purchases would be taxed at short-term rates if sold today.")
    if (result.get("single_stock_pct") or 0) >= 99.5 and len(result.get("rows", [])) > 0:
        add("what-you-own", "Everything here is individual stocks.")
    if result.get("sharpe_ratio") is not None:
        add("risk-adjusted", f"Your Sharpe ratio is {result['sharpe_ratio']:.2f}; here's what that means.")
    return recs[:limit]
