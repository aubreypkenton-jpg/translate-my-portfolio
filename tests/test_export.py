import json

from app.checklist import build_checklist
from app.export import build_export_json, build_summary_text


def sample_result():
    return {
        "total_value": 12345.67,
        "rows": [
            {"ticker": "AAA", "sector": "Technology", "value": 12345.67, "weight_pct": 100.0,
             "gain_loss_pct": 12.3, "max_drawdown_pct": -18.4},
        ],
        "effective_holdings": 1.0,
        "concentration": {"top_ticker": "AAA", "top_pct": 100.0, "flagged": True},
        "flagged_sectors": {"Technology": 100.0},
        "sector_pct": {"Technology": 100.0},
        "portfolio_vol": 25.0,
        "portfolio_cagr": 10.0,
        "portfolio_max_drawdown": -20.0,
        "sharpe_ratio": 0.8,
        "high_corr_pairs": [],
        "drawdown_scenarios": {
            "2022 bear market": {"estimated_portfolio_change_pct": -22.5, "coverage_pct": 100.0, "details": []},
        },
        "behavioral_flags": [],
        "tax_flags": [],
        "risk_score": 45.0,
        "risk_label": "Moderate",
        "benchmark": {"annualized_vol_pct": 15.0, "max_drawdown_pct": -25.0, "cagr_pct": 9.0},
        "correlation_matrix": None,
    }


def test_summary_text_includes_key_numbers():
    text = build_summary_text(sample_result())
    assert "$12,346" in text
    assert "45/100" in text
    assert "AAA" in text
    assert "22%" in text or "23%" in text  # rounding of 22.5


def test_summary_text_handles_missing_risk_score():
    result = sample_result()
    result["risk_score"] = None
    text = build_summary_text(result)
    assert "risk" not in text.split("--")[1] if "--" in text else True  # doesn't crash either way
    assert "$12,346" in text


def test_export_json_is_actually_json_serializable():
    result = sample_result()
    checklist = build_checklist(result)
    export = build_export_json(result, checklist)
    serialized = json.dumps(export)  # raises if anything isn't serializable
    assert "AAA" in serialized
    assert export["risk_score"] == 45.0
    assert export["checklist"] == checklist
    assert "disclaimer" in export


def test_export_json_rounds_holdings():
    result = sample_result()
    export = build_export_json(result, [])
    assert export["holdings"][0]["value"] == 12345.67
    assert export["holdings"][0]["gain_loss_pct"] == 12.3
