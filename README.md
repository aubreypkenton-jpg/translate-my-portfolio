# Translate My Portfolio

Type in what you own (ticker, shares, and optionally what you paid and when).
Get back a plain-English breakdown of:

- **Concentration** — how much of your money is riding on one company or one sector
- **Volatility** — how much this portfolio actually swings, in real terms
- **Hidden overlap** — holdings that move together even if they don't look related
- **Real crash history** — what this exact portfolio would have done during the 2020
  COVID crash and the 2022 bear market, using real historical prices
- **Your buying patterns** — flags like recency bias (buying after a run-up) and
  loss aversion (holding a loser too long), based on your actual purchase dates/prices
- **Tax basics** — short-term vs. long-term capital gains on what you hold today

No login, nothing saved, no brokerage integration, and no incentive to get you to trade —
this doesn't make money whether you buy, sell, or do nothing.

## Running locally

```
pip install -r requirements.txt
python app.py
```

Then open http://localhost:8080

## Deploying (free)

Push this folder to a GitHub repo, then import it into Replit or connect it to
Render/Railway's free tier. No API keys needed — it uses the free `yfinance`
library for all market data.

## Files

- `data_fetch.py` — the only file that talks to the internet (yfinance)
- `compute.py` — pure math on the fetched data (no network, unit-testable)
- `explain.py` — turns the computed numbers into plain-English sentences (template-based, not an LLM)
- `app.py` — the Flask web app tying it together
- `templates/`, `static/` — the page itself
