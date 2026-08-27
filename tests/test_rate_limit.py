"""
Exercises the REAL rate limiter (enforcement on), isolated from the rest of
the suite which disables it (see test_routes.py) so ~10 other tests hitting
/analyze don't trip each other's limit. This is the one place that actually
proves the "20 per minute" cap on /analyze does something.
"""
import pandas as pd
import numpy as np
import pytest

from app import create_app
from app.extensions import limiter
import app.routes as routes_module


def make_history(start=100, seed=1, n=300):
    dates = pd.date_range("2023-01-02", periods=n, freq="B").strftime("%Y-%m-%d")
    rng = np.random.default_rng(seed)
    return pd.Series(start * (1 + rng.normal(0.0005, 0.015, n)).cumprod(), index=dates)


@pytest.fixture
def limited_client(monkeypatch):
    app = create_app(rate_limit_enabled=True)
    app.testing = True

    fake_hist = {"AAPL": make_history()}
    fake_prices = {"AAPL": fake_hist["AAPL"].iloc[-1]}
    monkeypatch.setattr(routes_module, "fetch_holdings_data",
                         lambda tickers: (fake_prices, {"AAPL": "Technology"}, fake_hist, []))
    monkeypatch.setattr(routes_module, "fetch_benchmark", lambda: make_history(400, 3))

    # storage is a module-level singleton on the shared `limiter` object, so
    # explicitly reset it before this test rather than trusting it starts empty
    with app.app_context():
        limiter.storage.reset()

    return app.test_client()


def _post_holding(client):
    return client.post("/analyze", data={
        "ticker": ["AAPL"], "shares": ["1"], "purchase_price": [""], "purchase_date": [""],
    })


def test_requests_within_limit_succeed(limited_client):
    for _ in range(5):
        r = _post_holding(limited_client)
        assert r.status_code == 200


def test_exceeding_rate_limit_returns_429(limited_client):
    # the limit is 20/minute; firing 30 in a burst must trip it somewhere
    statuses = [_post_holding(limited_client).status_code for _ in range(30)]
    assert 429 in statuses
    # and everything before the first 429 should have been a normal 200
    first_429 = statuses.index(429)
    assert all(s == 200 for s in statuses[:first_429])


def test_index_and_about_are_not_rate_limited(limited_client):
    # the limit is scoped to /analyze specifically -- browsing shouldn't be capped
    for _ in range(25):
        assert limited_client.get("/").status_code == 200
        assert limited_client.get("/about").status_code == 200
