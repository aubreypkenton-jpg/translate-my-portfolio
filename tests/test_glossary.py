from app.glossary import GLOSSARY, relevant_glossary


def test_empty_explanations_yield_empty_glossary():
    explanations = {k: [] for k in ["concentration", "volatility", "correlation", "behavioral", "tax", "risk_score"]}
    assert relevant_glossary(explanations) == []


def test_only_relevant_sections_contribute_terms():
    explanations = {
        "concentration": ["some line"],
        "volatility": [],
        "correlation": [],
        "behavioral": [],
        "tax": [],
        "risk_score": [],
    }
    terms = [k for k, _ in relevant_glossary(explanations)]
    assert "concentration" in terms
    assert "diversification" in terms  # concentration section maps to both
    assert "volatility" not in terms
    assert "sharpe_ratio" not in terms


def test_no_duplicate_terms_across_sections():
    explanations = {
        "concentration": ["line"],
        "volatility": ["line"],
        "correlation": [],
        "behavioral": [],
        "tax": [],
        "risk_score": ["line"],
    }
    terms = [k for k, _ in relevant_glossary(explanations)]
    assert len(terms) == len(set(terms))


def test_every_glossary_entry_is_well_formed():
    for _key, definition in GLOSSARY.items():
        assert ":" in definition
        assert len(definition) > 20
