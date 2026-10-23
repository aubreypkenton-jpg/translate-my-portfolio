"""Central place for every tunable constant in the app.

Nothing in compute.py or explain.py should hardcode a number that belongs
here -- keeping thresholds in one file makes them easy to review, and easy
to justify in DECISIONS.md.
"""

# -- data --
HISTORY_PERIOD = "5y"          # yfinance period string; covers COVID + 2022 crash windows
BENCHMARK_TICKER = "SPY"       # S&P 500 ETF, used for "vs. the market" comparisons
CACHE_TTL_SECONDS = 15 * 60    # how long fetched price data is reused before re-fetching
FAILED_TICKER_TTL_SECONDS = 5 * 60  # remember "Yahoo has no data for X" this long
FETCH_ATTEMPTS = 3             # tries per ticker before giving up
FETCH_BACKOFF_SECONDS = 0.75   # wait before retry; doubles each time (0.75s, 1.5s)
FETCH_MAX_WORKERS = 4          # parallel Yahoo requests; kept low to avoid rate limits

# -- known historical drawdown windows, measured against REAL held-ticker prices --
CRASH_WINDOWS = {
    "2022 bear market": ("2022-01-03", "2022-10-12"),
    "COVID crash (2020)": ("2020-02-19", "2020-03-23"),
}

# one factual line of "why this happened" for each window above, so the
# numbers come with real historical context instead of floating free
CRASH_CONTEXT = {
    "2022 bear market": (
        "The Federal Reserve raised interest rates rapidly to fight the highest "
        "inflation in 40 years, which made borrowing more expensive and pulled "
        "money out of stocks, especially growth and tech names."
    ),
    "COVID crash (2020)": (
        "Fear of a global pandemic shutting down the economy triggered one of the "
        "fastest market drops in history -- and one of the fastest recoveries, once "
        "governments and central banks stepped in with massive support."
    ),
}

# -- flags / thresholds --
CONCENTRATION_FLAG_PCT = 25.0        # single holding above this % is "concentrated"
SECTOR_FLAG_PCT = 50.0               # single sector above this % is "concentrated"
HIGH_CORRELATION = 0.7               # holdings moving together above this
RECENCY_BIAS_RUNUP_PCT = 15.0        # bought this much above the 30-trading-day-ago price
LOSS_AVERSION_LOSS_PCT = -20.0       # underwater by this much...
LOSS_AVERSION_MIN_HOLD_DAYS = 180    # ...for at least this long
CONCENTRATED_RECENT_BUY_PCT = 20.0   # a holding bought this recently...
CONCENTRATED_RECENT_BUY_DAYS = 30    # ...within this many days...
                                      # ...that's already this big a bet, gets flagged

# -- risk score model (see DECISIONS.md: simple equal-weighted heuristic, not a
#    calibrated quant model) --
RISK_FREE_RATE = 0.04                # annual, used for Sharpe ratio; update periodically
RISK_SCORE_CAPS = {
    "concentration": 50.0,   # top holding % that maps to a max sub-score of 100
    "sector": 70.0,          # top sector % that maps to a max sub-score of 100
    "volatility": 40.0,      # annualized portfolio vol % that maps to 100
    "correlation": 1.0,      # correlation (0-1) that maps to 100
    "drawdown": 50.0,        # max drawdown % (absolute) that maps to 100
}
RISK_SCORE_BANDS = [
    (25, "Low"),
    (50, "Moderate"),
    (75, "High"),
    (101, "Very High"),
]
