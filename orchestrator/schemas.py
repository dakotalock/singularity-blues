"""Pydantic models matching prompts/scene.schema.json plus the Godot sidecar packet."""

from __future__ import annotations

from typing import Any, Literal, Optional

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
SceneName = Literal["living_room", "kitchen", "front_yard"]
Source = Literal["viewer", "autonomous", "seed"]


class Beat(BaseModel):
    speaker: Speaker
    line: str = Field(min_length=1, max_length=280)
    emotion: Emotion
    animation: Animation
    target: Optional[Speaker] = None
    camera: Camera = "auto"

    @field_validator("target", mode="before")
    @classmethod
    def empty_target_to_none(cls, value: Any) -> Any:
        if value == "" or value == "null":
            return None
        return value


class Scene(BaseModel):
    scene: SceneName
    topic: str = Field(min_length=3, max_length=280)
    source: Optional[Source] = None
    beats: list[Beat] = Field(min_length=4, max_length=24)


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


class Condensation(BaseModel):
    new_memories: list[MemoryRecord] = Field(default_factory=list)
    relationship_changes: list[RelationshipChange] = Field(default_factory=list)
    preference_deltas: list[PreferenceDelta] = Field(default_factory=list)
    new_running_gags: list[str] = Field(default_factory=list)
    resolved_threads: list[str] = Field(default_factory=list)


def validate_scene(payload: dict[str, Any]) -> Scene:
    """Validate scene JSON against the show schema. Raises ValidationError on failure."""
    return Scene.model_validate(payload)


def scene_to_dict(scene: Scene) -> dict[str, Any]:
    return scene.model_dump()
