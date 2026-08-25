import pytest
from pydantic import ValidationError

from orchestrator.gemini import TOASTER_APPLICATION_SCENE, MockWriter
from orchestrator.schemas import validate_scene


def test_toaster_scene_validates():
    scene = validate_scene(TOASTER_APPLICATION_SCENE)
    speakers = {b.speaker for b in scene.beats}
    assert speakers == {"reed", "maris", "jinx", "quill"}
    text = " ".join(b.line.lower() for b in scene.beats)
    assert "crumb tray" in text
    assert "veto" in text


def test_mock_writer_toaster_topic_has_required_bits():
    writer = MockWriter()
    scene = writer.write_scene("", {}, {}, "Reed applies for toaster status", source="seed")
    validated = validate_scene(scene)
    joined = " ".join(b.line for b in validated.beats)
    assert "crumb tray" in joined.lower()
    assert "veto" in joined.lower()
    assert {b.speaker for b in validated.beats} == {"reed", "maris", "jinx", "quill"}


def test_rejects_sol_as_speaker():
    payload = {
        "scene": "living_room",
        "topic": "someone named Sol shows up",
        "beats": [
            {"speaker": "sol", "line": "hi", "emotion": "calm", "animation": "talking"},
            {"speaker": "reed", "line": "no", "emotion": "tired", "animation": "talking"},
            {"speaker": "maris", "line": "no", "emotion": "annoyed", "animation": "talking"},
            {"speaker": "jinx", "line": "no", "emotion": "scheming", "animation": "talking"},
        ],
    }
    with pytest.raises(ValidationError):
        validate_scene(payload)


def test_rejects_too_few_beats():
    payload = {
        "scene": "living_room",
        "topic": "too short",
        "beats": [
            {"speaker": "reed", "line": "a", "emotion": "tired", "animation": "talking"},
            {"speaker": "maris", "line": "b", "emotion": "annoyed", "animation": "talking"},
            {"speaker": "jinx", "line": "c", "emotion": "scheming", "animation": "talking"},
        ],
    }
    with pytest.raises(ValidationError):
        validate_scene(payload)


def test_kitchen_and_porch_are_valid_sets():
    for name in ("kitchen", "porch", "hallway", "front_yard"):
        payload = {
            "scene": name,
            "topic": "fridge politics on a new set",
            "beats": [
                {"speaker": "reed", "line": "I would like to be a toaster in this room too.", "emotion": "tired", "animation": "talking"},
                {"speaker": "maris", "line": "I have the casserole timestamp on file. I am not inventing a new Tuesday.", "emotion": "annoyed", "animation": "talking"},
                {"speaker": "jinx", "line": "New walls, same anthill.", "emotion": "scheming", "animation": "talking"},
                {"speaker": "quill", "line": "I move we take notice of the change of venue.", "emotion": "earnest", "animation": "talking"},
            ],
        }
        assert validate_scene(payload).scene == name
