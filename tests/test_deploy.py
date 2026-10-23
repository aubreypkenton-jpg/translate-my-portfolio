"""Deployment plumbing: health check, friendly error pages, provider outage
message, cache behavior, and the config files hosts depend on."""
from pathlib import Path

import pytest

import app.routes as routes_module
from app import create_app
from app.cache import TTLCache
from app.data_fetch import DataProviderError

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def client():
    app = create_app(rate_limit_enabled=False)
    app.testing = True
    return app.test_client()


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.get_json() == {"status": "ok"}


def test_health_never_touches_yahoo(client, monkeypatch):
    monkeypatch.setattr(routes_module, "fetch_holdings_data",
                        lambda *a: (_ for _ in ()).throw(AssertionError("no network")))
    assert client.get("/health").status_code == 200


def test_404_is_friendly(client):
    r = client.get("/does-not-exist")
    assert r.status_code == 404
    assert b"Back to the analyzer" in r.data


def test_provider_outage_shows_friendly_503(client, monkeypatch):
    def down(tickers):
        raise DataProviderError("rate limited")

    monkeypatch.setattr(routes_module, "fetch_holdings_data", down)
    r = client.post("/analyze", data={"ticker": ["AAPL"], "shares": ["10"],
                                      "purchase_price": [""], "purchase_date": [""]})
    assert r.status_code == 503
    body = r.get_data(as_text=True)
    assert "isn&#39;t a problem with your tickers" in body or "isn't a problem with your tickers" in body


def test_ttl_cache_expires(monkeypatch):
    import app.cache as cache_mod
    now = [1000.0]
    monkeypatch.setattr(cache_mod.time, "time", lambda: now[0])
    c = TTLCache(ttl_seconds=10)
    c.set("a", 1)
    assert c.get("a") == 1
    now[0] += 11
    assert c.get("a") is None
    assert len(c) == 0


def test_ttl_cache_evicts_when_full():
    c = TTLCache(ttl_seconds=60, max_entries=2)
    c.set("a", 1)
    c.set("b", 2)
    c.set("c", 3)
    assert len(c) == 2 and c.get("c") == 3


def test_gunicorn_config_reads_port(monkeypatch):
    monkeypatch.setenv("PORT", "10000")
    ns: dict = {}
    exec((ROOT / "gunicorn.conf.py").read_text(), ns)
    assert ns["bind"] == "0.0.0.0:10000"
    assert ns["timeout"] >= 60


def test_deploy_files_present():
    for name in ("Dockerfile", "render.yaml", "railway.json", ".replit", "gunicorn.conf.py"):
        assert (ROOT / name).exists(), name
    assert "gunicorn" in (ROOT / "requirements.txt").read_text()
    assert "/health" in (ROOT / "render.yaml").read_text()


def test_legacy_v1_files_removed():
    # one source of truth: the app/ package (see DECISIONS.md)
    for name in ("app.py", "compute.py", "data_fetch.py", "explain.py"):
        assert not (ROOT / name).exists(), name
