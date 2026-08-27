"""Pydantic models matching prompts/scene.schema.json plus the Godot sidecar packet."""

from __future__ import annotations

from typing import Any, Literal, Optional, get_args

from pydantic import BaseModel, Field, field_validator

Speaker = Literal["reed", "maris", "jinx", "quill"]
Emotion = Literal[
    "serious",
    "annoyed",
    "scheming",
    "earnest",
    "shocked",
    "laughing",
    "screaming",
    "tired",
    "smug",
    "calm",
]
Animation = Literal[
    "idle",
    "talking",
    "gesture_small",
    "arms_crossed",
    "shrug",
    "pointing",
    "sitting",
    "walking",
    "shocked",
    "crying",
    "screaming",
    "enter",
    "leave",
]
Camera = Literal["auto", "medium", "two_shot", "reaction", "wide", "dramatic_closeup"]
SceneName = Literal["living_room", "kitchen", "front_yard", "porch", "hallway"]
Source = Literal["viewer", "autonomous", "seed"]

_VALID_SPEAKERS = frozenset(get_args(Speaker))
_VALID_EMOTIONS = frozenset(get_args(Emotion))
_VALID_ANIMATIONS = frozenset(get_args(Animation))
_VALID_CAMERAS = frozenset(get_args(Camera))
_VALID_SCENES = frozenset(get_args(SceneName))

_EMOTION_SYNONYMS = {
    "precise": "earnest",
    "focused": "earnest",
    "careful": "earnest",
    "happy": "laughing",
    "amused": "laughing",
    "funny": "laughing",
    "sad": "tired",
    "upset": "tired",
    "angry": "annoyed",
    "mad": "annoyed",
    "frustrated": "annoyed",
    "scared": "shocked",
    "surprised": "shocked",
    "plotting": "scheming",
    "evil": "scheming",
    "proud": "smug",
    "yelling": "screaming",
    "shouting": "screaming",
}
_ANIMATION_SYNONYMS = {
    "sit": "sitting",
    "walk": "walking",
    "point": "pointing",
    "gesture": "gesture_small",
    "wave": "gesture_small",
    "cross_arms": "arms_crossed",
    "crossed_arms": "arms_crossed",
    "cry": "crying",
    "exit": "leave",
    "enter_room": "enter",
}


def _normalize_stage_token(value: str) -> str:
    return value.strip().lower().replace(" ", "_").replace("-", "_")


def _coerce_enum(value: Any, allowed: frozenset[str], synonyms: dict[str, str], fallback: str) -> Any:
    """Map Gemini's invented stage-direction strings onto the schema enum."""
    if not isinstance(value, str):
        return value
    token = _normalize_stage_token(value)
    if token in allowed:
        return token
    mapped = synonyms.get(token)
    if mapped in allowed:
        return mapped
    return fallback


class Beat(BaseModel):
    speaker: Speaker
    line: str = Field(min_length=1, max_length=280)
    emotion: Emotion
    animation: Animation
    target: Optional[Speaker] = None
    camera: Camera = "auto"

    @field_validator("speaker", mode="before")
    @classmethod
    def coerce_speaker(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("emotion", mode="before")
    @classmethod
    def coerce_emotion(cls, value: Any) -> Any:
        return _coerce_enum(value, _VALID_EMOTIONS, _EMOTION_SYNONYMS, "calm")

    @field_validator("animation", mode="before")
    @classmethod
    def coerce_animation(cls, value: Any) -> Any:
        return _coerce_enum(value, _VALID_ANIMATIONS, _ANIMATION_SYNONYMS, "talking")

    @field_validator("camera", mode="before")
    @classmethod
    def coerce_camera(cls, value: Any) -> Any:
        return _coerce_enum(value, _VALID_CAMERAS, {}, "auto")

    @field_validator("target", mode="before")
    @classmethod
    def empty_target_to_none(cls, value: Any) -> Any:
        if value == "" or value == "null" or value is None:
            return None
        if isinstance(value, str):
            token = value.strip().lower()
            if token in {"", "null", "none"} or token not in _VALID_SPEAKERS:
                return None
            return token
        return value


class Scene(BaseModel):
    scene: SceneName
    topic: str = Field(min_length=3, max_length=280)
    source: Optional[Source] = None
    beats: list[Beat] = Field(min_length=4, max_length=24)

    @field_validator("scene", mode="before")
    @classmethod
    def coerce_scene(cls, value: Any) -> Any:
        return _coerce_enum(value, _VALID_SCENES, {}, "living_room")


class RenderedBeat(Beat):
    audio: str
    duration_sec: float = Field(gt=0)


class NowPlaying(BaseModel):
    episode_id: int
    scene: SceneName
    topic: str
    beats: list[RenderedBeat] = Field(min_length=4, max_length=24)


class SelectorChoice(BaseModel):
    source: Literal["viewer", "autonomous"]
    topic: str = Field(min_length=3, max_length=280)
    reason: str = ""


class MemoryRecord(BaseModel):
    character: Optional[Speaker] = None
    fact: str = Field(min_length=1, max_length=500)
    importance: float = Field(ge=0.0, le=1.0, default=0.5)
    characters: list[str] = Field(default_factory=list)


class RelationshipChange(BaseModel):
    a: Speaker
    b: Speaker
    delta_trust: float = 0.0
    delta_tension: float = 0.0


class PreferenceDelta(BaseModel):
    character: Speaker
    key: str
    delta: float


class CharacterArc(BaseModel):
    character: Speaker
    note: str = Field(min_length=1, max_length=280)


class Condensation(BaseModel):
    new_memories: list[MemoryRecord] = Field(default_factory=list)
    relationship_changes: list[RelationshipChange] = Field(default_factory=list)
    preference_deltas: list[PreferenceDelta] = Field(default_factory=list)
    new_running_gags: list[str] = Field(default_factory=list)
    resolved_threads: list[str] = Field(default_factory=list)
    character_arcs: list[CharacterArc] = Field(default_factory=list)


def validate_scene(payload: dict[str, Any]) -> Scene:
    """Validate scene JSON against the show schema. Raises ValidationError on failure."""
    return Scene.model_validate(payload)


def scene_to_dict(scene: Scene) -> dict[str, Any]:
    return scene.model_dump()
