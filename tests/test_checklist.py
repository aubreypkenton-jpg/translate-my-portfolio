from app.checklist import build_checklist


def base_result(**overrides):
    result = {
        "concentration": {"top_ticker": "AAA", "top_pct": 20.0, "flagged": False},
        "flagged_sectors": {},
        "high_corr_pairs": [],
        "sharpe_ratio": 1.2,
        "behavioral_flags": [],
        "risk_score": 30.0,
        "risk_label": "Moderate",
    }
    result.update(overrides)
    return result


def test_all_pass_when_nothing_flagged():
    checklist = build_checklist(base_result())
    assert all(item["status"] == "pass" for item in checklist)


def test_concentration_warn_when_flagged():
    checklist = build_checklist(base_result(concentration={"top_ticker": "AAA", "top_pct": 80.0, "flagged": True}))
    item = next(i for i in checklist if "single holding" in i["label"])
    assert item["status"] == "warn"
    assert "AAA" in item["detail"]


def test_sector_warn_when_flagged():
    checklist = build_checklist(base_result(flagged_sectors={"Technology": 90.0}))
    item = next(i for i in checklist if "sector" in i["label"])
    assert item["status"] == "warn"


def test_correlation_warn_when_pairs_present():
    checklist = build_checklist(base_result(high_corr_pairs=[("A", "B", 0.85)]))
    item = next(i for i in checklist if "correlated" in i["label"])
    assert item["status"] == "warn"
    assert "A/B" in item["detail"]


def test_sharpe_na_when_missing():
    checklist = build_checklist(base_result(sharpe_ratio=None))
    item = next(i for i in checklist if "Sharpe" in i["label"])
    assert item["status"] == "na"


def test_sharpe_warn_when_negative():
    checklist = build_checklist(base_result(sharpe_ratio=-0.5))
    item = next(i for i in checklist if "Sharpe" in i["label"])
    assert item["status"] == "warn"


def test_behavioral_warn_when_flags_present():
    checklist = build_checklist(base_result(behavioral_flags=[{"ticker": "AAA", "type": "recency_bias", "detail": 20}]))
    item = next(i for i in checklist if "buying-pattern" in i["label"])
    assert item["status"] == "warn"
    assert "1 flagged" in item["detail"]


def test_risk_score_warn_when_high():
    checklist = build_checklist(base_result(risk_score=80.0, risk_label="Very High"))
    item = next(i for i in checklist if "risk score" in i["label"])
    assert item["status"] == "warn"


def test_risk_score_absent_when_no_score():
    checklist = build_checklist(base_result(risk_score=None))
    assert not any("risk score" in i["label"] for i in checklist)
