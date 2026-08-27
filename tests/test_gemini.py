from types import SimpleNamespace
import pytest

from orchestrator.gemini import GeminiClient, GeminiWriter, GEMINI_MODELS, WriterCascadeError, model_cascade


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


def _valid_scene(line: str = "A valid line."):
    return {
        "scene": "living_room",
        "topic": "temporary",
        "source": "viewer",
        "beats": [
            {"speaker": "reed", "line": line, "emotion": "confused", "animation": "double_take"},
            {"speaker": "maris", "line": "Logged.", "emotion": "determined", "animation": "hands_on_hips"},
            {"speaker": "jinx", "line": "Interesting.", "emotion": "suspicious", "animation": "lean_in"},
            {"speaker": "quill", "line": "I object.", "emotion": "nervous", "animation": "facepalm"},
        ],
    }


def test_writer_tries_next_model_after_refusal_and_validation_error(monkeypatch):
    monkeypatch.setenv("GEMINI_MODELS", "writer-one,writer-two,writer-three")
    calls = []

    class Fake:
        def generate_json_once(self, prompt, model, temperature=0.9):
            calls.append(model)
            if model == "writer-one":
                return {"refuse": True, "note": "No."}
            if model == "writer-two":
                return _valid_scene("x" * 281)
            return _valid_scene()

    out = GeminiWriter(Fake()).write_scene("", {}, {}, "a difficult prompt", source="viewer", username="Alex")
    assert calls == ["writer-one", "writer-two", "writer-three"]
    assert out["topic"] == "a difficult prompt by Alex"
    assert out["beats"][0]["animation"] == "double_take"


def test_writer_accepts_refusal_only_after_all_three_refuse(monkeypatch):
    monkeypatch.setenv("GEMINI_MODELS", "writer-one,writer-two,writer-three")
    calls = []

    class Fake:
        def generate_json_once(self, prompt, model, temperature=0.9):
            calls.append(model)
            return {"refuse": True, "note": f"Declined by {model}."}

    out = GeminiWriter(Fake()).write_scene("", {}, {}, "a difficult prompt", source="viewer")
    assert calls == ["writer-one", "writer-two", "writer-three"]
    assert out == {"refuse": True, "note": "Declined by writer-one."}


def test_writer_raises_only_after_all_three_invalid(monkeypatch):
    monkeypatch.setenv("GEMINI_MODELS", "writer-one,writer-two,writer-three")
    calls = []

    class Fake:
        def generate_json_once(self, prompt, model, temperature=0.9):
            calls.append(model)
            return _valid_scene("x" * 281)

    with pytest.raises(WriterCascadeError, match="all 3 writer attempts failed"):
        GeminiWriter(Fake()).write_scene("", {}, {}, "a difficult prompt", source="viewer")
    assert calls == ["writer-one", "writer-two", "writer-three"]
