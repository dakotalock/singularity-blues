from fastapi.testclient import TestClient

from web.app import app


def test_episode_without_key_is_503(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr("web.app.has_gemini_key", lambda: False)
    client = TestClient(app)
    r = client.post("/episode", json={})
    assert r.status_code == 503
