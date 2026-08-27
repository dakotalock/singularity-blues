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
    assert "document.body.classList.contains('broadcast')" in html
    assert "setInterval(() => setAudioEnabled(true), 2000)" in html


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


def test_mobile_controls_scroll_without_moving_the_player():
    html = (ROOT / "web" / "stage" / "index.html").read_text(encoding="utf-8")
    assert "#sitcom-chrome {" in html
    assert "overflow-y: auto" in html
    assert "touch-action: pan-y" in html
    assert "#player-shell {" in html and "touch-action: none" in html
    assert "max-height: min(52dvh, 520px)" in html
    assert 'id="sitcom-chrome-inner"' in html


def test_secondary_tools_use_compact_disclosure_panels():
    html = (ROOT / "web" / "stage" / "index.html").read_text(encoding="utf-8")
    for control in ("sitcom-buy-toggle", "sitcom-queue-toggle", "sitcom-storage-toggle"):
        assert f'id="{control}"' in html
    assert "const panelPairs = [" in html
    assert "activePanel.scrollIntoView" in html
    assert 'id="sitcom-recovery-copy"' in html



def test_private_showing_copy_and_control():
    html = (ROOT / "web" / "stage" / "index.html").read_text(encoding="utf-8")
    assert "Private Showing" in html
    assert 'id="sitcom-private"' in html
    assert "saved to the library and memory" in html.lower()
    assert "without waiting on others" in html.lower()
    assert "Ask the Selector" in html
    assert "Gemini" not in html
    assert "Piper" not in html
    assert "gemini-3.7" not in html
    assert '"index.pck":130512' in html
    assert "#sitcom-chrome {" in html
    assert "overflow-y: auto" in html
    assert "touch-action: pan-y" in html
    assert "max-height: min(52dvh, 520px)" in html
    assert "body.broadcast #player-controls" in html
    assert "private_showing" in html
