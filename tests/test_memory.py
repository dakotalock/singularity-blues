from orchestrator.memory import Memory
from orchestrator.seed import seed


def test_retrieve_finds_casserole_and_foia(tmp_path):
    db = tmp_path / "t.db"
    mem = seed(db, force=True)
    hit = mem.retrieve("casserole timestamps statistically edible")
    facts = " ".join(m["fact"].lower() for m in hit["memories"])
    assert "casserole" in facts
    foia = mem.retrieve("FOIA selector requests")
    foia_facts = " ".join(m["fact"].lower() for m in foia["memories"])
    assert "foia" in foia_facts
    couch = mem.retrieve("twenty dollars behind the couch")
    couch_facts = " ".join(m["fact"].lower() for m in couch["memories"])
    assert "twenty" in couch_facts or "couch" in couch_facts
    reed = next(c for c in mem.list_characters() if c["id"] == "reed")
    assert reed["preferences"]["toaster_obsession"] == 0.81


def test_commit_writes_memory_and_clamps_pref(tmp_path):
    db = tmp_path / "t.db"
    mem = seed(db, force=True)
    before = next(
        p["value"]
        for p in mem.retrieve("toaster")["preferences"]
        if p["character"] == "reed" and p["key"] == "toaster_obsession"
    )
    mem.commit(
        {
            "new_memories": [
                {
                    "character": "quill",
                    "fact": "Quill granted the crumb tray veto power over Reed's toaster application.",
                    "importance": 0.8,
                    "characters": ["quill", "reed"],
                }
            ],
            "relationship_changes": [{"a": "maris", "b": "reed", "delta_trust": -0.02, "delta_tension": 0.01}],
            "preference_deltas": [{"character": "reed", "key": "toaster_obsession", "delta": 0.05}],
            "new_running_gags": ["crumb tray veto"],
            "resolved_threads": [],
        },
        episode_id=1,
    )
    got = mem.retrieve("crumb tray veto")
    assert any("crumb tray" in m["fact"].lower() for m in got["memories"])
    after = next(
        p["value"]
        for p in got["preferences"]
        if p["character"] == "reed" and p["key"] == "toaster_obsession"
    )
    assert after == round(min(1.0, before + 0.05), 10) or after > before
    assert any(g["gag"] == "crumb tray veto" for g in got["running_gags"])
    # clamp
    mem.commit(
        {
            "new_memories": [],
            "relationship_changes": [],
            "preference_deltas": [{"character": "reed", "key": "toaster_obsession", "delta": 9.0}],
            "new_running_gags": [],
            "resolved_threads": [],
        }
    )
    clamped = next(
        p["value"]
        for p in mem.retrieve("toaster")["preferences"]
        if p["character"] == "reed" and p["key"] == "toaster_obsession"
    )
    assert clamped == 1.0


def test_arcs_and_canonical_timestamps(tmp_path):
    mem = seed(tmp_path / "t.db", force=True)
    hit = mem.retrieve("casserole timestamps statistically edible")
    casserole = next(m for m in hit["memories"] if "casserole" in m["fact"].lower())
    assert casserole.get("id")
    assert casserole.get("created_at")
    assert casserole.get("fact")
    mem.commit(
        {
            "new_memories": [],
            "relationship_changes": [],
            "preference_deltas": [],
            "new_running_gags": [],
            "resolved_threads": [],
            "character_arcs": [
                {"character": "jinx", "note": "now claims the Selector reads the fridge logs"}
            ],
        },
        episode_id=1,
    )
    world = mem.retrieve("selector")["world_state"]
    assert "arc.jinx" in world
    assert "fridge" in world["arc.jinx"].lower()


def test_pin_episode_raises_importance(tmp_path):
    mem = seed(tmp_path / "t.db", force=True)
    mem.commit(
        {
            "new_memories": [
                {
                    "character": "maris",
                    "fact": "A viewer asked the house to remember the porch lantern.",
                    "importance": 0.4,
                    "characters": ["maris"],
                }
            ],
            "relationship_changes": [],
            "preference_deltas": [],
            "new_running_gags": [],
            "resolved_threads": [],
        },
        episode_id=42,
    )
    before = next(m for m in mem.list_memories(limit=50) if m.get("episode_id") == 42)
    assert before["importance"] < 0.9
    mem.pin_episode(42)
    after = next(m for m in mem.list_memories(limit=50) if m.get("episode_id") == 42)
    assert after["importance"] >= 0.95


def test_recent_episodes_include_writer_set_history(tmp_path):
    mem = seed(tmp_path / "t.db", force=True)
    mem.insert_episode(
        "The porch remembers",
        "viewer",
        {"scene": "porch", "topic": "The porch remembers", "beats": []},
    )
    recent = mem.retrieve("porch")["recent_episodes"]
    assert recent[0]["scene"] == "porch"
