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


def test_r2_explicit_broadcast_object_keys(monkeypatch, tmp_path):
    for name, value in {
        "R2_ACCOUNT_ID": "account",
        "R2_ACCESS_KEY_ID": "access",
        "R2_SECRET_ACCESS_KEY": "secret",
        "R2_BUCKET": "bucket",
    }.items():
        monkeypatch.setenv(name, value)

    uploaded = {}

    class Body:
        def read(self):
            return b"segment"

    class Client:
        def upload_file(self, path, bucket, key):
            uploaded.update(path=path, bucket=bucket, key=key)

        def get_object(self, **kwargs):
            uploaded["get"] = kwargs
            return {"Body": Body()}

    monkeypatch.setattr(r2, "_client", lambda: Client())
    source = tmp_path / "seg-000.ts"
    source.write_bytes(b"mpeg-ts")
    assert r2.put_object_file(source, "/broadcast/ep-1/seg-000.ts") is True
    assert uploaded["bucket"] == "bucket"
    assert uploaded["key"] == "broadcast/ep-1/seg-000.ts"
    assert r2.get_object_bytes("broadcast/ep-1/seg-000.ts") == b"segment"
