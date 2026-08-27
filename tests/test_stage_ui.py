from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_player_exposes_clear_sound_and_fullscreen_controls():
    html = (ROOT / "web" / "stage" / "index.html").read_text(encoding="utf-8")
    assert 'id="sitcom-volume"' in html
    assert "Muted — tap for sound" in html
    assert "GodotAudio.ctx" in html
    assert ".resume()" in html
    assert 'id="sitcom-fullscreen"' in html
    assert "requestFullscreen" in html
    assert "Exit full screen" in html
    assert "player-expanded" in html
    assert "body.broadcast #player-controls" in html


def test_renderer_defines_every_writer_set():
    stage = (ROOT / "renderer" / "scripts" / "LivingRoom.gd").read_text(encoding="utf-8")
    for group in ("SetKitchen", "SetHallway", "SetPorch", "SetFrontYard"):
        assert group in stage
    writer = (ROOT / "prompts" / "writer.md").read_text(encoding="utf-8")
    for scene in ("living_room", "kitchen", "hallway", "porch", "front_yard"):
        assert scene in writer
