"""
Tests for explain.py: given a result dict shaped like compute.py's output,
does it produce the right plain-English sections? These use hand-built
result dicts rather than going through compute_portfolio, so each test
isolates exactly one behavior of the template layer.
"""
from app.explain import build_explanations


def base_result(**overrides):
    result = {
        "total_value": 1000.0,
        "rows": [{"ticker": "AAA", "weight_pct": 100.0}],
        "effective_holdings": 1.0,
        "concentration": {"top_ticker": "AAA", "top_pct": 100.0, "flagged": True},
        "sector_pct": {"Technology": 100.0},
        "flagged_sectors": {},
        "volatility": {},
        "portfolio_vol": None,
        "portfolio_cagr": None,
        "portfolio_max_drawdown": None,
        "sharpe_ratio": None,
        "high_corr_pairs": [],
        "drawdown_scenarios": {},
        "behavioral_flags": [],
        "tax_flags": [],
        "risk_score": None,
        "risk_label": None,
        "benchmark": None,
        "correlation_matrix": None,
    }
    result.update(overrides)
    return result


def test_crash_context_appended_after_drawdown_line():
    result = base_result(drawdown_scenarios={
        "2022 bear market": {"estimated_portfolio_change_pct": -25.0, "coverage_pct": 100.0, "details": []},
    })
    out = build_explanations(result)
    joined = " ".join(out["drawdown"])
    assert "2022 bear market" in joined
    assert "Federal Reserve" in joined  # the historical context line


def test_reflect_prompt_for_very_high_risk():
    result = base_result(risk_score=90.0, risk_label="Very High")
    out = build_explanations(result)
    assert any("very high risk" in line for line in out["reflect"])


def test_no_reflect_prompt_for_low_risk():
    result = base_result(risk_score=10.0, risk_label="Low")
    out = build_explanations(result)
    assert not any("risk" in line.lower() and "high" in line.lower() for line in out["reflect"])


def test_reflect_prompt_for_severe_drawdown():
    result = base_result(drawdown_scenarios={
        "COVID crash (2020)": {"estimated_portfolio_change_pct": -35.0, "coverage_pct": 100.0, "details": []},
    })
    out = build_explanations(result)
    assert any("35%" in line for line in out["reflect"])


def test_reflect_prompt_for_behavioral_flags():
    result = base_result(behavioral_flags=[{"ticker": "AAA", "type": "recency_bias", "detail": 20.0}])
    out = build_explanations(result)
    assert any("buying patterns" in line for line in out["reflect"])


def test_reflect_capped_at_three():
    result = base_result(
        risk_score=90.0, risk_label="Very High",
        drawdown_scenarios={"2022 bear market": {"estimated_portfolio_change_pct": -40.0, "coverage_pct": 100.0, "details": []}},
        behavioral_flags=[{"ticker": "AAA", "type": "loss_aversion", "detail": -30.0}],
    )
    out = build_explanations(result)
    assert len(out["reflect"]) <= 3
