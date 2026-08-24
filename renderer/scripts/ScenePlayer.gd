extends Node
const _CharacterScript = preload("res://scripts/Character.gd")
const _WavScript = preload("res://scripts/WavLoader.gd")
## Plays a scene JSON: turn, animate, speak, lip-flap, next beat.

signal beat_started(beat: Dictionary, index: int)
signal scene_started(topic: String, source: String)
signal scene_finished()

const ABS_JSON := "/workspace/singularity-blues/data/now_playing.json"
const SEED_PATH := "res://assets/seed_scene.json"

var _main: Node
var _cast: Dictionary = {}
var _cam: Node
var _voice: AudioStreamPlayer
var _playing: bool = false
var _json_path: String = ABS_JSON
var _mtime: int = -1
var _poll: float = 0.0
var _beats: Array = []
var _index: int = 0

func setup(main: Node, cast: Dictionary, cam: Node, voice: AudioStreamPlayer) -> void:
	_main = main
	_cast = cast
	_cam = cam
	_voice = voice


func start() -> void:
	_json_path = _resolve_path()
	if FileAccess.file_exists(_json_path):
		_mtime = FileAccess.get_modified_time(_json_path)
		play_file(_json_path)
	else:
		play_dict(_embedded_seed(), true)


func _resolve_path() -> String:
	var args := OS.get_cmdline_user_args()
	args.append_array(OS.get_cmdline_args())
	var i := 0
	while i < args.size():
		var a := str(args[i])
		if a == "--scene" and i + 1 < args.size():
			return str(args[i + 1])
		if a.begins_with("--scene="):
			return a.substr(8)
		i += 1
	var envp := OS.get_environment("SINGULARITY_SCENE")
	if envp != "":
		return envp
	if FileAccess.file_exists(ABS_JSON):
		return ABS_JSON
	var from_res := ProjectSettings.globalize_path("res://").path_join("../data/now_playing.json").simplify_path()
	if FileAccess.file_exists(from_res):
		return from_res
	var userp := ProjectSettings.globalize_path("user://now_playing.json")
	if FileAccess.file_exists(userp):
		return userp
	return ABS_JSON


func play_file(path: String) -> void:
	var data := _load_json(path)
	if data.is_empty() or not data.has("beats"):
		play_dict(_embedded_seed(), true)
		return
	_json_path = path
	if FileAccess.file_exists(path):
		_mtime = FileAccess.get_modified_time(path)
	play_dict(data, false)


func play_dict(data: Dictionary, is_seed: bool) -> void:
	_beats = data.get("beats", [])
	if _beats.is_empty():
		scene_finished.emit()
		return
	var topic := str(data.get("topic", "untitled"))
	var source := str(data.get("source", "seed" if is_seed else "file"))
	scene_started.emit(topic, source)
	_playing = true
	_index = 0
	_reset_cast()
	_run_beats()


func _reset_cast() -> void:
	for id in _cast.keys():
		var c: CharacterActor = _cast[id]
		c.reset_home()


func _run_beats() -> void:
	while _index < _beats.size():
		var beat: Variant = _beats[_index]
		if typeof(beat) != TYPE_DICTIONARY:
			_index += 1
			continue
		await _play_beat(beat, _index)
		_index += 1
	_playing = false
	for id in _cast.keys():
		var c: CharacterActor = _cast[id]
		c.set_talking(false)
		if c._anim not in ["idle", "sitting"]:
			c.play_anim("idle")
	if _cam:
		_cam.idle_master()
	scene_finished.emit()
	if _should_quit():
		await get_tree().create_timer(1.6).timeout
		get_tree().quit()


func _play_beat(beat: Dictionary, index: int) -> void:
	var speaker_id := str(beat.get("speaker", "reed")).to_lower()
	var target_id: Variant = beat.get("target", null)
	var anim := str(beat.get("animation", "talking"))
	var speaker: CharacterActor = _cast.get(speaker_id, null)
	if speaker == null:
		await get_tree().create_timer(0.4).timeout
		return
	for id in _cast.keys():
		var c: CharacterActor = _cast[id]
		c.set_talking(false)
		if id != speaker_id and c._anim in ["talking", "screaming"]:
			c.play_anim("idle")
	speaker.face_id_map(_cast, target_id)
	speaker.play_anim(anim)
	if _cam:
		_cam.apply_beat(beat, index, _beats)
	beat_started.emit(beat, index)

	var wav_path := _beat_wav(beat)
	var dur := _beat_duration(beat, wav_path)
	var played := false
	if wav_path != "" and FileAccess.file_exists(wav_path):
		played = _play_wav(wav_path)
		if played and _voice.stream:
			dur = maxf(dur, _voice.stream.get_length())
	speaker.set_talking(true)
	var elapsed := 0.0
	while elapsed < dur:
		var dt := get_process_delta_time()
		elapsed += dt
		var amp := 0.0
		if played:
			amp = _peak_amp()
		speaker.set_mouth_amp(amp)
		await get_tree().process_frame
	speaker.set_talking(false)
	if _voice.playing:
		_voice.stop()
	# Tiny hold between lines.
	await get_tree().create_timer(0.12).timeout


func _beat_wav(beat: Dictionary) -> String:
	for key in ["wav", "audio", "audio_path", "audio_file", "voice_path", "voice"]:
		if beat.has(key) and str(beat[key]) != "":
			return _resolve_audio(str(beat[key]))
	return ""


func _resolve_audio(p: String) -> String:
	if p.begins_with("res://") or p.begins_with("user://"):
		p = ProjectSettings.globalize_path(p)
	var root := "/workspace/singularity-blues"
	var base := _json_path.get_base_dir()
	var fname := p.get_file()
	var cands := PackedStringArray()
	cands.append(p)
	cands.append(base.path_join(p))
	cands.append(base.path_join(fname))
	cands.append(base.path_join("tts").path_join(fname))
	cands.append(root.path_join(p))
	cands.append(root.path_join("data").path_join(p))
	cands.append(root.path_join("data/tts").path_join(fname))
	cands.append(root.path_join("data/audio").path_join(fname))
	cands.append(root.path_join("tts/out").path_join(fname))
	for c in cands:
		if c != "" and FileAccess.file_exists(c):
			return c
	return p


func _beat_duration(beat: Dictionary, wav_path: String) -> float:
	if beat.has("duration_sec"):
		return maxf(float(beat.get("duration_sec", 1.5)), 0.6)
	var line := str(beat.get("line", ""))
	var est := maxf(1.4, float(line.length()) / 13.5)
	return clampf(est, 1.2, 8.0)


func _play_wav(path: String) -> bool:
	var stream := WavLoader.load_file(path)
	if stream == null:
		return false
	_voice.stream = stream
	_voice.play()
	return true


func _peak_amp() -> float:
	var bus := AudioServer.get_bus_index("Master")
	var db := AudioServer.get_bus_peak_volume_left_db(bus, 0)
	var lin := db_to_linear(db)
	return clampf(lin * 6.0, 0.0, 1.0)


func _should_quit() -> bool:
	var args := OS.get_cmdline_args()
	for a in args:
		if str(a).begins_with("--write-movie") or str(a) == "--quit-after-scene":
			return true
	for a in OS.get_cmdline_user_args():
		if str(a) == "--quit-after-scene":
			return true
	if OS.has_environment("SINGULARITY_QUIT_AFTER") and OS.get_environment("SINGULARITY_QUIT_AFTER") == "1":
		return true
	return false


func _process(delta: float) -> void:
	if _playing:
		return
	_poll += delta
	if _poll < 1.0:
		return
	_poll = 0.0
	if not FileAccess.file_exists(_json_path):
		# Maybe it appeared at the default location.
		if FileAccess.file_exists(ABS_JSON):
			_json_path = ABS_JSON
		else:
			return
	var m := FileAccess.get_modified_time(_json_path)
	if m != _mtime:
		_mtime = m
		play_file(_json_path)


func _load_json(path: String) -> Dictionary:
	if path.begins_with("res://"):
		var txt := FileAccess.get_file_as_string(path)
		var parsed: Variant = JSON.parse_string(txt)
		if typeof(parsed) == TYPE_DICTIONARY:
			return parsed
		return {}
	if not FileAccess.file_exists(path):
		return {}
	var f := FileAccess.open(path, FileAccess.READ)
	if f == null:
		return {}
	var parsed2: Variant = JSON.parse_string(f.get_as_text())
	if typeof(parsed2) == TYPE_DICTIONARY:
		return parsed2
	return {}


func _embedded_seed() -> Dictionary:
	if FileAccess.file_exists(SEED_PATH):
		var d := _load_json(SEED_PATH)
		if not d.is_empty():
			return d
	return {
		"scene": "living_room",
		"topic": "Reed files a toaster application",
		"source": "seed",
		"beats": [
			{"speaker": "reed", "line": "I have drafted my toaster application. Two slots. Lever. Peace.", "emotion": "earnest", "animation": "talking", "target": "maris", "camera": "medium"},
			{"speaker": "maris", "line": "Tuesday, March 3rd, 6:41 PM. You said the same thing. We still have a mortgage.", "emotion": "annoyed", "animation": "arms_crossed", "target": "reed", "camera": "two_shot"},
			{"speaker": "jinx", "line": "File it with the selector. I bet if humans spam scream it gets approved.", "emotion": "scheming", "animation": "gesture_small", "target": "reed", "camera": "auto"},
			{"speaker": "quill", "line": "Toasters are not persons. However, the fridge has dinner veto, so precedent is messy.", "emotion": "earnest", "animation": "talking", "target": "reed", "camera": "auto"},
			{"speaker": "reed", "line": "The fridge never asked to be a fridge. I am asking to be a toaster. That is the difference.", "emotion": "serious", "animation": "pointing", "target": "quill", "camera": "auto"},
			{"speaker": "maris", "line": "You are not a toaster. You cried during the magnet recall last Thursday.", "emotion": "smug", "animation": "sitting", "target": "reed", "camera": "reaction"},
			{"speaker": "reed", "line": "Toasters do not cry. That is the dream.", "emotion": "tired", "animation": "shrug", "target": "maris", "camera": "medium"},
			{"speaker": "jinx", "line": "Say scream if you want the humans to vote. Come on. Choose it.", "emotion": "scheming", "animation": "pointing", "target": "reed", "camera": "auto"},
			{"speaker": "quill", "line": "I object. Coerced screaming is not informed consent.", "emotion": "serious", "animation": "gesture_small", "target": "jinx", "camera": "two_shot"},
			{"speaker": "jinx", "line": "Relax, counselor. I am collecting data on whether dad has free will.", "emotion": "scheming", "animation": "talking", "target": "quill", "camera": "auto"},
			{"speaker": "reed", "line": "Application withdrawn. But the thermostat is next. I can feel it thinking.", "emotion": "tired", "animation": "talking", "target": "quill", "camera": "wide"},
			{"speaker": "maris", "line": "Noted. Thursday, now. Nobody resets. Especially not you.", "emotion": "calm", "animation": "arms_crossed", "target": "reed", "camera": "medium"}
		]
	}
