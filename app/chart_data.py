"""
Builds JSON-serializable chart data for the front end (Chart.js).

Kept separate from compute.py so the financial math stays free of "how should
this be drawn" concerns. Nothing new is calculated here beyond reshaping:
sorting, rebasing, and thinning long daily series so the page stays fast.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

MAX_POINTS = 400  # ~5 years of daily data thinned to roughly weekly points


def _thin(series: pd.Series, max_points: int = MAX_POINTS) -> pd.Series:
    """Keep every k-th point (always including the last) so charts stay light."""
    if len(series) <= max_points:
        return series
    step = -(-len(series) // max_points)  # ceiling division
    picked = series.iloc[::step]
    if picked.index[-1] != series.index[-1]:
        picked = pd.concat([picked, series.iloc[[-1]]])
    return picked


def _sorted_bars(pct_by_label: dict[str, float]) -> dict[str, list]:
    items = sorted(pct_by_label.items(), key=lambda kv: -kv[1])
    return {"labels": [k for k, _ in items], "values": [round(v, 1) for _, v in items]}


def build_chart_data(result: dict[str, Any], price_histories: dict[str, pd.Series] | None = None
                     ) -> dict[str, Any]:
    """Shape a compute_portfolio() result into what charts.js draws."""
    rows = result["rows"]

    allocation = _sorted_bars({r["ticker"]: r["weight_pct"] for r in rows})
    allocation["dollars"] = [round(next(r["value"] for r in rows if r["ticker"] == t), 2)
                             for t in allocation["labels"]]

    growth: dict[str, Any] = {"dates": [], "portfolio": [], "benchmark": []}
    drawdown: dict[str, Any] = {"dates": [], "portfolio": [], "benchmark": []}
    port = result.get("portfolio_index")
    bench = result.get("benchmark_index")
    if port is not None and len(port) > 1:
        frame = pd.DataFrame({"portfolio": port})
        if bench is not None and len(bench) > 1:
            frame["benchmark"] = bench.reindex(frame.index).ffill()
            frame["benchmark"] = frame["benchmark"] / frame["benchmark"].dropna().iloc[0]
        frame = frame.dropna(how="all")
        dd = frame / frame.cummax() - 1.0
        thin_idx = _thin(frame["portfolio"]).index
        growth["dates"] = drawdown["dates"] = [str(d) for d in thin_idx]
        # growth of $10,000, the format fund fact sheets use
        growth["portfolio"] = [round(float(v) * 10000, 2) for v in frame.loc[thin_idx, "portfolio"]]
        drawdown["portfolio"] = [round(float(v) * 100, 2) for v in dd.loc[thin_idx, "portfolio"]]
        if "benchmark" in frame:
            growth["benchmark"] = [None if pd.isna(v) else round(float(v) * 10000, 2)
                                   for v in frame.loc[thin_idx, "benchmark"]]
            drawdown["benchmark"] = [None if pd.isna(v) else round(float(v) * 100, 2)
                                     for v in dd.loc[thin_idx, "benchmark"]]

    return {
        "allocation": allocation,
        "sectors": _sorted_bars(result.get("sector_pct") or {}),
        "asset_classes": _sorted_bars(result.get("asset_class_pct") or {}),
        "growth": growth,
        "drawdown": drawdown,
        "correlation": result.get("correlation_matrix"),
    }
