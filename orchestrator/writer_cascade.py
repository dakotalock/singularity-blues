"""Writer errors fall through to the next model. A deliberate topic veto stops immediately."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from orchestrator import SCENE_SCHEMA_PATH, WRITER_PROMPT_PATH
from orchestrator.denver import denver_logged_at
from orchestrator.moderation import episode_title, wrap_untrusted
from orchestrator.schemas import validate_scene

DEFAULT_VETO_NOTE = "The topic was moderated by the AI."

_INFRA_REFUSE = re.compile(
    r"(?i)\b(json|jsondecodeerror|timeout|timed out|http\s*[45]\d\d|exception|traceback|"
    r"internal error|empty response|truncated|schema validation|"
    r"resource_exhausted|429|500|502|503)\b"
)

_installed = False


def deliberate_refuse_note(payload: Any) -> str | None:
    """Return the viewer note only for a real moderation refuse, not a crashed writer."""
    if not isinstance(payload, dict) or not payload.get("refuse"):
        return None
    if payload.get("beats"):
        return None
    note = payload.get("note") if isinstance(payload.get("note"), str) else ""
    note = note.strip()
    if not note:
        return DEFAULT_VETO_NOTE
    if _INFRA_REFUSE.search(note):
        return None
    return note


def invoke_one_writer_model(client: Any, prompt: str, model_id: str, temperature: float = 1.05) -> Any:
    """Exactly one model. Never the client-level cascade — schema belongs to the writer loop."""
    generate_once = getattr(client, "generate_json_once", None)
    if callable(generate_once):
        return generate_once(prompt, model=model_id, temperature=temperature)
    generate = getattr(client, "generate_json", None)
    if callable(generate):
        return generate(prompt, model=model_id, temperature=temperature)
    raise RuntimeError("writer client cannot generate")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def patched_generate_json_once(self, prompt: str, *, model: str, temperature: float = 0.9) -> dict[str, Any]:
    """Call exactly one model. Empty/non-object responses are errors, not refuses."""
    from orchestrator.gemini import parse_json_text

    resp = self.client.models.generate_content(
        model=model,
        contents=prompt,
        config=self._types.GenerateContentConfig(
            temperature=temperature,
            response_mime_type="application/json",
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
    return payload


def patched_write_scene(
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
    from orchestrator.gemini import WriterCascadeError, model_cascade

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
            payload = invoke_one_writer_model(self.client, prompt, model_id, 1.05)
            note = deliberate_refuse_note(payload)
            if note is not None:
                return {"refuse": True, "note": note}
            if isinstance(payload, dict) and payload.get("refuse"):
                raise RuntimeError("writer returned a malformed refuse")
            if not isinstance(payload, dict):
                raise TypeError("writer response was not a JSON object")
            payload["topic"] = heading
            payload.setdefault("source", source)
            return validate_scene(payload).model_dump()
        except Exception as exc:
            failures.append(exc)
            continue

    if failures:
        last = failures[-1]
        raise WriterCascadeError(
            f"all {len(models)} writer attempts failed; last error: {type(last).__name__}: {last}"
        ) from last
    raise WriterCascadeError("no writer models configured")


def install() -> None:
    """Patch GeminiClient / GeminiWriter so any error tries the next model."""
    global _installed
    if _installed:
        return
    from orchestrator import gemini

    gemini.deliberate_refuse_note = deliberate_refuse_note
    gemini.invoke_one_writer_model = invoke_one_writer_model
    gemini.GeminiClient.generate_json_once = patched_generate_json_once
    gemini.GeminiWriter.write_scene = patched_write_scene
    _installed = True
