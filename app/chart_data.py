"""
Builds JSON-serializable chart data for the front end (Chart.js). Kept
separate from compute.py so the pure financial math stays free of any
"how should this be visualized" concerns.
"""

REBASE_WINDOW_DAYS = 504  # ~2 trading years


def build_chart_data(result, price_histories):
    rows = result["rows"]

    allocation = {
        "labels": [r["ticker"] for r in rows],
        "values": [round(r["value"], 2) for r in rows],
    }

    sector_pct = result.get("sector_pct") or {}
    sectors = {
        "labels": list(sector_pct.keys()),
        "values": [round(v, 1) for v in sector_pct.values()],
    }

    # rebased price history, aligned on the intersection of available dates
    tickers = [r["ticker"] for r in rows if r["ticker"] in price_histories]
    rebased = {"dates": [], "series": {}}
    if tickers:
        common_index = None
        for t in tickers:
            idx = set(price_histories[t].dropna().index)
            common_index = idx if common_index is None else (common_index & idx)
        if common_index:
            sorted_dates = sorted(common_index)[-REBASE_WINDOW_DAYS:]
            rebased["dates"] = sorted_dates
            for t in tickers:
                series = price_histories[t].loc[sorted_dates]
                base = series.iloc[0]
                rebased["series"][t] = [round(float(v) / float(base) * 100.0, 2) for v in series]

    correlation = result.get("correlation_matrix")

    return {
        "allocation": allocation,
        "sectors": sectors,
        "rebased": rebased,
        "correlation": correlation,
    }
