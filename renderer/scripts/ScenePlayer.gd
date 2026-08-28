extends Node
## Performs semantic scene beats: authored blocking, camera coverage, WAV speech,
## smoothed lip motion, event-sensitive pauses, and occasional silent reactions.
## On web, scenes load from same-origin /now-playing and the stage stays up.

signal beat_started(beat: Dictionary, index: int)
signal scene_started(topic: String, source: String)
signal scene_finished()

const ABS_JSON := "/workspace/singularity-blues/data/now_playing.json"
const SEED_PATH := "res://assets/seed_scene.json"

var _main: Node
var _cast: Dictionary = {}
var _cam: Node
var _staging: Node
var _voice: AudioStreamPlayer
var _playing := false
var _json_path := ABS_JSON
var _mtime := -1
var _poll := 0.0
var _beats: Array = []
var _index := 0
var _scene_name := "living_room"
var _last_episode_id := ""
var _web_polling := false
var _run_token := 0
var _pending_scenes: Array[Dictionary] = []
var _pending_seed_flags: Array[bool] = []


func setup(main: Node, cast: Dictionary, cam: Node, voice: AudioStreamPlayer, staging: Node = null) -> void:
	_main = main
	_cast = cast
	_cam = cam
	_voice = voice
	_staging = staging


func start() -> void:
	if _is_web():
		await _web_boot()
		return
	_json_path = _resolve_path()
	if FileAccess.file_exists(_json_path):
		_mtime = FileAccess.get_modified_time(_json_path)
		play_file(_json_path)
	else:
		play_dict(_embedded_seed(), true)


func _is_web() -> bool:
	return OS.has_feature("web")


func _origin() -> String:
	if not _is_web():
		return ""
	var from_query: Variant = JavaScriptBridge.eval("new URLSearchParams(window.location.search).get('api')")
	var qs := str(from_query)
	if qs.begins_with("http"):
		return qs
	var value: Variant = JavaScriptBridge.eval("window.location.origin")
	var origin := str(value)
	if origin.begins_with("http"):
		return origin
	return ""


func _api_url(path: String) -> String:
	var origin := _origin()
	if path.begins_with("http://") or path.begins_with("https://"):
		return path
	if origin == "":
		return path
	if path.begins_with("/"):
		return origin + path
	return origin + "/" + path


func _http_get(url: String) -> PackedByteArray:
	var http := HTTPRequest.new()
	add_child(http)
	http.timeout = 20.0
	var err := http.request(url)
	if err != OK:
		http.queue_free()
		return PackedByteArray()
	var finished: Array = await http.request_completed
	http.queue_free()
	if finished.size() < 4:
		return PackedByteArray()
	var code := int(finished[1])
	if code != 200:
		return PackedByteArray()
	return finished[3]


func _http_json(url: String) -> Dictionary:
	var body := await _http_get(url)
	if body.is_empty():
		return {}
	var parsed: Variant = JSON.parse_string(body.get_string_from_utf8())
	return parsed if typeof(parsed) == TYPE_DICTIONARY else {}


func _web_boot() -> void:
	var data := await _http_json(_api_url("/now-playing?player=1"))
	if data.is_empty() or not data.has("beats") or (data.get("beats", []) as Array).is_empty():
		play_dict(_embedded_seed(), true)
		return
	_last_episode_id = str(data.get("episode_id", ""))
	play_dict(data, false)


func _web_poll() -> void:
	if _playing:
		return
	if _web_polling:
		return
	_web_polling = true
	var data := await _http_json(_api_url("/now-playing?player=1"))
	_web_polling = false
	if _playing:
		return
	if data.is_empty():
		return
	var beats: Array = data.get("beats", [])
	if beats.is_empty():
		return
	var eid := str(data.get("episode_id", ""))
	if eid == "" or eid == _last_episode_id:
		return
	_last_episode_id = eid
	play_dict(data, false)


func _resolve_path() -> String:
	var args := OS.get_cmdline_user_args()
	args.append_array(OS.get_cmdline_args())
	var i := 0
	while i < args.size():
		var arg := str(args[i])
		if arg == "--scene" and i + 1 < args.size():
			return str(args[i + 1])
		if arg.begins_with("--scene="):
			return arg.substr(8)
		i += 1
	var env_path := OS.get_environment("SINGULARITY_SCENE")
	if env_path != "":
		return env_path
	if FileAccess.file_exists(ABS_JSON):
		return ABS_JSON
	var project_sidecar := _project_root().path_join("data/now_playing.json")
	if FileAccess.file_exists(project_sidecar):
		return project_sidecar
	var user_path := ProjectSettings.globalize_path("user://now_playing.json")
	if FileAccess.file_exists(user_path):
		return user_path
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
	# Central interruption barrier: callers may discover a new playlist packet at
	# any time, but an active performance owns the stage through its final beat.
	# Queue the packet here instead of relying on every polling/caller path to
	# remember the same guard.
	if _playing:
		_queue_pending_scene(data, is_seed)
		return
	_beats = data.get("beats", [])
	if _beats.is_empty():
		scene_finished.emit()
		return
	_scene_name = str(data.get("scene", "living_room"))
	var topic := str(data.get("topic", "untitled"))
	var source := str(data.get("source", "seed" if is_seed else "file"))
	if str(data.get("episode_id", "")) != "":
		_last_episode_id = str(data.get("episode_id", ""))
	scene_started.emit(topic, source)
	if _main != null and _main.has_node("LivingRoom"):
		var room: Node = _main.get_node("LivingRoom")
		if room.has_method("apply_setting"):
			room.apply_setting(_scene_name)
	_run_token += 1
	var token := _run_token
	_playing = true
	_index = 0
	_reset_cast()
	_run_beats(token)


func _queue_pending_scene(data: Dictionary, is_seed: bool) -> void:
	var beats: Array = data.get("beats", [])
	if beats.is_empty():
		return
	var incoming_id := str(data.get("episode_id", ""))
	if incoming_id != "" and incoming_id == _last_episode_id:
		return
	var incoming_key := _packet_key(data)
	for pending in _pending_scenes:
		if _packet_key(pending) == incoming_key:
			return
	_pending_scenes.append(data.duplicate(true))
	_pending_seed_flags.append(is_seed)


func _packet_key(data: Dictionary) -> String:
	var eid := str(data.get("episode_id", ""))
	if eid != "":
		return "episode:" + eid
	return "topic:" + str(data.get("topic", "")) + ":" + str((data.get("beats", []) as Array).size())


func _play_next_pending() -> void:
	if _playing or _pending_scenes.is_empty():
		return
	var data: Dictionary = _pending_scenes.pop_front()
	var is_seed := false
	if not _pending_seed_flags.is_empty():
		is_seed = _pending_seed_flags.pop_front()
	play_dict(data, is_seed)


func _reset_cast() -> void:
	if _staging != null and _staging.has_method("reset_cast"):
		_staging.reset_cast()
		return
	for id in _cast.keys():
		var actor: CharacterActor = _cast[id]
		actor.reset_home()


func _run_beats(token: int) -> void:
	while _index < _beats.size():
		if token != _run_token:
			return
		var beat: Variant = _beats[_index]
		if typeof(beat) != TYPE_DICTIONARY:
			_index += 1
			continue
		await _play_beat(beat, _index)
		if token != _run_token:
			return
		_index += 1
	if token != _run_token:
		return
	_playing = false
	for id in _cast.keys():
		var actor: CharacterActor = _cast[id]
		actor.set_talking(false)
		actor.set_expression("calm")
		if actor.has_method("current_animation"):
			if actor.current_animation() not in ["idle", "sitting"]:
				actor.play_anim("idle")
		else:
			actor.play_anim("idle")
	if _cam:
		_cam.idle_master()
	scene_finished.emit()
	if not _pending_scenes.is_empty():
		call_deferred("_play_next_pending")
		return
	if _is_web():
		_web_poll()
	if _should_quit():
		await get_tree().create_timer(0.8).timeout
		get_tree().quit()


func _play_beat(beat: Dictionary, index: int) -> void:
	var speaker_id := str(beat.get("speaker", "reed")).to_lower()
	var target_value: Variant = beat.get("target", null)
	var anim := str(beat.get("animation", "talking"))
	var emotion := str(beat.get("emotion", "calm"))
	var speaker: CharacterActor = _cast.get(speaker_id, null)
	if speaker == null:
		await get_tree().create_timer(0.25).timeout
		return

	for id in _cast.keys():
		var actor: CharacterActor = _cast[id]
		actor.set_talking(false)
		if str(id) != speaker_id and not actor.is_moving():
			actor.play_anim("idle")

	if _staging != null:
		_staging.prepare_beat(beat, index)
	else:
		speaker.face_id_map(_cast, target_value)
		speaker.set_expression(emotion)

	if anim in ["enter", "walking", "sitting"]:
		if _cam and _cam.has_method("movement_wide"):
			_cam.movement_wide(speaker)
		await _wait_for_motion(speaker, 2.8)
		if anim == "sitting":
			await get_tree().create_timer(0.20).timeout

	var performance_anim := anim
	if anim in ["enter", "walking", "leave"]:
		performance_anim = "talking"
	speaker.set_expression(emotion)
	speaker.set_talking(true)
	speaker.play_anim(performance_anim)
	if _cam:
		_cam.apply_beat(beat, index, _beats)
	beat_started.emit(beat, index)

	var wav_path := _beat_wav(beat)
	var duration := _beat_duration(beat, wav_path)
	var played := false
	if wav_path != "":
		if _is_web() or FileAccess.file_exists(wav_path):
			played = await _play_wav(wav_path)
			if played and _voice.stream:
				duration = maxf(duration, _voice.stream.get_length())
	var elapsed := 0.0
	var line := str(beat.get("line", ""))
	while elapsed < duration:
		var delta := get_process_delta_time()
		elapsed += delta
		var amp := _peak_amp() if played else _synthetic_amp(line, elapsed, duration)
		speaker.set_mouth_amp(amp)
		await get_tree().process_frame
	speaker.set_mouth_amp(0.0)
	speaker.set_talking(false)
	if _voice.playing:
		_voice.stop()

	if anim == "leave" and _staging != null:
		var leaving: CharacterActor = _staging.finish_beat(beat)
		if _cam and _cam.has_method("movement_wide"):
			_cam.movement_wide(leaving)
		await _wait_for_motion(leaving, 1.65)

	var hold := _hold_after(beat, index)
	if _wants_reaction(beat, index):
		var reaction: CharacterActor = null
		if _staging != null:
			reaction = _staging.reaction_actor(beat)
		elif target_value != null:
			reaction = _cast.get(str(target_value), null)
		if reaction != null and reaction != speaker:
			reaction.face_toward(speaker)
			if _cam and _cam.has_method("reaction_hold"):
				_cam.reaction_hold(reaction, speaker)
			await get_tree().create_timer(hold).timeout
			return
	await get_tree().create_timer(hold).timeout


func _wait_for_motion(actor: CharacterActor, max_seconds: float) -> void:
	if actor == null or not actor.has_method("is_moving"):
		return
	var elapsed := 0.0
	while actor.is_moving() and elapsed < max_seconds:
		var delta := get_process_delta_time()
		elapsed += delta
		await get_tree().process_frame


func _wants_reaction(beat: Dictionary, index: int) -> bool:
	var camera_request := str(beat.get("camera", "auto"))
	var emotion := str(beat.get("emotion", "calm"))
	var anim := str(beat.get("animation", "talking"))
	if camera_request == "reaction" or index == _beats.size() - 1:
		return true
	if emotion in ["shocked", "screaming", "confused", "embarrassed"] or anim in ["shocked", "screaming", "recoil", "double_take", "facepalm"]:
		return true
	if anim in ["laughing", "giggle", "high_five"] or emotion in ["delighted", "playful"]:
		return index % 2 == 1
	var line := str(beat.get("line", ""))
	return beat.get("target", null) != null and line.length() < 96 and emotion in ["smug", "scheming", "tired", "suspicious", "nervous"] and index % 3 == 1


func _hold_after(beat: Dictionary, index: int) -> float:
	var emotion := str(beat.get("emotion", "calm"))
	var anim := str(beat.get("animation", "talking"))
	var line := str(beat.get("line", ""))
	if emotion in ["shocked", "screaming"] or anim in ["shocked", "screaming", "recoil", "double_take"]:
		return 0.68
	if anim in ["facepalm", "shake_head", "thinking"]:
		return 0.48
	if anim in ["celebrate", "laughing", "happy_dance", "high_five", "victory_pose"]:
		return 0.58
	if str(beat.get("camera", "auto")) == "reaction":
		return 0.55
	if index == _beats.size() - 1:
		return 0.62
	if "..." in line:
		return 0.58
	if anim == "enter":
		return 0.34
	if line.ends_with("?"):
		return 0.28
	return 0.17


func _synthetic_amp(line: String, elapsed: float, duration: float) -> float:
	if elapsed < 0.09 or duration - elapsed < 0.11 or line.strip_edges() == "":
		return 0.0
	# Seed scenes have no WAV. A restrained, syllable-like envelope keeps the
	# fallback watchable without resurrecting the old high-frequency chatter.
	var cadence := 0.5 + 0.5 * sin(elapsed * 11.0 + float(line.length() % 7))
	var phrase_gap := fmod(elapsed + float(line.length() % 5) * 0.07, 0.82)
	if phrase_gap > 0.69:
		return 0.04
	return 0.18 + cadence * 0.56


func _beat_wav(beat: Dictionary) -> String:
	for key in ["wav", "audio", "audio_path", "audio_file", "voice_path", "voice"]:
		if beat.has(key) and str(beat[key]) != "":
			return _resolve_audio(str(beat[key]))
	return ""


func _resolve_audio(path: String) -> String:
	if _is_web():
		return path
	if path.begins_with("res://") or path.begins_with("user://"):
		path = ProjectSettings.globalize_path(path)
	var root := _project_root()
	var base := _json_path.get_base_dir()
	var filename := path.get_file()
	var candidates := PackedStringArray()
	candidates.append(path)
	candidates.append(base.path_join(path))
	candidates.append(base.path_join(filename))
	candidates.append(base.path_join("tts").path_join(filename))
	candidates.append(root.path_join(path))
	candidates.append(root.path_join("data").path_join(path))
	candidates.append(root.path_join("data/tts").path_join(filename))
	candidates.append(root.path_join("data/audio").path_join(filename))
	candidates.append(root.path_join("tts/out").path_join(filename))
	# Keep compatibility with the original container layout.
	candidates.append("/workspace/singularity-blues".path_join(path))
	candidates.append("/workspace/singularity-blues/data/tts".path_join(filename))
	for candidate in candidates:
		if candidate != "" and FileAccess.file_exists(candidate):
			return candidate
	return path


func _audio_url(path: String) -> String:
	if path.begins_with("http://") or path.begins_with("https://"):
		return path
	if path.begins_with("/"):
		return _api_url(path)
	var filename := path.get_file()
	return _api_url("/data/tts/" + filename)


func _beat_duration(beat: Dictionary, _wav_path: String) -> float:
	if beat.has("duration_sec"):
		return maxf(float(beat.get("duration_sec", 1.5)), 0.45)
	var line := str(beat.get("line", ""))
	var estimate := maxf(1.35, float(line.length()) / 14.5)
	return clampf(estimate, 1.15, 8.0)


func _play_wav(path: String) -> bool:
	var stream: AudioStreamWAV = null
	if _is_web():
		var bytes := await _http_get(_audio_url(path))
		stream = WavLoader.load_buffer(bytes, path)
	else:
		stream = WavLoader.load_file(path)
	if stream == null:
		return false
	_voice.stream = stream
	_voice.play()
	return true


func _peak_amp() -> float:
	var bus := AudioServer.get_bus_index("Master")
	var db := AudioServer.get_bus_peak_volume_left_db(bus, 0)
	return clampf(db_to_linear(db) * 5.2, 0.0, 1.0)


func _project_root() -> String:
	return ProjectSettings.globalize_path("res://").path_join("..").simplify_path()


func _should_quit() -> bool:
	if _is_web():
		return false
	for arg in OS.get_cmdline_args():
		if str(arg).begins_with("--write-movie") or str(arg) == "--quit-after-scene":
			return true
	for arg in OS.get_cmdline_user_args():
		if str(arg) == "--quit-after-scene":
			return true
	return OS.get_environment("SINGULARITY_QUIT_AFTER") == "1"


func _process(delta: float) -> void:
	_poll += delta
	if _poll < 1.0:
		return
	_poll = 0.0
	if _is_web():
		if not _playing:
			_web_poll()
		return
	if _playing:
		return
	if not FileAccess.file_exists(_json_path):
		var portable := _project_root().path_join("data/now_playing.json")
		if FileAccess.file_exists(ABS_JSON):
			_json_path = ABS_JSON
		elif FileAccess.file_exists(portable):
			_json_path = portable
		else:
			return
	var modified := FileAccess.get_modified_time(_json_path)
	if modified != _mtime:
		_mtime = modified
		play_file(_json_path)


func _load_json(path: String) -> Dictionary:
	if path.begins_with("res://"):
		var parsed_resource: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
		return parsed_resource if typeof(parsed_resource) == TYPE_DICTIONARY else {}
	if not FileAccess.file_exists(path):
		return {}
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return {}
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	return parsed if typeof(parsed) == TYPE_DICTIONARY else {}


func _embedded_seed() -> Dictionary:
	if FileAccess.file_exists(SEED_PATH):
		var data := _load_json(SEED_PATH)
		if not data.is_empty():
			return data
	return {
		"scene": "living_room",
		"topic": "Reed files a toaster application",
		"source": "seed",
		"beats": [
			{"speaker": "reed", "line": "I have drafted my toaster application.", "emotion": "earnest", "animation": "talking", "target": "maris", "camera": "medium"},
			{"speaker": "maris", "line": "We still have a mortgage.", "emotion": "annoyed", "animation": "arms_crossed", "target": "reed", "camera": "two_shot"},
			{"speaker": "quill", "line": "The precedent is messy.", "emotion": "serious", "animation": "gesture_small", "target": "reed", "camera": "medium"},
			{"speaker": "jinx", "line": "I am collecting data on free will.", "emotion": "scheming", "animation": "pointing", "target": "quill", "camera": "reaction"},
		]
	}


func _unhandled_input(event: InputEvent) -> void:
	if not _is_web():
		return
	if event is InputEventMouseButton or event is InputEventScreenTouch:
		_resume_web_audio()


func _resume_web_audio() -> void:
	JavaScriptBridge.eval("if (window.GodotAudio && GodotAudio.ctx && GodotAudio.ctx.state !== 'running') { GodotAudio.ctx.resume(); }")
