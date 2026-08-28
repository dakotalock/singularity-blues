from types import SimpleNamespace
import json
import pytest

from orchestrator.gemini import GeminiClient, GeminiWriter, GEMINI_MODELS, WriterCascadeError, model_cascade
from orchestrator.writer_cascade import DEFAULT_VETO_NOTE, install as _install_writer_cascade

_install_writer_cascade()


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
    assert calls == ["writer-one"]
    assert out == {"refuse": True, "note": "No."}


def test_writer_tries_next_model_after_validation_error(monkeypatch):
    monkeypatch.setenv("GEMINI_MODELS", "writer-one,writer-two,writer-three")
    calls = []

    class Fake:
        def generate_json_once(self, prompt, model, temperature=0.9):
            calls.append(model)
            if model == "writer-one":
                return _valid_scene("x" * 281)
            return _valid_scene()

    out = GeminiWriter(Fake()).write_scene("", {}, {}, "a difficult prompt", source="viewer", username="Alex")
    assert calls == ["writer-one", "writer-two"]
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
    assert calls == ["writer-one"]
    assert out == {"refuse": True, "note": "Declined by writer-one."}


def test_writer_empty_refuse_note_is_veto_with_default(monkeypatch):
    monkeypatch.setenv("GEMINI_MODELS", "writer-one,writer-two")
    calls = []

    class Fake:
        def generate_json_once(self, prompt, model, temperature=0.9):
            calls.append(model)
            return {"refuse": True, "note": ""}

    out = GeminiWriter(Fake()).write_scene("", {}, {}, "a difficult prompt", source="viewer")
    assert calls == ["writer-one"]
    assert out == {"refuse": True, "note": DEFAULT_VETO_NOTE}


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


def test_writer_uses_second_model_after_invalid_json(monkeypatch):
    monkeypatch.setenv("GEMINI_MODELS", "writer-one,writer-two")
    calls = []

    class Fake:
        def generate_json_once(self, prompt, model, temperature=0.9):
            calls.append(model)
            if model == "writer-one":
                raise json.JSONDecodeError("Expecting value", "not-json {", 0)
            return _valid_scene()

    out = GeminiWriter(Fake()).write_scene("", {}, {}, "thermostat union", source="viewer", username="Alex")
    assert calls == ["writer-one", "writer-two"]
    assert out["beats"][0]["speaker"] == "reed"
    assert "thermostat union" in out["topic"]


def test_writer_retries_timeout_http_empty_and_garbage_then_succeeds(monkeypatch):
    monkeypatch.setenv("GEMINI_MODELS", "writer-one,writer-two,writer-three")
    calls = []

    class Fake:
        def generate_json_once(self, prompt, model, temperature=0.9):
            calls.append(model)
            if model == "writer-one":
                raise TimeoutError("deadline exceeded")
            if model == "writer-two":
                raise RuntimeError("empty writer response")
            return _valid_scene()

    out = GeminiWriter(Fake()).write_scene("", {}, {}, "a difficult prompt", source="viewer")
    assert calls == ["writer-one", "writer-two", "writer-three"]
    assert len(out["beats"]) >= 4


def test_writer_two_fail_one_succeeds_does_not_raise(monkeypatch):
    monkeypatch.setenv("GEMINI_MODELS", "writer-one,writer-two,writer-three")
    calls = []

    class Fake:
        def generate_json_once(self, prompt, model, temperature=0.9):
            calls.append(model)
            if model == "writer-one":
                raise RuntimeError("502 Bad Gateway")
            if model == "writer-two":
                return "truncated{"
            return _valid_scene()

    out = GeminiWriter(Fake()).write_scene("", {}, {}, "a difficult prompt", source="viewer")
    assert calls == ["writer-one", "writer-two", "writer-three"]
    assert out["scene"] == "living_room"


def test_writer_all_three_invalid_json_raises_cascade(monkeypatch):
    monkeypatch.setenv("GEMINI_MODELS", "writer-one,writer-two,writer-three")
    calls = []

    class Fake:
        def generate_json_once(self, prompt, model, temperature=0.9):
            calls.append(model)
            raise json.JSONDecodeError("Expecting value", "{", 0)

    with pytest.raises(WriterCascadeError, match="all 3 writer attempts failed"):
        GeminiWriter(Fake()).write_scene("", {}, {}, "a difficult prompt", source="viewer")
    assert calls == ["writer-one", "writer-two", "writer-three"]


def test_writer_malformed_refuse_is_error_not_moderation(monkeypatch):
    monkeypatch.setenv("GEMINI_MODELS", "writer-one,writer-two")
    calls = []

    class Fake:
        def generate_json_once(self, prompt, model, temperature=0.9):
            calls.append(model)
            if model == "writer-one":
                return {"refuse": True, "note": "JSONDecodeError: truncated output"}
            return _valid_scene()

    out = GeminiWriter(Fake()).write_scene("", {}, {}, "a difficult prompt", source="viewer")
    assert calls == ["writer-one", "writer-two"]
    assert "beats" in out


def test_generate_json_once_empty_response_raises():
    def generate_content(model, contents, config=None):
        return SimpleNamespace(text="", candidates=None)

    client = _client_with_generate(generate_content)
    with pytest.raises(RuntimeError, match="empty writer response"):
        GeminiClient.generate_json_once(client, "prompt", model="writer-one")


def test_writer_call_uses_scene_or_veto_schema_and_supported_temperature():
    captured = {}

    def generate_content(model, contents, config=None):
        captured["model"] = model
        captured["config"] = config
        return SimpleNamespace(text='{"result": {"refuse": true, "note": "Not this topic."}}', candidates=None)

    client = _client_with_generate(generate_content)
    out = GeminiClient.generate_writer_json_once(client, "prompt", model="writer-one")
    assert out["refuse"] is True
    assert captured["model"] == "writer-one"
    assert 0.0 <= captured["config"]["temperature"] <= 1.0
    schema = captured["config"]["response_json_schema"]
    choices = schema["properties"]["result"]["anyOf"]
    assert len(choices) == 2
    assert choices[0]["properties"]["beats"]["minItems"] == 4
    assert choices[1]["required"] == ["refuse", "note"]
    assert "minLength" not in json.dumps(schema)
    assert "maxLength" not in json.dumps(schema)


def test_writer_prefers_schema_constrained_method(monkeypatch):
    monkeypatch.setenv("GEMINI_MODELS", "writer-one")
    calls = []

    class Fake:
        def generate_writer_json_once(self, prompt, model, temperature=0.9):
            calls.append(("structured", model, temperature))
            return _valid_scene()

        def generate_json_once(self, prompt, model, temperature=0.9):
            calls.append(("generic", model, temperature))
            return _valid_scene()

    out = GeminiWriter(Fake()).write_scene("", {}, {}, "a normal topic", source="viewer")
    assert out["scene"] == "living_room"
    assert calls == [("structured", "writer-one", 0.95)]


def test_writer_model_cascade_appends_gemma4_after_gemini(monkeypatch):
    monkeypatch.setenv("GEMINI_MODELS", "gemini-3.7-flash,gemini-2.5-flash")
    monkeypatch.delenv("GEMMA_MODELS", raising=False)
    from orchestrator.gemini import writer_model_cascade
    assert writer_model_cascade() == [
        "gemini-3.7-flash",
        "gemini-2.5-flash",
        "gemma-4-31b-it",
        "gemma-4-26b-a4b-it",
    ]


def test_writer_skips_remaining_gemini_on_429_and_uses_gemma(monkeypatch):
    monkeypatch.setenv("GEMINI_MODELS", "gemini-3.7-flash,gemini-3.6-flash")
    monkeypatch.setenv("GEMMA_MODELS", "gemma-4-31b-it")
    calls = []

    class Fake:
        def generate_writer_json_once(self, prompt, model, temperature=0.9):
            calls.append(("structured", model))
            if str(model).startswith("gemini-"):
                raise RuntimeError("429 RESOURCE_EXHAUSTED")
            raise AssertionError("Gemma should not use the Gemini JSON schema path")

        def generate_json_once(self, prompt, model, temperature=0.9):
            calls.append(("plain", model))
            return _valid_scene()

    out = GeminiWriter(Fake()).write_scene("", {}, {}, "a difficult prompt", source="viewer")
    assert ("structured", "gemini-3.7-flash") in calls
    assert ("structured", "gemini-3.6-flash") not in calls
    assert ("plain", "gemma-4-31b-it") in calls
    assert out["scene"] == "living_room"
