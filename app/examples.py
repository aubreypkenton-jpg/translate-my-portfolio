"""Sample portfolios for the "Try an example" buttons.

These are illustrative inputs only, not recommendations. Purchase prices and
dates are made up for demonstration; everything the app *computes* from them
still comes from real price history.
"""
from __future__ import annotations

EXAMPLE_PORTFOLIOS: list[dict] = [
    {
        "id": "tech",
        "label": "Tech-heavy starter",
        "blurb": "A few big tech names plus an S&P 500 fund. Shows concentration and correlation flags.",
        "holdings": [
            {"ticker": "AAPL", "shares": "10", "purchase_price": "150", "purchase_date": "2022-06-01"},
            {"ticker": "MSFT", "shares": "5", "purchase_price": "250", "purchase_date": "2021-03-15"},
            {"ticker": "NVDA", "shares": "15", "purchase_price": "", "purchase_date": ""},
            {"ticker": "SPY", "shares": "8", "purchase_price": "380", "purchase_date": "2023-01-10"},
        ],
    },
    {
        "id": "three-fund",
        "label": "Three-fund index",
        "blurb": "US stocks, international stocks, and bonds through low-cost index ETFs.",
        "holdings": [
            {"ticker": "VTI", "shares": "20", "purchase_price": "", "purchase_date": ""},
            {"ticker": "VXUS", "shares": "40", "purchase_price": "", "purchase_date": ""},
            {"ticker": "BND", "shares": "35", "purchase_price": "", "purchase_date": ""},
        ],
    },
    {
        "id": "income",
        "label": "Dividend focused",
        "blurb": "Income-oriented funds and a REIT. Shows the dividend-yield and fee flags.",
        "holdings": [
            {"ticker": "SCHD", "shares": "60", "purchase_price": "", "purchase_date": ""},
            {"ticker": "VYM", "shares": "15", "purchase_price": "", "purchase_date": ""},
            {"ticker": "O", "shares": "30", "purchase_price": "", "purchase_date": ""},
            {"ticker": "JEPI", "shares": "30", "purchase_price": "", "purchase_date": ""},
        ],
    },
    {
        "id": "single-stock",
        "label": "One big bet",
        "blurb": "Mostly one stock. Shows what a high risk score and a lopsided HHI look like.",
        "holdings": [
            {"ticker": "TSLA", "shares": "40", "purchase_price": "", "purchase_date": ""},
            {"ticker": "VOO", "shares": "2", "purchase_price": "", "purchase_date": ""},
        ],
    },
]
