import time

from fastapi.testclient import TestClient

from orchestrator.credits import grant_bundle, reset_sqlite_for_tests, sign_buyer
from orchestrator.gemini import PromptRefused
from orchestrator.writer_cascade import DEFAULT_VETO_NOTE
from web.app import app


def _wait_job(client, job_id):
    snap = {}
    for _ in range(80):
        snap = client.get("/episode/status", params={"job_id": job_id}).json()
        if snap.get("status") in ("ready", "error", "rejected", "refused"):
            return snap
        time.sleep(0.05)
    return snap


def test_writer_veto_refunds_and_says_topic_moderated_by_ai(monkeypatch, tmp_path):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("CREDITS_SQLITE_PATH", str(tmp_path / "credits.db"))
    reset_sqlite_for_tests()
    grant_bundle("buyerVeto", "5")

    def run(mem, topic=None, once=False, progress=None, **kwargs):
        raise PromptRefused("No.")

    monkeypatch.setattr("web.app.has_gemini_key", lambda: True)
    monkeypatch.setattr("web.app.run_episode", run)
    client = TestClient(app)
    client.cookies.set("sb_buyer", sign_buyer("buyerVeto"))
    r = client.post(
        "/episode",
        json={"topic": "What if the thermostat joins the union", "username": "Alex"},
    )
    assert r.status_code == 200
    snap = _wait_job(client, r.json()["job_id"])
    assert snap["status"] == "refused"
    assert snap.get("refunded") is True
    assert snap.get("note") == "No."
    blob = f"{snap.get('error') or ''} {snap.get('note') or ''}".lower()
    assert "moderated by the ai" in blob
    assert "gemini" not in blob and "piper" not in blob
    acc = client.get("/account").json()
    assert acc["credits"] == 5


def test_writer_veto_empty_note_uses_default_and_refunds(monkeypatch, tmp_path):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("CREDITS_SQLITE_PATH", str(tmp_path / "credits.db"))
    reset_sqlite_for_tests()
    grant_bundle("buyerEmpty", "5")

    def run(mem, topic=None, once=False, progress=None, **kwargs):
        raise PromptRefused("")

    monkeypatch.setattr("web.app.has_gemini_key", lambda: True)
    monkeypatch.setattr("web.app.run_episode", run)
    client = TestClient(app)
    client.cookies.set("sb_buyer", sign_buyer("buyerEmpty"))
    r = client.post(
        "/episode",
        json={"topic": "What if the thermostat joins the union", "username": "Alex"},
    )
    snap = _wait_job(client, r.json()["job_id"])
    assert snap["status"] == "refused"
    assert snap.get("refunded") is True
    assert snap.get("note") == DEFAULT_VETO_NOTE
    assert "moderated by the AI" in (snap.get("error") or "")
    acc = client.get("/account").json()
    assert acc["credits"] == 5
