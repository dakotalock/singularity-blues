extends Node3D
## Wires the designed set, four Blue actors, authored staging, cameras, HUD, and
## sidecar player. Broadcast UI is deliberately screen-space and phone-readable.

const SPEAKER_COLORS := {
	"reed": Color(0.45, 0.70, 0.96),
	"maris": Color(0.42, 0.82, 0.94),
	"jinx": Color(0.40, 0.88, 0.84),
	"quill": Color(0.64, 0.82, 1.00),
}

var _cast: Dictionary = {}
var _subtitle: Label
var _speaker_label: Label
var _topic_label: Label
var _caption_style: StyleBoxFlat
var _capture_dir := ""


func _ready() -> void:
	_capture_dir = OS.get_environment("SINGULARITY_CAPTURE_DIR")
	_make_hud()
	_spawn_cast()
	var staging: Node = $StagingDirector
	staging.setup(_cast, $LivingRoom)
	var camera_director: Node = $CameraDirector
	camera_director.setup(_cast, staging)
	var player: Node = $ScenePlayer
	player.setup(self, _cast, camera_director, $ScenePlayer/Voice, staging)
	player.beat_started.connect(_on_beat)
	player.scene_started.connect(_on_scene_started)
	player.scene_finished.connect(_on_scene_finished)
	_save_still_after("pilot.png", 1.0)
	player.start()


func _spawn_cast() -> void:
	var holder: Node3D = $Cast
	for id in ["reed", "maris", "jinx", "quill"]:
		var actor := CharacterActor.make(id)
		holder.add_child(actor)
		_cast[id] = actor


func _make_hud() -> void:
	var hud: CanvasLayer = $HUD

	var top := PanelContainer.new()
	top.name = "ShowHeader"
	top.mouse_filter = Control.MOUSE_FILTER_IGNORE
	top.anchor_right = 1.0
	top.offset_left = 18.0
	top.offset_top = 14.0
	top.offset_right = -18.0
	top.offset_bottom = 64.0
	var top_style := StyleBoxFlat.new()
	top_style.bg_color = Color(0.055, 0.065, 0.085, 0.90)
	top_style.border_color = Color(1.0, 0.80, 0.42, 0.30)
	top_style.border_width_bottom = 1
	_set_corners(top_style, 12)
	top.add_theme_stylebox_override("panel", top_style)
	hud.add_child(top)

	var top_margin := MarginContainer.new()
	top_margin.add_theme_constant_override("margin_left", 18)
	top_margin.add_theme_constant_override("margin_right", 18)
	top_margin.add_theme_constant_override("margin_top", 7)
	top_margin.add_theme_constant_override("margin_bottom", 7)
	top.add_child(top_margin)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 16)
	top_margin.add_child(row)

	var live := Label.new()
	live.text = "●  LIVE"
	live.add_theme_font_size_override("font_size", 17)
	live.add_theme_color_override("font_color", Color(1.0, 0.30, 0.29))
	live.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	row.add_child(live)

	var title := Label.new()
	title.text = "THE SINGULARITY BLUES"
	title.add_theme_font_size_override("font_size", 20)
	title.add_theme_color_override("font_color", Color(0.78, 0.90, 1.0))
	title.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	row.add_child(title)

	var divider := VSeparator.new()
	divider.custom_minimum_size.x = 1.0
	row.add_child(divider)

	_topic_label = Label.new()
	_topic_label.text = ""
	_topic_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_topic_label.add_theme_font_size_override("font_size", 17)
	_topic_label.add_theme_color_override("font_color", Color(1.0, 0.84, 0.55))
	_topic_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	_topic_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	row.add_child(_topic_label)

	var caption := PanelContainer.new()
	caption.name = "DialogueCaption"
	caption.mouse_filter = Control.MOUSE_FILTER_IGNORE
	caption.anchor_left = 0.045
	caption.anchor_right = 0.955
	caption.anchor_top = 1.0
	caption.anchor_bottom = 1.0
	caption.offset_top = -142.0
	caption.offset_bottom = -22.0
	_caption_style = StyleBoxFlat.new()
	_caption_style.bg_color = Color(0.035, 0.045, 0.065, 0.91)
	_caption_style.border_color = SPEAKER_COLORS["reed"]
	_caption_style.border_width_left = 5
	_caption_style.shadow_color = Color(0.0, 0.0, 0.0, 0.34)
	_caption_style.shadow_size = 8
	_caption_style.shadow_offset = Vector2(0, 3)
	_set_corners(_caption_style, 14)
	caption.add_theme_stylebox_override("panel", _caption_style)
	hud.add_child(caption)

	var cap_margin := MarginContainer.new()
	cap_margin.add_theme_constant_override("margin_left", 22)
	cap_margin.add_theme_constant_override("margin_right", 22)
	cap_margin.add_theme_constant_override("margin_top", 13)
	cap_margin.add_theme_constant_override("margin_bottom", 13)
	caption.add_child(cap_margin)
	var copy := VBoxContainer.new()
	copy.add_theme_constant_override("separation", 4)
	cap_margin.add_child(copy)

	_speaker_label = Label.new()
	_speaker_label.add_theme_font_size_override("font_size", 17)
	_speaker_label.add_theme_color_override("font_color", SPEAKER_COLORS["reed"])
	copy.add_child(_speaker_label)

	_subtitle = Label.new()
	_subtitle.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_subtitle.add_theme_font_size_override("font_size", 24)
	_subtitle.add_theme_color_override("font_color", Color(0.985, 0.97, 0.93))
	_subtitle.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_subtitle.vertical_alignment = VERTICAL_ALIGNMENT_TOP
	_subtitle.max_lines_visible = 3
	_subtitle.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	copy.add_child(_subtitle)


func _set_corners(style: StyleBoxFlat, radius: int) -> void:
	style.corner_radius_top_left = radius
	style.corner_radius_top_right = radius
	style.corner_radius_bottom_left = radius
	style.corner_radius_bottom_right = radius


func _on_scene_started(topic: String, _source: String) -> void:
	_topic_label.text = topic
	_subtitle.text = ""
	_speaker_label.text = ""


func _on_beat(beat: Dictionary, index: int) -> void:
	var speaker_id := str(beat.get("speaker", "reed")).to_lower()
	_speaker_label.text = speaker_id.to_upper()
	_subtitle.text = str(beat.get("line", ""))
	var accent: Color = SPEAKER_COLORS.get(speaker_id, SPEAKER_COLORS["reed"])
	_speaker_label.add_theme_color_override("font_color", accent)
	_caption_style.border_color = accent
	if _capture_dir != "":
		_save_still_after("beat_%02d_%s.png" % [index, speaker_id], 0.16)


func _on_scene_finished() -> void:
	_speaker_label.text = ""
	_subtitle.text = ""
	if _capture_dir != "":
		_save_still_after("scene_end.png", 0.12)


func _save_still_after(filename: String, delay: float) -> void:
	await get_tree().create_timer(delay).timeout
	await RenderingServer.frame_post_draw
	var texture := get_viewport().get_texture()
	if texture == null:
		return
	var image := texture.get_image()
	if image == null:
		return
	var directory := _capture_dir if _capture_dir != "" else _default_data_dir()
	DirAccess.make_dir_recursive_absolute(directory)
	var error := image.save_png(directory.path_join(filename))
	if error != OK:
		var fallback := ProjectSettings.globalize_path("user://").path_join(filename)
		image.save_png(fallback)


func _default_data_dir() -> String:
	return ProjectSettings.globalize_path("res://").path_join("../data").simplify_path()
