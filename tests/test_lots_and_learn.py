"""Per-purchase (lot) tax handling, brokerage CSV import, and the Learn section."""
import io
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

import app.routes as routes_module
from app import create_app
from app.compute import compute_portfolio, compute_rebalance
from app.csv_import import normalize_date, parse_csv, parse_csv_with_notes
from app.explain import build_explanations
from app.lessons import FEE_EXAMPLE, LESSON_IDS, LESSONS, recommend_lessons
from app.normalize import merge_duplicate_tickers
from app.validation import MAX_HOLDINGS, validate_holdings

TODAY = datetime(2024, 6, 1)


def lot(t, shares, price, d):
    return {"ticker": t, "shares": str(shares), "purchase_price": str(price) if price else None, "purchase_date": d}


def monthly_voo():
    # 14 monthly buys from 2023-04 to 2024-05: some long-term, some short-term on 2024-06-01
    return [lot("VOO", 1, 350 + 5 * i, f"{2023 + (3 + i) // 12}-{(3 + i) % 12 + 1:02d}-15") for i in range(14)]


def analyze(lots, prices, today=TODAY, **kw):
    merged, _ = merge_duplicate_tickers(lots)
    return compute_portfolio(merged, prices, {}, {}, today=today, lots=lots, **kw)


# ---------------- per-lot taxes ----------------

def test_each_purchase_gets_its_own_tax_row():
    r = analyze(monthly_voo(), {"VOO": 450.0})
    assert len(r["tax_flags"]) == 14
    terms = [f["term"] for f in r["tax_flags"]]
    assert terms.count("long-term") == 2 and terms.count("short-term") == 12  # Apr & May 2023 lots are > 1 year


def test_old_merge_bug_fixed_long_term_lots_not_hidden_by_recent_buy():
    lots = [lot("VOO", 10, 300, "2020-01-15"), lot("VOO", 1, 440, "2024-05-15")]
    r = analyze(lots, {"VOO": 450.0})
    by_date = {f["purchase_date"]: f for f in r["tax_flags"]}
    assert by_date["2020-01-15"]["term"] == "long-term"
    assert by_date["2024-05-15"]["term"] == "short-term"
    assert r["tax_summary"]["long_term_gain"] == pytest.approx(1500)
    assert r["tax_summary"]["short_term_gain"] == pytest.approx(10)


def test_multi_lot_summary_sentence():
    r = analyze(monthly_voo(), {"VOO": 450.0})
    text = " ".join(build_explanations(r)["tax"])
    assert "VOO: 14 separate purchases" in text
    assert "2 long-term" in text and "12 short-term" in text
    assert "turns long-term in" in text and "FIFO" in text


def test_missing_dates_are_called_out():
    lots = [lot("VOO", 1, 300, "2020-01-15"), lot("AAPL", 2, None, None)]
    r = analyze(lots, {"VOO": 450.0, "AAPL": 190.0})
    assert r["tax_missing_dates"] == ["AAPL"]
    assert any("No purchase dates for AAPL" in line for line in build_explanations(r)["tax"])


def test_without_lots_argument_behaves_like_before():
    r = compute_portfolio([lot("A", 1, 100, "2020-01-02")], {"A": 120.0}, {}, {}, today=TODAY)
    assert r["tax_flags"][0]["term"] == "long-term" and r["tax_flags"][0]["unrealized_gain"] == pytest.approx(20)


def test_recency_bias_checked_per_purchase():
    dates = pd.date_range("2023-01-02", "2024-05-31", freq="B").strftime("%Y-%m-%d")
    s = pd.Series(100.0, index=dates)
    i = dates.get_loc("2024-03-01")
    s.iloc[i - 35:i + 1] = np.linspace(100, 130, 36)
    s.iloc[i + 1:] = 130.0
    lots = [lot("A", 5, 100, "2023-06-01"), lot("A", 1, 130, "2024-03-01")]  # only the 2nd buy chased a run-up
    merged, _ = merge_duplicate_tickers(lots)
    r = compute_portfolio(merged, {"A": 130.0}, {}, {"A": s}, today=TODAY, lots=lots)
    assert [f["type"] for f in r["behavioral_flags"]].count("recency_bias") == 1


def test_rebalance_warning_uses_lots():
    lots = [lot("A", 10, 50, "2020-01-02"), lot("A", 1, 50, "2024-05-01"), lot("B", 1, 100, "2020-01-02")]
    prices = {"A": 100.0, "B": 100.0}
    merged, _ = merge_duplicate_tickers(lots)
    r = compute_portfolio(merged, prices, {}, {}, today=TODAY, lots=lots)
    rb = compute_rebalance(r, {"A": 50.0, "B": 50.0}, prices, {}, {}, today=TODAY)
    sell = next(t for t in rb["trades"] if t["ticker"] == "A")
    assert sell["action"] == "sell" and sell["short_term_gain_warning"] is True


def test_merge_note_mentions_separate_tax_treatment():
    _, notes = merge_duplicate_tickers(monthly_voo())
    assert "each purchase separately" in notes[0]


def test_many_lots_of_few_tickers_are_allowed():
    rows = [{"ticker": t, "shares": "1", "purchase_price": "", "purchase_date": ""}
            for t in ("VOO", "VXUS") for _ in range(150)]
    clean, errors = validate_holdings(rows)
    assert len(clean) == 300 and errors == []


def test_distinct_ticker_cap_still_applies():
    rows = [{"ticker": f"T{i}", "shares": "1"} for i in range(MAX_HOLDINGS + 3)]
    clean, errors = validate_holdings(rows)
    assert len({r["ticker"] for r in clean}) == MAX_HOLDINGS and errors


# ---------------- CSV import ----------------

def stream(text):
    return io.BytesIO(text.encode("utf-8"))


def test_brokerage_positions_export_columns():
    text = 'Symbol,Description,Quantity,Average Cost,Acquired\nVOO,Vanguard S&P 500,"1,000",$350.25,3/15/2022\n'
    h, e = parse_csv(stream(text))
    assert e == [] and h[0] == {"ticker": "VOO", "shares": "1,000", "purchase_price": "$350.25",
                                "purchase_date": "2022-03-15"}
    clean, errs = validate_holdings(h)
    assert errs == [] and float(clean[0]["shares"]) == 1000 and float(clean[0]["purchase_price"]) == 350.25


def test_total_cost_basis_converted_to_per_share():
    text = "Symbol,Quantity,Cost Basis Total\nAAPL,4,$600.00\n"
    h, e = parse_csv(stream(text))
    assert float(h[0]["purchase_price"]) == pytest.approx(150.0)


def test_price_dollar_header_and_parenthesized_symbol():
    text = "Security,Shares,Price ($)\nApple Inc (AAPL),2,190\n"
    h, e = parse_csv(stream(text))
    assert h[0]["ticker"] == "AAPL" and h[0]["purchase_price"] == "190"


def test_a_type_column_does_not_trigger_transaction_mode():
    text = "Symbol,Quantity,Type\nVOO,3,ETF\n"
    h, e = parse_csv(stream(text))
    assert e == [] and h[0]["ticker"] == "VOO"


@pytest.mark.parametrize("raw,iso", [("2024-03-15", "2024-03-15"), ("3/15/2024", "2024-03-15"),
                                     ("03/15/24", "2024-03-15"), ("2024/03/15", "2024-03-15"),
                                     ("2024-03-15T10:00:00", "2024-03-15"), ("", ""), ("soon", "soon")])
def test_normalize_date(raw, iso):
    assert normalize_date(raw) == iso


ACTIVITY = (
    '"Activity Date","Process Date","Settle Date","Instrument","Description","Trans Code","Quantity","Price","Amount"\n'
    '"5/15/2024","5/15/2024","5/16/2024","VOO","Vanguard S&P 500 ETF","Buy","1","$480.00","($480.00)"\n'
    '"4/30/2024","4/30/2024","4/30/2024","VOO","Dividend","CDIV","","","$5.10"\n'
    '"3/1/2024","3/1/2024","3/4/2024","VOO","Vanguard S&P 500 ETF","Sell","1.5","$470.00","$705.00"\n'
    '"2/15/2024","2/15/2024","2/16/2024","VOO","Vanguard S&P 500 ETF","Buy","1","$450.00","($450.00)"\n'
    '"1/15/2023","1/15/2023","1/17/2023","VOO","Vanguard S&P 500 ETF","Buy","2","$360.00","($720.00)"\n'
    '"1/10/2023","1/10/2023","1/10/2023","","ACH Deposit","ACH","","","$1,000.00"\n'
)


def test_transaction_history_becomes_fifo_lots():
    h, e, notes = parse_csv_with_notes(stream(ACTIVITY))
    assert e == []
    # FIFO: the 1.5 shares sold come out of the oldest (2023-01-15) lot first
    assert h == [
        {"ticker": "VOO", "shares": "0.5", "purchase_price": "360.0000", "purchase_date": "2023-01-15"},
        {"ticker": "VOO", "shares": "1", "purchase_price": "450.0000", "purchase_date": "2024-02-15"},
        {"ticker": "VOO", "shares": "1", "purchase_price": "480.0000", "purchase_date": "2024-05-15"},
    ]
    assert "3 buy(s) and 1 sell(s)" in notes[0] and "FIFO" in notes[0]


def test_selling_more_than_bought_is_flagged():
    text = '"Activity Date","Instrument","Trans Code","Quantity","Price"\n"1/2/2024","AAPL","Buy","1","$100"\n"2/2/2024","AAPL","Sell","3","$120"\n"2/3/2024","MSFT","Buy","1","$400"\n'
    h, e, notes = parse_csv_with_notes(stream(text))
    assert [x["ticker"] for x in h] == ["MSFT"]
    assert any("Sold more AAPL" in n for n in notes)


def test_split_rows_produce_a_warning():
    text = '"Activity Date","Instrument","Description","Trans Code","Quantity","Price"\n"1/2/2024","NVDA","NVDA","Buy","1","$500"\n"6/10/2024","NVDA","Stock Split 10:1","SPL","9",""\n'
    h, e, notes = parse_csv_with_notes(stream(text))
    assert any("splits" in n for n in notes)


def test_history_with_nothing_left_is_an_error():
    text = '"Activity Date","Instrument","Trans Code","Quantity","Price"\n"1/2/2024","AAPL","Buy","1","$100"\n"2/2/2024","AAPL","Sell","1","$120"\n'
    h, e, notes = parse_csv_with_notes(stream(text))
    assert h == [] and "didn't leave any shares" in e[0]


def test_company_named_splunk_is_not_a_split():
    text = '"Activity Date","Instrument","Description","Trans Code","Quantity","Price"\n"1/2/2024","SPLK","Splunk Inc","Buy","1","$100"\n'
    _, _, notes = parse_csv_with_notes(stream(text))
    assert not any("splits" in n for n in notes)


# ---------------- lessons ----------------

def test_lessons_well_formed():
    assert len(LESSONS) >= 8 and len(LESSON_IDS) == len(LESSONS)
    for lesson in LESSONS:
        assert lesson["title"] and lesson["why"] and lesson["body"] and lesson["sources"]


def test_fee_example_math():
    lo, mid, hi = FEE_EXAMPLE
    assert lo["ending"] == pytest.approx(10_000 * (1.07 - 0.0003) ** 30)
    assert lo["ending"] > mid["ending"] > hi["ending"]


def test_recommendations_quote_the_report():
    r = compute_portfolio([lot("NVDA", 9, None, None), lot("AAPL", 1, None, None)],
                          {"NVDA": 100.0, "AAPL": 100.0}, {"NVDA": "Technology", "AAPL": "Technology"}, {},
                          profiles={"NVDA": {"asset_class": "Individual stock"}, "AAPL": {"asset_class": "Individual stock"}})
    recs = recommend_lessons(r)
    assert recs[0]["id"] == "diversification" and "NVDA is 90%" in recs[0]["reason"]
    assert len(recs) <= 3 and all(x["id"] in LESSON_IDS for x in recs)


def test_no_recommendations_for_empty_signal():
    r = compute_portfolio([lot("VOO", 1, None, None)], {"VOO": 1.0}, {"VOO": "Diversified fund (ETF)"}, {},
                          profiles={"VOO": {"asset_class": "ETF"}})
    assert recommend_lessons(r) == []


# ---------------- web layer ----------------

def hist(seed, n=700):
    dates = pd.bdate_range("2022-01-03", periods=n).strftime("%Y-%m-%d")
    rng = np.random.default_rng(seed)
    return pd.Series(100 * (1 + rng.normal(0.0004, 0.012, n)).cumprod(), index=dates)


H = {"VOO": hist(1), "SPY": hist(2), "AAPL": hist(3)}


@pytest.fixture
def client(monkeypatch):
    app = create_app(rate_limit_enabled=False)
    app.testing = True
    monkeypatch.setattr(routes_module, "fetch_holdings_data", lambda ts: (
        {t: float(H[t].iloc[-1]) for t in ts if t in H}, {t: "Technology" for t in ts},
        {t: H[t] for t in ts if t in H}, [t for t in ts if t not in H]))
    monkeypatch.setattr(routes_module, "fetch_benchmark", lambda: H["SPY"])
    monkeypatch.setattr(routes_module, "get_cached_profiles", lambda ts: {})
    return app.test_client()


def test_learn_page_lists_every_lesson_with_sources(client):
    body = client.get("/learn").get_data(as_text=True)
    for lesson in LESSONS:
        assert f'id="{lesson["id"]}"' in body
    assert "investor.gov" in body and "finra.org" in body and "Education, not advice" in body
    assert "?example=tech" in body


def test_nav_has_learn_link(client):
    assert 'href="/learn"' in client.get("/").get_data(as_text=True)


def test_report_links_to_lessons_and_recommends(client):
    r = client.post("/analyze", data={"ticker": ["AAPL"], "shares": ["10"], "purchase_price": [""],
                                      "purchase_date": [""]})
    body = r.get_data(as_text=True)
    assert "Recommended lessons for this portfolio" in body
    assert "/learn#diversification" in body


def test_lots_stay_separate_in_the_form_and_tax_table(client):
    r = client.post("/analyze", data={"ticker": ["VOO", "VOO"], "shares": ["2", "1"],
                                      "purchase_price": ["300", "400"], "purchase_date": ["2022-02-01", "2024-01-02"]})
    body = r.get_data(as_text=True)
    assert body.count('name="ticker" placeholder="AAPL" aria-label="Ticker symbol" value="VOO"') == 2
    assert "2022-02-01" in body and "2024-01-02" in body
    assert 'id="show-details" checked' in body


def test_details_hidden_by_default_on_blank_form(client):
    body = client.get("/").get_data(as_text=True)
    assert "hide-details" in body and 'id="show-details" checked' not in body


def test_transaction_history_upload_through_the_app(client):
    r = client.post("/analyze", data={"ticker": [""], "shares": [""], "purchase_price": [""], "purchase_date": [""],
                                      "csv_file": (io.BytesIO(ACTIVITY.encode()), "activity.csv")},
                    content_type="multipart/form-data")
    body = r.get_data(as_text=True)
    assert "Read a transaction history" in body and "Overview" in body
    assert "One row per purchase" in body
