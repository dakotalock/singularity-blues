from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_player_exposes_clear_sound_and_fullscreen_controls():
    html = (ROOT / "web" / "stage" / "index.html").read_text(encoding="utf-8")
    assert 'id="sitcom-volume"' in html
    assert 'data-state="muted"' in html
    assert 'aria-label="Unmute the show"' in html
    assert "🔇" in html
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


def test_scene_player_has_a_central_interruption_barrier():
    player = (ROOT / "renderer" / "scripts" / "ScenePlayer.gd").read_text(encoding="utf-8")
    assert "if _playing:\n\t\t_queue_pending_scene(data, is_seed)" in player
    assert "scene_finished.emit()\n\tif not _pending_scenes.is_empty()" in player
    assert "_packet_key(pending) == incoming_key" in player


def test_storage_mentions_recovery_key_and_restore():
    html = (ROOT / "web" / "stage" / "index.html").read_text(encoding="utf-8")
    lowered = html.lower()
    assert "recovery key" in lowered
    assert "restore" in lowered
    assert 'id="sitcom-recovery-key"' in html
    assert 'id="sitcom-recovery-input"' in html
    assert 'id="sitcom-recovery-restore"' in html
    assert "How prompts are stored" in html
    assert '"index.pck":130512' in html
