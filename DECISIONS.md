# Decisions

**Why yfinance instead of a paid API.** No signup, no API key, no cost: the
best fit for a free personal tool. It's an unofficial wrapper around Yahoo
Finance data, which is fine for a small personal-scale tool; it would not be
what you'd reach for at real institutional volume.

**Why template-based explanations instead of calling an LLM.** Every sentence
is built directly from a number that came out of `compute.py`, which came
from real fetched prices. There is no generation step where a model could
invent a statistic. This was the core positioning decision for the whole
project: the pitch against tools like Rogo/Hebbia is "grounded in your real
numbers, always," and an LLM writing the explanations would undercut that,
even used carefully. It also means zero ongoing LLM API cost.

**Why manual entry instead of brokerage linking (Plaid, etc.) for v1.**
Brokerage linking adds real complexity (OAuth, compliance, security surface)
for a feature that isn't needed to prove the concept. Manual entry also means
the user is the one typing in their own numbers, which was flagged early on
as part of the point; you learn more entering your own holdings than
watching them auto-import.

**Why these two crash windows (COVID 2020, 2022 bear market).** Both are
recent, well-known, and severe enough to be meaningful reference points, and
both have complete daily price history available for virtually any ticker
that existed at the time.

**Concentration/correlation/loss-aversion thresholds are simple fixed
numbers** (25% single holding, 50% single sector, 0.7 correlation, -20% loss
held 180+ days, 15% run-up before purchase). These are reasonable defaults,
not calibrated against real behavioral-finance literature, and calibrating them is a natural next
step if this grows past a personal tool.

---

## v2 decisions (October 2026)

**One copy of the app.** An older single-file version (`app.py`, `compute.py`, `data_fetch.py`,
`explain.py`, `templates/`, `static/`) lived next to the real `app/` package, and the README's
`python app.py` launched the old one. It was removed so there is exactly one `data_fetch.py`.

**One process, four threads.** Free hosts give about 512 MB of RAM, and the price cache and rate
limiter live in memory. One gunicorn worker with threads keeps them shared by every request; two
workers would each keep their own copy. The 120-second timeout covers a cold, many-ticker analysis.

**Telling an outage from a typo.** yfinance often logs network errors and returns an empty table
instead of raising, which looks exactly like a mistyped ticker. When every ticker comes back empty,
the app checks SPY (which always has data); if SPY is empty too, it reports a provider problem and
does not remember the user's tickers as invalid.

**Sharpe from daily excess returns.** v1 divided CAGR (a compound return) by volatility of daily
returns. v2 uses the textbook ex-post Sharpe: mean daily excess return over standard deviation,
times sqrt(252), so numerator and denominator come from the same data. The risk-free rate is a user
input (default 4%) because the right value changes over time.

**Benchmark over identical dates.** Portfolio history only exists on dates all holdings share, so the
S&P 500 is cut to the same window before any comparison.

**Constant weights.** Portfolio history replays today's weights, rebalanced daily. That answers "how
has this mix behaved," which is what the report is about, and avoids needing every trade the user
ever made. Stated on the methodology page.

**IRS holding period.** Long-term requires holding more than one year, counted from the day after
purchase (IRS Publication 550). v1 used `>= 365 days`, which mislabeled exactly-one-year positions.

**Funds excluded from single-holding concentration.** 40% in a total-market ETF is not the same risk
as 40% in one company. Diversified funds are excluded from the single-holding and sector checks
(and from that part of the risk score) but still count in the HHI, which measures position sizing.

**Crash scenarios re-weighted over covered holdings.** If a holding didn't exist during a crash
window, the scenario is averaged over the holdings that did and the coverage percent is shown, rather
than silently counting the missing holding as 0%.

**Self-hosted Chart.js.** Bundled (MIT) instead of loaded from a CDN, so charts work even if a CDN is
blocked (school networks) or down.

**Hosting.** Replit keeps the original link (free published apps expire after 30 days and must be
republished); Render (Docker, `render.yaml`) is the backup; `railway.json` and the Dockerfile cover
anything else. All read `PORT` through `gunicorn.conf.py`.
