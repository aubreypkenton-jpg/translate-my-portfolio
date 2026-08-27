"""
Turns the already-computed flags into a pass/warn/n-a checklist -- a report
card view of the same underlying numbers everything else on the page uses.
No new metrics are computed here; this is purely a presentation layer over
compute.py's output, kept separate because "how do we summarize this as a
checklist" is a different concern from "how do we calculate it."
"""
from . import config


def build_checklist(result):
    items = []

    c = result["concentration"]
    items.append({
        "label": f"No single holding over {config.CONCENTRATION_FLAG_PCT:.0f}% of the portfolio",
        "status": "warn" if c["flagged"] else "pass",
        "detail": f"{c['top_ticker']} is {c['top_pct']:.0f}%" if c["top_ticker"] else "n/a",
    })

    items.append({
        "label": f"No single sector over {config.SECTOR_FLAG_PCT:.0f}% of the portfolio",
        "status": "warn" if result["flagged_sectors"] else "pass",
        "detail": ", ".join(f"{s} {p:.0f}%" for s, p in result["flagged_sectors"].items()) or "n/a",
    })

    items.append({
        "label": "No two holdings are highly correlated (>70%)",
        "status": "warn" if result["high_corr_pairs"] else "pass",
        "detail": ", ".join(f"{a}/{b} {c*100:.0f}%" for a, b, c in result["high_corr_pairs"]) or "n/a",
    })

    if result.get("sharpe_ratio") is not None:
        items.append({
            "label": "Positive risk-adjusted return (Sharpe ratio above 0)",
            "status": "pass" if result["sharpe_ratio"] > 0 else "warn",
            "detail": f"{result['sharpe_ratio']:.2f}",
        })
    else:
        items.append({"label": "Positive risk-adjusted return (Sharpe ratio above 0)",
                       "status": "na", "detail": "not enough price history"})

    items.append({
        "label": "No flagged buying-pattern biases",
        "status": "warn" if result["behavioral_flags"] else "pass",
        "detail": f"{len(result['behavioral_flags'])} flagged" if result["behavioral_flags"] else "n/a",
    })

    if result.get("risk_score") is not None:
        items.append({
            "label": "Overall risk score is Moderate or lower",
            "status": "pass" if result["risk_score"] < 50 else "warn",
            "detail": f"{result['risk_score']:.0f}/100 ({result['risk_label']})",
        })

    return items
