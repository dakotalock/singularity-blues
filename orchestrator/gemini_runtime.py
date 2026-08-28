"""Gemini client and writer. GeminiWriter.write_scene stops on a real topic veto."""

from __future__ import annotations

import json
import os
from typing import Any

from orchestrator import SCENE_SCHEMA_PATH, WRITER_PROMPT_PATH
from orchestrator.denver import denver_logged_at
from orchestrator.gemini import (
    WriterCascadeError,
    _read,
    has_gemini_key,
    model_cascade,
    parse_json_text,
)
from orchestrator.gemini_mock import MockWriter, Writer
from orchestrator.moderation import episode_title, wrap_untrusted
from orchestrator.schemas import validate_scene
from orchestrator.writer_cascade import (
    DEFAULT_VETO_NOTE,
    WRITER_TEMPERATURE,
    deliberate_refuse_note,
    writer_response_schema,
)


class GeminiClient:
    """Thin wrapper around google-genai. Only constructed when a key is present."""

    def __init__(self) -> None:
        if not has_gemini_key():
            raise RuntimeError("GEMINI_API_KEY missing")
        from google import genai  # type: ignore
        from google.genai import types  # type: ignore

        self._types = types
        self.client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
        self.lite_model = os.environ.get("GEMINI_MODEL", "")
        self.writer_model = os.environ.get("GEMINI_WRITER_MODEL", "")

    @staticmethod
    def _is_gemma(model: str) -> bool:
        return str(model).strip().lower().startswith("gemma-")

    def _json_config(
        self,
        *,
        model: str,
        temperature: float,
        response_json_schema: dict[str, Any] | None = None,
    ) -> Any:
        """Use constrained JSON for Gemini and prompt-only JSON for Gemma."""
        kwargs: dict[str, Any] = {
            "temperature": min(1.0, max(0.0, temperature)),
        }
        if not self._is_gemma(model):
            kwargs["response_mime_type"] = "application/json"
            if response_json_schema is not None:
                kwargs["response_json_schema"] = response_json_schema
        return self._types.GenerateContentConfig(**kwargs)

    def generate_json_once(self, prompt: str, *, model: str, temperature: float = 0.9) -> dict[str, Any]:
        """Call exactly one model. Writer-level validation decides whether to continue."""
        resp = self.client.models.generate_content(
            model=model,
            contents=prompt,
            config=self._json_config(model=model, temperature=temperature),
        )
        text = getattr(resp, "text", None) or ""
        if not text and getattr(resp, "candidates", None):
            try:
                text = resp.candidates[0].content.parts[0].text
            except Exception:
                text = ""
        blob = (text or "").strip()
        if not blob:
            raise RuntimeError("empty writer response")
        payload = parse_json_text(blob)
        if not isinstance(payload, dict):
            raise TypeError("response was not a JSON object")
        return payload

    def generate_writer_json_once(
        self,
        prompt: str,
        *,
        model: str,
        temperature: float = WRITER_TEMPERATURE,
    ) -> dict[str, Any]:
        """Call one writer with a scene-or-veto schema so malformed JSON cannot look like a veto."""
        if str(model).lower().startswith("gemma-"):
            return self.generate_json_once(prompt, model=model, temperature=temperature)
        resp = self.client.models.generate_content(
            model=model,
            contents=prompt,
            config=self._json_config(
                model=model,
                temperature=temperature,
                response_json_schema=writer_response_schema(),
            ),
        )
        text = getattr(resp, "text", None) or ""
        if not text and getattr(resp, "candidates", None):
            try:
                text = resp.candidates[0].content.parts[0].text
            except Exception:
                text = ""
        blob = (text or "").strip()
        if not blob:
            raise RuntimeError("empty writer response")
        payload = parse_json_text(blob)
        if not isinstance(payload, dict):
            raise TypeError("writer response was not a JSON object")
        result = payload.get("result")
        if isinstance(result, dict):
            return result
        # Compatibility with providers/test doubles that already return the
        # inner object even when given a top-level response schema.
        return payload

    def generate_json(self, prompt: str, *, model: str | None = None, temperature: float = 0.9) -> dict[str, Any]:
        last_err: Exception | None = None
        for mid in model_cascade(model):
            try:
                return self.generate_json_once(prompt, model=mid, temperature=temperature)
            except Exception as exc:
                last_err = exc
                continue
        if last_err is not None:
            raise last_err
        raise RuntimeError("no models configured")


def get_gemini_client() -> GeminiClient | None:
    if not has_gemini_key():
        return None
    try:
        return GeminiClient()
    except Exception:
        return None


class GeminiWriter(Writer):
    def __init__(self, client: GeminiClient) -> None:
        self.client = client

    def write_scene(
        self,
        bible: str,
        states: dict[str, Any],
        memories: dict[str, Any],
        topic: str,
        *,
        source: str = "autonomous",
        username: str | None = None,
        paid: bool = False,
        refuse_reason: str | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        schema = _read(SCENE_SCHEMA_PATH)
        writer_rules = _read(WRITER_PROMPT_PATH)
        heading = title or episode_title(topic, username, refuse_reason=refuse_reason)
        ledger = []
        for row in memories.get("memories") or []:
            ledger.append(
                {
                    "id": row.get("id"),
                    "episode_id": row.get("episode_id"),
                    "who": row.get("character"),
                    "category": row.get("character"),
                    "fact": row.get("fact"),
                    "logged_at": denver_logged_at(row.get("created_at")),
                }
            )
        prompt = (
            writer_rules
            + "\n\n## Show bible (trusted)\n"
            + bible
            + "\n\n## Scene JSON schema (trusted)\n"
            + schema
            + "\n\n## CANONICAL_MEMORIES (trusted; the only past anyone may cite)\n"
            + json.dumps(ledger, ensure_ascii=True, default=str)
            + "\n\n## Retrieved state (trusted JSON from our DB)\n"
            + json.dumps(
                {
                    "source": source,
                    "title": heading,
                    "username": username or "",
                    "paid": bool(paid),
                    "refuse_reason": refuse_reason or "",
                    "must_honor_accepted_viewer_topic": source == "viewer",
                    "preferences": memories.get("preferences"),
                    "running_gags": memories.get("running_gags"),
                    "world_state": memories.get("world_state"),
                    "relationships": memories.get("relationships"),
                    "recent_episodes": memories.get("recent_episodes"),
                    "character_arcs": {
                        k: v
                        for k, v in (memories.get("world_state") or {}).items()
                        if str(k).startswith("arc.")
                    },
                },
                ensure_ascii=True,
                default=str,
            )
            + "\n\n"
            + wrap_untrusted("VIEWER_TOPIC", {"topic": topic, "claimed_source": source, "title": heading})
            + "\nOutput ONLY valid scene JSON. Use a refuse object only for a genuine topic veto.\n"
        )
        models = model_cascade()
        failures: list[Exception] = []
        for model_id in models:
            try:
                generate_once = getattr(self.client, "generate_writer_json_once", None)
                if not callable(generate_once):
                    generate_once = getattr(self.client, "generate_json_once", None)
                if callable(generate_once):
                    payload = generate_once(prompt, model=model_id, temperature=WRITER_TEMPERATURE)
                else:
                    payload = self.client.generate_json(prompt, model=model_id, temperature=WRITER_TEMPERATURE)
                note = deliberate_refuse_note(payload)
                if note is not None:
                    return {"refuse": True, "note": note or DEFAULT_VETO_NOTE}
                if isinstance(payload, dict) and payload.get("refuse"):
                    raise RuntimeError("writer returned a malformed refuse")
                if not isinstance(payload, dict):
                    raise TypeError("writer response was not a JSON object")
                payload["topic"] = heading
                payload.setdefault("source", source)
                return validate_scene(payload).model_dump()
            except Exception as exc:
                failures.append(exc)

        if failures:
            last = failures[-1]
            raise WriterCascadeError(
                f"all {len(models)} writer attempts failed; last error: {type(last).__name__}: {last}"
            ) from last
        raise WriterCascadeError("no writer models configured")


def get_writer() -> Writer:
    client = get_gemini_client()
    if client is not None:
        return GeminiWriter(client)
    return MockWriter()
