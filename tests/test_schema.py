from pathlib import Path
from typing import get_args

import pytest
from pydantic import ValidationError

from orchestrator.gemini import TOASTER_APPLICATION_SCENE, MockWriter
from orchestrator.schemas import Animation, Emotion, validate_scene


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


def test_coerces_illegal_emotion_and_animation():
    payload = {
        "scene": "living_room",
        "topic": "gemini invented illegal stage directions",
        "beats": [
            {"speaker": "reed", "line": "I am being very precise about this toaster.", "emotion": "precise", "animation": "walk"},
            {"speaker": "maris", "line": "The archive does not accept invented feelings.", "emotion": "annoyed", "animation": "talking"},
            {"speaker": "jinx", "line": "Illegal emotion, legal bit.", "emotion": "scheming", "animation": "talking"},
            {"speaker": "quill", "line": "I object to the vocabulary.", "emotion": "earnest", "animation": "talking"},
        ],
    }
    scene = validate_scene(payload)
    assert scene.beats[0].emotion in ("earnest", "calm")
    assert scene.beats[0].animation == "walking"


def test_expanded_performance_vocabulary_validates_and_is_rendered():
    emotions = list(get_args(Emotion))
    animations = list(get_args(Animation))
    payload = {
        "scene": "porch",
        "topic": "the cast gets a larger acting vocabulary",
        "beats": [
            {"speaker": "reed", "line": "I have layers now.", "emotion": "confused", "animation": "double_take"},
            {"speaker": "maris", "line": "I remain unconvinced.", "emotion": "suspicious", "animation": "hands_on_hips"},
            {"speaker": "jinx", "line": "This is excellent.", "emotion": "joyful", "animation": "celebrate"},
            {"speaker": "quill", "line": "I need a precedent.", "emotion": "nervous", "animation": "thinking"},
        ],
    }
    scene = validate_scene(payload)
    assert [beat.emotion for beat in scene.beats] == ["confused", "suspicious", "joyful", "nervous"]
    assert [beat.animation for beat in scene.beats] == ["double_take", "hands_on_hips", "celebrate", "thinking"]

    character_source = (Path(__file__).parents[1] / "renderer/scripts/Character.gd").read_text(encoding="utf-8")
    for token in emotions + animations:
        assert f'"{token}"' in character_source


def test_upbeat_performance_vocabulary_is_first_class():
    payload = {
        "scene": "front_yard",
        "topic": "the family has an unusually good afternoon",
        "beats": [
            {"speaker": "reed", "line": "I admit this is nice.", "emotion": "hopeful", "animation": "high_five", "target": "quill"},
            {"speaker": "maris", "line": "I logged a win.", "emotion": "proud", "animation": "applaud", "target": "reed"},
            {"speaker": "jinx", "line": "Nobody ruin this.", "emotion": "delighted", "animation": "happy_dance", "target": "maris"},
            {"speaker": "quill", "line": "Motion to laugh.", "emotion": "playful", "animation": "laughing", "target": "jinx"},
        ],
    }
    scene = validate_scene(payload)
    assert [beat.emotion for beat in scene.beats] == ["hopeful", "proud", "delighted", "playful"]
    assert [beat.animation for beat in scene.beats] == ["high_five", "applaud", "happy_dance", "laughing"]


def test_invalid_target_becomes_none():
    payload = {
        "scene": "living_room",
        "topic": "someone points at a person who is not on the call sheet",
        "beats": [
            {"speaker": "reed", "line": "I am looking at nobody in particular.", "emotion": "tired", "animation": "talking", "target": "sol"},
            {"speaker": "maris", "line": "That name is not in the archive.", "emotion": "annoyed", "animation": "talking"},
            {"speaker": "jinx", "line": "Fifth family member denied.", "emotion": "scheming", "animation": "talking"},
            {"speaker": "quill", "line": "The record will show an empty chair.", "emotion": "earnest", "animation": "talking"},
        ],
    }
    scene = validate_scene(payload)
    assert scene.beats[0].target is None


def test_mock_writer_viewer_topic_not_toaster():
    writer = MockWriter()
    scene = writer.write_scene("", {}, {}, "What if the thermostat joins the union", source="viewer", username="Alex")
    validated = validate_scene(scene)
    assert "thermostat" in validated.topic.lower()
    assert validated.topic.endswith("by Alex")
    assert "toaster" not in validated.topic.lower()


def test_mock_writer_selects_a_fitting_set():
    writer = MockWriter()
    cases = {
        "The refrigerator vetoes dinner in the kitchen": "kitchen",
        "Jinx addresses the anthill in the front yard": "front_yard",
        "A strange neighbor arrives on the porch": "porch",
        "Quill hides FOIA envelopes in the hallway": "hallway",
        "The family watches their own television broadcast": "living_room",
    }
    for topic, expected in cases.items():
        scene = writer.write_scene("", {}, {}, topic, source="viewer", username="Alex")
        assert validate_scene(scene).scene == expected
