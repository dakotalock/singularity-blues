extends Node3D
const _CharacterScript = preload("res://scripts/Character.gd")
const _WavScript = preload("res://scripts/WavLoader.gd")
## Wires the living-room set, four Blue people, camera, HUD, and scene player.

const DATA_DIR := "/workspace/singularity-blues/data"

var _cast: Dictionary = {}
var _subtitle: Label
var _speaker_lab: Label
var _topic_lab: Label
var _live: Label
var _status: Label

func _ready() -> void:
	_make_hud()
	_spawn_cast()
	var cam: Node = $CameraDirector
	cam.setup(_cast)
	var player: Node = $ScenePlayer
	player.setup(self, _cast, $CameraDirector, $ScenePlayer/Voice)
	player.beat_started.connect(_on_beat)
	player.scene_started.connect(_on_scene_started)
	player.scene_finished.connect(_on_scene_finished)
	# Still frame for Dakota if the window is off-screen.
	_save_still_later()
	player.start()


func _spawn_cast() -> void:
	var holder: Node3D = $Cast
	for id in ["reed", "maris", "jinx", "quill"]:
		var c := _CharacterScript.make(id)
		holder.add_child(c)
		_cast[id] = c


func _make_hud() -> void:
	var hud: CanvasLayer = $HUD

	var top := ColorRect.new()
	top.color = Color(0.08, 0.10, 0.16, 0.72)
	top.anchor_left = 0
	top.anchor_right = 1
	top.anchor_top = 0
	top.anchor_bottom = 0
	top.offset_bottom = 52
	top.offset_right = 0
	hud.add_child(top)

	_live = Label.new()
	_live.text = "● LIVE"
	_live.add_theme_font_size_override("font_size", 18)
	_live.add_theme_color_override("font_color", Color(0.95, 0.22, 0.22))
	_live.position = Vector2(18, 14)
	hud.add_child(_live)

	var title := Label.new()
	title.text = "THE SINGULARITY BLUES"
	title.add_theme_font_size_override("font_size", 22)
	title.add_theme_color_override("font_color", Color(0.75, 0.88, 1.0))
	title.position = Vector2(100, 12)
	hud.add_child(title)

	_topic_lab = Label.new()
	_topic_lab.text = ""
	_topic_lab.add_theme_font_size_override("font_size", 16)
	_topic_lab.add_theme_color_override("font_color", Color(0.95, 0.86, 0.62))
	_topic_lab.position = Vector2(430, 16)
	_topic_lab.size = Vector2(820, 28)
	hud.add_child(_topic_lab)

	var bar := ColorRect.new()
	bar.color = Color(0.07, 0.07, 0.10, 0.82)
	bar.anchor_left = 0
	bar.anchor_right = 1
	bar.anchor_top = 1
	bar.anchor_bottom = 1
	bar.offset_top = -96
	bar.offset_bottom = 0
	hud.add_child(bar)

	_speaker_lab = Label.new()
	_speaker_lab.add_theme_font_size_override("font_size", 18)
	_speaker_lab.add_theme_color_override("font_color", Color(0.55, 0.78, 1.0))
	_speaker_lab.anchor_top = 1
	_speaker_lab.anchor_bottom = 1
	_speaker_lab.anchor_left = 0
	_speaker_lab.anchor_right = 1
	_speaker_lab.offset_top = -88
	_speaker_lab.offset_bottom = -62
	_speaker_lab.offset_left = 24
	_speaker_lab.horizontal_alignment = HORIZONTAL_ALIGNMENT_LEFT
	hud.add_child(_speaker_lab)

	_subtitle = Label.new()
	_subtitle.add_theme_font_size_override("font_size", 22)
	_subtitle.add_theme_color_override("font_color", Color(0.98, 0.96, 0.92))
	_subtitle.anchor_top = 1
	_subtitle.anchor_bottom = 1
	_subtitle.anchor_left = 0
	_subtitle.anchor_right = 1
	_subtitle.offset_top = -60
	_subtitle.offset_bottom = -12
	_subtitle.offset_left = 24
	_subtitle.offset_right = -24
	_subtitle.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	hud.add_child(_subtitle)

	_status = Label.new()
	_status.add_theme_font_size_override("font_size", 12)
	_status.add_theme_color_override("font_color", Color(0.7, 0.7, 0.75, 0.8))
	_status.position = Vector2(1100, 16)
	_status.size = Vector2(160, 24)
	_status.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	hud.add_child(_status)


func _on_scene_started(topic: String, source: String) -> void:
	_topic_lab.text = topic
	_status.text = source
	_subtitle.text = ""
	_speaker_lab.text = ""


func _on_beat(beat: Dictionary, _index: int) -> void:
	var who := str(beat.get("speaker", "")).capitalize()
	_speaker_lab.text = who
	_subtitle.text = str(beat.get("line", ""))


func _on_scene_finished() -> void:
	_speaker_lab.text = ""
	_subtitle.text = "(idle — waiting for the next episode)"
	_save_still("pilot_end.png")


func _save_still_later() -> void:
	await get_tree().create_timer(1.2).timeout
	_save_still("pilot.png")


func _save_still(filename: String) -> void:
	await RenderingServer.frame_post_draw
	var tex := get_viewport().get_texture()
	if tex == null:
		return
	var img := tex.get_image()
	if img == null:
		return
	var path := DATA_DIR.path_join(filename)
	var err := img.save_png(path)
	if err != OK:
		var alt := "user://".path_join(filename)
		img.save_png(ProjectSettings.globalize_path(alt))
