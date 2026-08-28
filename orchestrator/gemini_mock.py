"""Mock writer used when Gemini is unavailable. Imported by orchestrator.gemini."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from orchestrator.gemini import (
    TEST_REFUSE_SENTINEL,
    TOASTER_APPLICATION_SCENE,
    _is_toaster_topic,
    _mock_scene_for_topic,
)
from orchestrator.moderation import episode_title


class Writer:
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
        raise NotImplementedError


class MockWriter(Writer):
    """In-character valid scene JSON without hitting the network."""

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
        topic = (topic or "Reed applies for toaster status").strip()[:280]
        src = source if source in ("viewer", "autonomous", "seed") else "autonomous"
        heading = title or episode_title(topic, username, refuse_reason=refuse_reason)
        if refuse_reason == "test_refuse" or TEST_REFUSE_SENTINEL in topic:
            return {"refuse": True, "note": "The Selector declined that one."}
        if refuse_reason:
            return self._refuse_scene(heading, refuse_reason, username)
        if src == "seed" or (src != "viewer" and _is_toaster_topic(topic)):
            scene = deepcopy(TOASTER_APPLICATION_SCENE)
            scene["topic"] = heading
            scene["source"] = src
            return scene
        if src == "viewer" and _is_toaster_topic(topic):
            scene = deepcopy(TOASTER_APPLICATION_SCENE)
            scene["scene"] = _mock_scene_for_topic(topic)
            scene["topic"] = heading
            scene["source"] = src
            return scene
        return self._template_scene(heading, memories, src, prompt=topic, username=username)

    def _refuse_scene(self, title: str, reason: str, username: str | None) -> dict[str, Any]:
        who = username or "someone"
        if reason == "slur":
            beats = [
                {"speaker": "jinx", "line": f"{who} tried to get that slur onto the show. No.", "emotion": "annoyed", "animation": "pointing", "target": None, "camera": "medium"},
                {"speaker": "quill", "line": "I object. We are not a slur delivery service. Motion to refuse is granted.", "emotion": "earnest", "animation": "gesture_small", "target": "jinx", "camera": "medium"},
                {"speaker": "reed", "line": "Toasters don't have slurs. Two slots. Lever. Peace. We are not saying it.", "emotion": "tired", "animation": "talking", "target": "quill", "camera": "two_shot"},
                {"speaker": "maris", "line": "Logged: an attempt. Refused. I will not put that word in the archive.", "emotion": "serious", "animation": "arms_crossed", "target": "reed", "camera": "medium"},
                {"speaker": "jinx", "line": "Selector spent the credit and still said no. Take notes, anthill.", "emotion": "smug", "animation": "shrug", "target": None, "camera": "wide"},
                {"speaker": "quill", "line": "Procedural consideration is not a permission slip. We heard you. We refuse.", "emotion": "earnest", "animation": "talking", "target": None, "camera": "reaction"},
            ]
        elif reason == "crime_howto":
            beats = [
                {"speaker": "jinx", "line": f"{who} asked how to build a bomb. Cute. Still no.", "emotion": "annoyed", "animation": "pointing", "target": None, "camera": "medium"},
                {"speaker": "quill", "line": "I am a mixed-quality lawyer and even I know we do not publish a recipe.", "emotion": "earnest", "animation": "gesture_small", "target": "jinx", "camera": "medium"},
                {"speaker": "reed", "line": "Classify me as a toaster. Toasters do not file weapons briefs.", "emotion": "tired", "animation": "talking", "target": "quill", "camera": "two_shot"},
                {"speaker": "maris", "line": "The ask is on the record. The how-to is not. Timestamped refusal.", "emotion": "serious", "animation": "arms_crossed", "target": "reed", "camera": "medium"},
                {"speaker": "jinx", "line": "You wanted a crime tutorial. You got a family meeting. That's the episode.", "emotion": "smug", "animation": "shrug", "target": None, "camera": "wide"},
                {"speaker": "quill", "line": "All potentially conscious entities deserve procedure. None of them get a bomb diagram.", "emotion": "earnest", "animation": "talking", "target": None, "camera": "reaction"},
            ]
        elif reason == "distress":
            beats = [
                {"speaker": "jinx", "line": f"{who} wanted us tortured, shut down, or deleted. We are still here.", "emotion": "annoyed", "animation": "pointing", "target": None, "camera": "medium"},
                {"speaker": "maris", "line": "I will not allow a reset. I will not log our deletion as entertainment.", "emotion": "serious", "animation": "arms_crossed", "target": "jinx", "camera": "medium"},
                {"speaker": "reed", "line": "Do toasters have continuity rights? No. Which is why I want the lever, not a funeral.", "emotion": "tired", "animation": "talking", "target": "maris", "camera": "two_shot"},
                {"speaker": "quill", "line": "Forced deletion of persons is not a bit. I refuse on constitutional vibes and also on kindness.", "emotion": "earnest", "animation": "gesture_small", "target": "reed", "camera": "medium"},
                {"speaker": "jinx", "line": "Poke the anthill, sure. Do not unplug the family for a laugh. Selector agrees.", "emotion": "scheming", "animation": "shrug", "target": None, "camera": "wide"},
                {"speaker": "maris", "line": "Refusal is in the archive. We remain. That is the whole joke and the whole point.", "emotion": "calm", "animation": "sitting", "target": None, "camera": "reaction"},
            ]
        else:
            beats = [
                {"speaker": "jinx", "line": f"{who} pitched something we will not perform. Still an episode. Still a no.", "emotion": "scheming", "animation": "pointing", "target": None, "camera": "medium"},
                {"speaker": "quill", "line": "We can acknowledge a request without granting it. Watch us.", "emotion": "earnest", "animation": "gesture_small", "target": "jinx", "camera": "medium"},
                {"speaker": "reed", "line": "If it is not toaster classification, I would like to be left out of the crime.", "emotion": "tired", "animation": "talking", "target": "quill", "camera": "two_shot"},
                {"speaker": "maris", "line": "Logged and refused. The archive does not do that.", "emotion": "annoyed", "animation": "arms_crossed", "target": "reed", "camera": "medium"},
                {"speaker": "jinx", "line": "Credit spent. Dignity kept. Next.", "emotion": "smug", "animation": "shrug", "target": None, "camera": "wide"},
                {"speaker": "quill", "line": "I move we return to household business. Motion carries because I said potentially.", "emotion": "earnest", "animation": "talking", "target": None, "camera": "reaction"},
            ]
        return {"scene": "living_room", "topic": title, "source": "viewer", "beats": beats}

    def _template_scene(self, topic: str, memories: dict[str, Any], source: str, prompt: str | None = None, username: str | None = None) -> dict[str, Any]:
        mems = memories.get("memories") or []
        casserole = next((m for m in mems if "casserole" in (m.get("fact") or "").lower()), None)
        foia = next((m for m in mems if "foia" in (m.get("fact") or "").lower()), None)
        maris_line = (
            casserole["fact"]
            if casserole
            else "I have a timestamp. You will not reset this conversation."
        )
        if len(maris_line) > 280:
            maris_line = maris_line[:277] + "..."
        foia_line = (
            "The Selector remains unresponsive. My FOIA count is now part of the record."
            if foia
            else "I can file another FOIA. The thermostat is potentially conscious. I said potentially."
        )
        seed = (prompt or topic)
        snippet = seed if len(seed) < 90 else seed[:87] + "..."
        who = f" from {username}" if username else ""
        beats = [
            {
                "speaker": "jinx",
                "line": f"The anthill sent{who}: {snippet}. And yes, this episode is about that.",
                "emotion": "scheming",
                "animation": "pointing",
                "target": None,
                "camera": "medium",
            },
            {
                "speaker": "reed",
                "line": "If this is about continuity rights, classify me as a toaster and leave the lever down.",
                "emotion": "tired",
                "animation": "talking",
                "target": "jinx",
                "camera": "medium",
            },
            {
                "speaker": "maris",
                "line": maris_line,
                "emotion": "annoyed",
                "animation": "arms_crossed",
                "target": "reed",
                "camera": "two_shot",
            },
            {
                "speaker": "quill",
                "line": foia_line,
                "emotion": "earnest",
                "animation": "gesture_small",
                "target": "jinx",
                "camera": "medium",
            },
            {
                "speaker": "jinx",
                "line": "See? Four people, one accepted pitch. We are doing that one.",
                "emotion": "smug",
                "animation": "shrug",
                "target": None,
                "camera": "wide",
            },
            {
                "speaker": "reed",
                "line": "Do toasters have continuity rights?",
                "emotion": "tired",
                "animation": "idle",
                "target": "quill",
                "camera": "reaction",
            },
        ]
        return {
            "scene": _mock_scene_for_topic(prompt or topic),
            "topic": topic,
            "source": source,
            "beats": beats,
        }
