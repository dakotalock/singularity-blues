"""Topic selector: regex prefilter, then Gemini or heuristic. Always autonomous on scream/spam/empty."""

from __future__ import annotations

from typing import Any

from orchestrator.gemini import get_gemini_client, llm_select
from orchestrator.moderation import FilterResult, is_scream_or_spam_queue, prefilter
from orchestrator.schemas import SelectorChoice

AUTONOMOUS_TOPICS = [
    "Reed applies for toaster status",
    "The thermostat requests a union",
    "Lasagna night versus the fridge's dinner veto",
    "Zoning: is a toaster a small appliance or a person",
    "Tuesday timestamps and the casserole that will not die",
    "Quill files FOIA number eighteen",
    "Jinx tries to make Reed choose to scream",
]


def pick_autonomous(context: dict[str, Any] | None = None, reason: str = "queue empty") -> SelectorChoice:
    recent = [t.lower() for t in (context or {}).get("recent_topics") or []]
    for topic in AUTONOMOUS_TOPICS:
        if topic.lower() not in recent:
            return SelectorChoice(source="autonomous", topic=topic, reason=reason)
    # All used recently: still reject humanity, rotate.
    topic = AUTONOMOUS_TOPICS[len(recent) % len(AUTONOMOUS_TOPICS)]
    return SelectorChoice(source="autonomous", topic=topic, reason=reason + "; rotating household life")


def _heuristic_pick(kept: list[dict[str, Any]], context: dict[str, Any]) -> SelectorChoice:
    recent = [t.lower() for t in context.get("recent_topics") or []]

    def score(item: dict[str, Any]) -> float:
        text = item.get("text") or ""
        s = min(len(text), 140) / 140.0
        if text.lower() in recent:
            s -= 1.0
        for r in recent:
            if r and r[:40] in text.lower():
                s -= 0.4
        if "toaster" in text.lower() or "selector" in text.lower() or "thermostat" in text.lower():
            s += 0.15
        return s

    best = max(kept, key=score)
    return SelectorChoice(
        source="viewer",
        topic=best["text"][:280],
        reason="heuristic: novel enough and in-character",
    )


def choose(
    prompts: list[dict[str, Any]] | FilterResult | None,
    context: dict[str, Any] | None = None,
    *,
    already_filtered: bool = False,
) -> SelectorChoice:
    """
    Prefilter (unless already done), then Gemini or heuristic.
    ALWAYS autonomous if the queue is scream/spam/empty.
    """
    context = context or {}
    if isinstance(prompts, FilterResult):
        filtered = prompts
    elif already_filtered:
        filtered = FilterResult(kept=list(prompts or []))
    else:
        filtered = prefilter(prompts or [], recent_texts=context.get("recent_prompt_texts") or [])

    if is_scream_or_spam_queue(filtered):
        reason = "queue empty or scream/spam; rejecting humanity"
        return pick_autonomous(context, reason=reason)

    client = get_gemini_client()
    if client is not None:
        try:
            topics = [p["text"] for p in filtered.kept]
            choice = llm_select(client, topics, context)
            # If the model tries to pick a viewer topic we already rejected, fall back.
            if choice.source == "viewer" and choice.topic not in topics:
                # Allow close-enough: still a viewer-sourced rewrite only if it looks like a kept prompt.
                lowered = choice.topic.lower()
                if not any(lowered in (t.lower()) or t.lower() in lowered for t in topics):
                    return _heuristic_pick(filtered.kept, context)
            return choice
        except Exception:
            pass
    return _heuristic_pick(filtered.kept, context)
