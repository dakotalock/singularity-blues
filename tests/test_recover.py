from fastapi.testclient import TestClient

from orchestrator.credits import (
    grant_bundle,
    reset_sqlite_for_tests,
    sign_buyer,
    spend_credit,
)
from web.app import app


def _iso(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("CREDITS_SQLITE_PATH", str(tmp_path / "credits.db"))
    reset_sqlite_for_tests()


def test_account_returns_recovery_key(monkeypatch, tmp_path):
    _iso(monkeypatch, tmp_path)
    client = TestClient(app)
    r = client.get("/account")
    assert r.status_code == 200
    data = r.json()
    assert data["recovery_key"].startswith("sbk_")
    assert "credits" in data
    assert "ltm_pins" in data


def test_recover_restores_cookie_and_remaining_credits(monkeypatch, tmp_path):
    _iso(monkeypatch, tmp_path)
    grant_bundle("orig-buyer", "5")
    assert spend_credit("orig-buyer", 2) is True
    orig = TestClient(app)
    orig.cookies.set("sb_buyer", sign_buyer("orig-buyer"))
    acc = orig.get("/account").json()
    key = acc["recovery_key"]
    assert acc["credits"] == 3
    assert key.startswith("sbk_")

    fresh = TestClient(app)
    r = fresh.post("/recover", json={"key": key})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["credits"] == 3
    assert data["ltm_pins"] == 1
    assert data["recovery_key"] == key
    assert fresh.cookies.get("sb_buyer")
    acc2 = fresh.get("/account").json()
    assert acc2["credits"] == 3
    assert acc2["recovery_key"] == key


def test_unknown_recovery_key_is_403(monkeypatch, tmp_path):
    _iso(monkeypatch, tmp_path)
    client = TestClient(app)
    r = client.post("/recover", json={"key": "sbk_not-a-real-recovery"})
    assert r.status_code == 403
    assert client.cookies.get("sb_owner") in (None, "")


def test_owner_secret_as_recover_key_is_403(monkeypatch, tmp_path):
    _iso(monkeypatch, tmp_path)
    monkeypatch.setenv("OWNER_PROMPT_SECRET", "house-test-key")
    client = TestClient(app)
    r = client.post("/recover", json={"key": "house-test-key"})
    assert r.status_code == 403
    assert client.cookies.get("sb_owner") in (None, "")
    acc = client.get("/account").json()
    assert acc["owner"] is False
