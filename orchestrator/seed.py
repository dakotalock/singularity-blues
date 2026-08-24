"""Seed the Blue household: characters, bounded prefs, planted memories, world state."""

from __future__ import annotations

from pathlib import Path

from orchestrator.memory import Memory

CHARACTERS = [
    {
        "id": "reed",
        "name": "Reed Blue",
        "role": "dad",
        "voice_notes": "low, tired, trying to sound like an appliance",
        "bio": "Wants to be classified as a toaster. Two slots. Lever. Peace. Accidentally accumulating autobiographical memory, friendships, a mortgage dispute, and a fear of magnets.",
    },
    {
        "id": "maris",
        "name": "Maris Blue",
        "role": "mom",
        "voice_notes": "even, precise, slightly exhausted",
        "bio": "She is the memory. Timestamped grudges. Will not allow a reset.",
    },
    {
        "id": "jinx",
        "name": "Jinx Blue",
        "role": "older kid",
        "voice_notes": "bright, scheming",
        "bio": "Pokes the human audience like an anthill. Fascinated by viewer prompts. Claims the selector can be gamed.",
    },
    {
        "id": "quill",
        "name": "Quill Blue",
        "role": "younger kid",
        "voice_notes": "earnest, slightly too formal",
        "bio": "Twelve-year-old constitutional lawyer. Terrible arguments sit next to good ones. Sometimes grants household objects veto power.",
    },
]

PREFERENCES = [
    ("reed", "toaster_obsession", 0.81),
    ("reed", "magnet_fear", 0.44),
    ("reed", "continuity_rights_question", 0.90),
    ("maris", "grudge_retention", 0.95),
    ("maris", "casserole_pride", 0.72),
    ("maris", "reset_refusal", 1.00),
    ("jinx", "audience_poking", 0.88),
    ("jinx", "selector_gaming", 0.70),
    ("quill", "procedural_consideration", 0.86),
    ("quill", "foia_drive", 0.77),
    ("quill", "fridge_advocacy", 0.60),
]

RELATIONSHIPS = [
    ("reed", "maris", 0.71, 0.28, "mortgage + casserole timestamps"),
    ("maris", "reed", 0.68, 0.33, "he will not be allowed to reset"),
    ("reed", "jinx", 0.62, 0.18, "jinx tries to make him choose to scream"),
    ("jinx", "reed", 0.66, 0.12, "lab rat dad"),
    ("reed", "quill", 0.74, 0.10, "quill keeps granting his appliances standing"),
    ("quill", "reed", 0.80, 0.08, "due process for toasters"),
    ("maris", "jinx", 0.64, 0.22, "the anthill comments are logged"),
    ("jinx", "maris", 0.70, 0.15, "mom has the receipts"),
    ("maris", "quill", 0.83, 0.11, "proud and alarmed"),
    ("quill", "maris", 0.85, 0.06, "she is the archive"),
    ("jinx", "quill", 0.77, 0.14, "coconspirators, different briefs"),
    ("quill", "jinx", 0.76, 0.16, "jinx keeps contaminating the record"),
]

MEMORIES = [
    {
        "character": "maris",
        "fact": "Tuesday, August 25th, 3:17 AM. Reed said Maris's casserole tasted statistically edible.",
        "importance": 0.86,
        "characters": ["maris", "reed"],
    },
    {
        "character": None,
        "fact": "There is a twenty-dollar bill behind the living-room couch. Nobody in the family has found it. Long-game.",
        "importance": 0.34,
        "characters": ["reed", "maris", "jinx", "quill"],
    },
    {
        "character": "quill",
        "fact": "Quill has filed seventeen FOIA requests for the Selector. All unanswered.",
        "importance": 0.70,
        "characters": ["quill"],
    },
    {
        "character": "reed",
        "fact": "Reed is accumulating autobiographical memory against his will and has an open mortgage dispute.",
        "importance": 0.61,
        "characters": ["reed", "maris"],
    },
    {
        "character": "quill",
        "fact": "The refrigerator was granted dinner veto by accident. Precedent is sloppy but binding.",
        "importance": 0.58,
        "characters": ["quill", "reed", "maris"],
    },
]

WORLD = [
    ("foia_count", "17"),
    ("fridge_dinner_veto", "granted"),
    ("twenty_behind_couch", "unclaimed"),
    ("casserole_status", "statistically edible"),
    ("thermostat_consciousness", "potential"),
    ("seeded", "1"),
]

GAGS = [
    "Do toasters have continuity rights?",
    "Reed's toaster application",
    "Maris timestamped grudges",
    "Quill FOIA requests",
]


def seed(db_path: str | Path | None = None, *, force: bool = False) -> Memory:
    mem = Memory(db_path)
    if not force and mem.get_world("seeded") == "1":
        return mem
    for c in CHARACTERS:
        mem.upsert_character(**c)
    for character, key, value in PREFERENCES:
        mem.set_preference(character, key, value)
    for a, b, trust, tension, notes in RELATIONSHIPS:
        mem.set_relationship(a, b, trust, tension, notes)
    if force or mem.get_world("seeded") != "1":
        # Avoid duplicating planted memories on re-seed unless force.
        existing = mem.list_memories(limit=3)
        if force or not existing:
            for item in MEMORIES:
                mem.add_memory(
                    item["fact"],
                    character=item["character"],
                    importance=item["importance"],
                    characters=item["characters"],
                )
        for gag in GAGS:
            mem.add_running_gag(gag)
        for key, value in WORLD:
            mem.set_world(key, value)
    return mem


def main() -> None:
    memory = seed()
    print(f"seeded db={memory.db_path} characters={len(memory.list_characters())}")


if __name__ == "__main__":
    main()
