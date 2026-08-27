# Decisions

**Why yfinance instead of a paid API.** No signup, no API key, no cost — the
best fit for a free personal tool. It's an unofficial wrapper around Yahoo
Finance data, which is fine for a small personal-scale tool; it would not be
what you'd reach for at real institutional volume.

**Why template-based explanations instead of calling an LLM.** Every sentence
is built directly from a number that came out of `compute.py`, which came
from real fetched prices. There is no generation step where a model could
invent a statistic. This was the core positioning decision for the whole
project — the pitch against tools like Rogo/Hebbia is "grounded in your real
numbers, always," and an LLM writing the explanations would undercut that,
even used carefully. It also means zero ongoing LLM API cost.

**Why manual entry instead of brokerage linking (Plaid, etc.) for v1.**
Brokerage linking adds real complexity (OAuth, compliance, security surface)
for a feature that isn't needed to prove the concept. Manual entry also means
the user is the one typing in their own numbers, which was flagged early on
as part of the point — you learn more entering your own holdings than
watching them auto-import.

**Why these two crash windows (COVID 2020, 2022 bear market).** Both are
recent, well-known, and severe enough to be meaningful reference points, and
both have complete daily price history available for virtually any ticker
that existed at the time.

**Concentration/correlation/loss-aversion thresholds are simple fixed
numbers** (25% single holding, 50% single sector, 0.7 correlation, -20% loss
held 180+ days, 15% run-up before purchase). These are reasonable defaults,
not calibrated against real behavioral-finance literature — a natural next
step if this grows past a personal tool.
