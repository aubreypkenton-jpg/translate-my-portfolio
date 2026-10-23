import json
import logging
from datetime import datetime

from flask import Blueprint, jsonify, render_template, request

from .chart_data import build_chart_data
from .checklist import build_checklist
from .compute import compute_portfolio
from .csv_import import parse_csv
from .data_fetch import DataProviderError, fetch_benchmark, fetch_holdings_data
from .explain import build_explanations
from .export import build_export_json, build_summary_text
from .extensions import limiter
from .glossary import relevant_glossary
from .normalize import merge_duplicate_tickers
from .validation import validate_holdings

logger = logging.getLogger(__name__)
bp = Blueprint("main", __name__)

DEFAULT_CONTEXT = dict(result=None, explanations=None, errors=[], notes=[], failed=[],
                        chart_json=None, glossary=[], checklist=[], summary_text=None,
                        export_json=None)


PROVIDER_DOWN_MESSAGE = (
    "Our free market-data source (Yahoo Finance) isn't responding right now, "
    "usually because it's limiting how many requests it accepts. This isn't a "
    "problem with your tickers. Please wait a minute and try again."
)


@bp.route("/", methods=["GET"])
def index():
    return render_template("index.html", **DEFAULT_CONTEXT)


@bp.route("/health")
def health():
    """Liveness check for the host (Render/Railway/Replit). Deliberately does
    NOT call Yahoo: the app is "up" even if the data provider is having a bad
    minute, and a health check shouldn't burn rate-limit budget."""
    return jsonify(status="ok"), 200


@bp.route("/about")
def about():
    return render_template("about.html")


@bp.route("/analyze", methods=["POST"])
@limiter.limit("20 per minute")
def analyze():
    tickers = request.form.getlist("ticker")
    shares = request.form.getlist("shares")
    purchase_prices = request.form.getlist("purchase_price")
    purchase_dates = request.form.getlist("purchase_date")

    raw_holdings = [
        {"ticker": t, "shares": s, "purchase_price": p, "purchase_date": d}
        for t, s, p, d in zip(tickers, shares, purchase_prices, purchase_dates)
    ]

    errors = []
    csv_file = request.files.get("csv_file")
    if csv_file and csv_file.filename:
        csv_holdings, csv_errors = parse_csv(csv_file.stream)
        raw_holdings.extend(csv_holdings)
        errors.extend(csv_errors)
        if csv_holdings:
            logger.info("Parsed %d holding(s) from uploaded CSV '%s'", len(csv_holdings), csv_file.filename)

    clean_holdings, row_errors = validate_holdings(raw_holdings)
    errors.extend(msg for _, msg in row_errors)

    if not clean_holdings:
        if not errors:
            errors = ["Add at least one holding (ticker + shares)."]
        return render_template("index.html", **{**DEFAULT_CONTEXT, "errors": errors})

    merged_holdings, notes = merge_duplicate_tickers(clean_holdings)

    unique_tickers = sorted({h["ticker"].upper() for h in merged_holdings})
    logger.info("Analyzing %d holding(s): %s", len(merged_holdings), unique_tickers)

    try:
        current_prices, sectors, price_histories, failed = fetch_holdings_data(unique_tickers)
    except DataProviderError:
        logger.warning("Data provider unavailable for %s", unique_tickers)
        return render_template("index.html", **{**DEFAULT_CONTEXT, "errors": [PROVIDER_DOWN_MESSAGE]}), 503
    benchmark_series = fetch_benchmark()

    usable_holdings = [h for h in merged_holdings if h["ticker"].upper() in current_prices]

    if not usable_holdings:
        errors.append("Couldn't fetch data for any of those tickers. Double-check the symbols.")
        return render_template("index.html", **{**DEFAULT_CONTEXT, "errors": errors, "failed": failed})

    result = compute_portfolio(usable_holdings, current_prices, sectors, price_histories,
                                today=datetime.utcnow(), benchmark_series=benchmark_series)
    explanations = build_explanations(result)
    chart_data = build_chart_data(result, price_histories)
    glossary = relevant_glossary(explanations)
    checklist = build_checklist(result)
    summary_text = build_summary_text(result)
    export_json = build_export_json(result, checklist)

    return render_template(
        "index.html",
        result=result, explanations=explanations,
        errors=errors, notes=notes, failed=failed,
        chart_json=json.dumps(chart_data),
        glossary=glossary,
        checklist=checklist,
        summary_text=summary_text,
        export_json=json.dumps(export_json),
    )
