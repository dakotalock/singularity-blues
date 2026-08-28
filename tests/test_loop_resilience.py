from orchestrator import loop


def test_bad_remote_condenser_falls_back_after_voice(monkeypatch):
    committed = []

    class BrokenCondenser:
        def condense(self, scene):
            raise ValueError("malformed condenser JSON")

    class Memory:
        def commit(self, condensation, episode_id=None):
            committed.append((condensation, episode_id))

    monkeypatch.setattr(loop, "get_condenser", lambda: BrokenCondenser())
    scene = {
        "scene": "living_room",
        "topic": "the completed episode",
        "source": "viewer",
        "beats": [
            {"speaker": "reed", "line": "The voice work is already done."},
            {"speaker": "maris", "line": "Then it counts."},
        ],
    }

    loop._remember_episode(Memory(), scene, 44)

    assert len(committed) == 1
    condensation, episode_id = committed[0]
    assert episode_id == 44
    assert condensation["new_memories"]
    assert any("completed episode" in item["fact"] for item in condensation["new_memories"])
