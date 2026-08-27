from pathlib import Path

from orchestrator import r2


def test_r2_configured_false_when_env_empty(monkeypatch, tmp_path):
    monkeypatch.delenv("R2_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("R2_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("R2_SECRET_ACCESS_KEY", raising=False)
    monkeypatch.delenv("R2_BUCKET", raising=False)
    monkeypatch.delenv("R2_ENDPOINT", raising=False)
    assert r2.configured() is False
    missing = tmp_path / "nope.wav"
    assert r2.put_file(missing) is False
    assert r2.get_bytes("ep0001_00_reed.wav") is None
