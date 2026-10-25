"""Flask web layer: reads the form, calls the pure modules, renders pages.

The flow for one analysis is always the same, and each step lives in its own
module: validate -> merge duplicates -> fetch (the only network step) ->
compute -> explain -> render.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from flask import Blueprint, jsonify, render_template, request

from . import config
from .chart_data import build_chart_data
from .checklist import build_checklist
from .compute import compute_portfolio, compute_rebalance
from .csv_import import parse_csv_with_notes
from .data_fetch import DataProviderError, fetch_benchmark, fetch_holdings_data, get_cached_profiles
from .examples import EXAMPLE_PORTFOLIOS
from .explain import build_explanations
from .export import build_export_json, build_summary_text
from .extensions import limiter
from .glossary import relevant_glossary
from .lessons import FEE_EXAMPLE, LESSONS, SOURCES, recommend_lessons
from .normalize import merge_duplicate_tickers
from .validation import parse_risk_free_rate, validate_holdings, validate_targets

logger = logging.getLogger(__name__)
bp = Blueprint("main", __name__)

PROVIDER_DOWN_MESSAGE = (
    "Our free market-data source (Yahoo Finance) isn't responding right now, "
    "usually because it's limiting how many requests it accepts. This isn't a "
    "problem with your tickers. Please wait a minute and try again."
)


def _context(**overrides: Any) -> dict[str, Any]:
    """Every template variable with a safe default, so templates never crash."""
    ctx: dict[str, Any] = dict(
        result=None, explanations=None, errors=[], notes=[], failed=[],
        chart_data=None, glossary=[], checklist=[], summary_text=None, export_data=None,
        holdings=[], risk_free_pct=config.RISK_FREE_RATE * 100.0, rebalance=None,
        rebalance_errors=[], targets={}, examples=EXAMPLE_PORTFOLIOS, lesson_recs=[],
    )
    ctx.update(overrides)
    return ctx


@bp.route("/", methods=["GET"])
def index():
    return render_template("index.html", **_context())


@bp.route("/health")
def health():
    """Liveness check for the host (Render/Railway/Replit). Deliberately does
    NOT call Yahoo: the app is "up" even if the data provider is having a bad
    minute, and a health check shouldn't burn rate-limit budget."""
    return jsonify(status="ok"), 200


@bp.route("/learn")
def learn():
    """Beginner lessons, each linked to the report section it explains."""
    return render_template("learn.html", lessons=LESSONS, sources=SOURCES, fee_example=FEE_EXAMPLE)


@bp.route("/about")
@bp.route("/methodology")
def about():
    return render_template("about.html", config=config)


@bp.route("/analyze", methods=["POST"])
@limiter.limit("20 per minute")
def analyze():
    form = request.form
    raw_holdings = [
        {"ticker": t, "shares": s, "purchase_price": p, "purchase_date": d}
        for t, s, p, d in zip(form.getlist("ticker"), form.getlist("shares"),
                              form.getlist("purchase_price"), form.getlist("purchase_date"), strict=False)
    ]

    errors: list[str] = []
    import_notes: list[str] = []
    csv_file = request.files.get("csv_file")
    if csv_file and csv_file.filename:
        csv_holdings, csv_errors, csv_notes = parse_csv_with_notes(csv_file.stream)
        raw_holdings.extend(csv_holdings)
        errors.extend(csv_errors)
        import_notes.extend(csv_notes)
        if csv_holdings:
            logger.info("Parsed %d holding(s) from uploaded CSV", len(csv_holdings))

    rf, rf_error = parse_risk_free_rate(form.get("risk_free_rate"), config.RISK_FREE_RATE,
                                        config.RISK_FREE_RATE_MAX)
    if rf_error:
        errors.append(rf_error)

    clean_holdings, row_errors = validate_holdings(raw_holdings)
    errors.extend(msg for _, msg in row_errors)

    if not clean_holdings:
        if not errors:
            errors = ["Add at least one holding (ticker + shares)."]
        return render_template("index.html", **_context(errors=errors, holdings=raw_holdings,
                                                        risk_free_pct=rf * 100))

    merged_holdings, notes = merge_duplicate_tickers(clean_holdings)
    notes = import_notes + notes
    unique_tickers = sorted({h["ticker"].upper() for h in merged_holdings})
    logger.info("Analyzing %d holding(s): %s", len(merged_holdings), unique_tickers)

    try:
        current_prices, sectors, price_histories, failed = fetch_holdings_data(unique_tickers)
    except DataProviderError:
        logger.warning("Data provider unavailable for %s", unique_tickers)
        return render_template("index.html", **_context(errors=[PROVIDER_DOWN_MESSAGE],
                                                        holdings=merged_holdings,
                                                        risk_free_pct=rf * 100)), 503
    benchmark_series = fetch_benchmark()
    profiles = get_cached_profiles(unique_tickers)

    usable_holdings = [h for h in merged_holdings if h["ticker"].upper() in current_prices]
    if not usable_holdings:
        return render_template("index.html", **_context(
            errors=errors, failed=failed, holdings=merged_holdings, risk_free_pct=rf * 100))

    today = datetime.now(timezone.utc)
    usable_lots = [h for h in clean_holdings if h["ticker"].upper() in current_prices]
    result = compute_portfolio(usable_holdings, current_prices, sectors, price_histories,
                               today=today, benchmark_series=benchmark_series,
                               risk_free_rate=rf, profiles=profiles, lots=usable_lots)

    # optional "what if I rebalance?" comparison, submitted from the results page
    rebalance = None
    rebalance_errors: list[str] = []
    targets: dict[str, float] = {}
    if form.get("rebalance") == "1":
        parsed, rebalance_errors = validate_targets(form.getlist("target_ticker"),
                                                    form.getlist("target_pct"),
                                                    config.REBALANCE_SUM_TOLERANCE_PCT)
        unknown = [t for t in (parsed or {}) if t not in current_prices]
        if unknown:
            rebalance_errors.append(f"Target weights include tickers not in this portfolio: {', '.join(unknown)}.")
        elif parsed:
            targets = parsed
            rebalance = compute_rebalance(result, targets, current_prices, sectors, price_histories,
                                          today=today, benchmark_series=benchmark_series,
                                          risk_free_rate=rf, profiles=profiles)
        if not targets:
            targets = {t: _safe_float(p) for t, p in zip(form.getlist("target_ticker"),
                                                        form.getlist("target_pct"), strict=False)}

    explanations = build_explanations(result)
    checklist = build_checklist(result)

    return render_template(
        "index.html",
        **_context(
            result=result, explanations=explanations, errors=errors, notes=notes, failed=failed,
            chart_data=build_chart_data(result, price_histories),
            glossary=relevant_glossary(explanations),
            checklist=checklist,
            summary_text=build_summary_text(result),
            export_data=build_export_json(result, checklist),
            holdings=usable_lots, risk_free_pct=rf * 100,
            rebalance=rebalance, rebalance_errors=rebalance_errors, targets=targets,
            lesson_recs=recommend_lessons(result),
        ),
    )


def _safe_float(raw: str | None) -> float | None:
    try:
        return float(raw) if raw not in (None, "") else None
    except ValueError:
        return None
