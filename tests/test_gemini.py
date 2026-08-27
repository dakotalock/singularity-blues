from types import SimpleNamespace
from orchestrator.gemini import GeminiClient, GeminiWriter, GEMINI_MODELS, model_cascade


def _client_with_generate(fn):
    client = object.__new__(GeminiClient)
    client._types = SimpleNamespace(GenerateContentConfig=lambda **kw: kw)
    client.client = SimpleNamespace(models=SimpleNamespace(generate_content=fn))
    client.lite_model = ""
    client.writer_model = ""
    return client


def test_model_cascade_default_ignores_legacy_env(monkeypatch):
    monkeypatch.setenv("GEMINI_WRITER_MODEL", "gemini-2.5-flash")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
    monkeypatch.delenv("GEMINI_MODELS", raising=False)
    assert model_cascade() == GEMINI_MODELS
    assert model_cascade()[0] == "gemini-3.7-flash"


def test_model_cascade_env_and_preferred(monkeypatch):
    monkeypatch.setenv("GEMINI_MODELS", "gemini-3.7-flash, gemini-2.5-flash")
    assert model_cascade("gemini-2.5-flash") == ["gemini-2.5-flash", "gemini-3.7-flash"]


def test_generate_json_tries_next_model_on_429(monkeypatch):
    monkeypatch.delenv("GEMINI_MODELS", raising=False)
    calls = []

    def generate_content(model, contents, config=None):
        calls.append(model)
        if model == "gemini-3.7-flash":
            raise RuntimeError("429 RESOURCE_EXHAUSTED")
        return SimpleNamespace(text='{"ok": true}', candidates=None)

    client = _client_with_generate(generate_content)
    result = GeminiClient.generate_json(client, "prompt")
    assert result == {"ok": True}
    assert calls == ["gemini-3.7-flash", "gemini-3.6-flash"]


def test_generate_json_preferred_then_cascade_on_429(monkeypatch):
    monkeypatch.setenv("GEMINI_MODELS", "a-flash,b-flash")
    calls = []

    def generate_content(model, contents, config=None):
        calls.append(model)
        if model == "preferred-flash":
            raise RuntimeError("429")
        return SimpleNamespace(text='{"ok": true}', candidates=None)

    client = _client_with_generate(generate_content)
    result = GeminiClient.generate_json(client, "prompt", model="preferred-flash")
    assert result == {"ok": True}
    assert calls == ["preferred-flash", "a-flash"]


def test_generate_json_raises_last_error(monkeypatch):
    monkeypatch.setenv("GEMINI_MODELS", "one-flash,two-flash")

    def generate_content(model, contents, config=None):
        raise RuntimeError(f"fail-{model}")

    client = _client_with_generate(generate_content)
    try:
        GeminiClient.generate_json(client, "prompt")
        assert False, "expected raise"
    except RuntimeError as exc:
        assert "fail-two-flash" in str(exc)


def test_gemini_writer_returns_refuse_dict_unvalidated():
    class Fake:
        def generate_json(self, prompt, model=None, temperature=0.9):
            return {"refuse": True, "note": "Not that one."}

    out = GeminiWriter(Fake()).write_scene("", {}, {}, "bad pitch", source="viewer", username="Alex")
    assert out == {"refuse": True, "note": "Not that one."}
