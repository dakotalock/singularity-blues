extends Node3D
## Reliable multi-camera sitcom coverage. Every setup stays on the audience side
## of the stage and leaves room for the broadcast graphics.

@onready var camera: Camera3D = $Camera3D

var _cast: Dictionary = {}
var _staging: Node = null
var _last_shot: String = "wide"
var _last_speaker: String = ""


func setup(cast: Dictionary, staging: Node = null) -> void:
	_cast = cast
	_staging = staging
	cut_wide()


func apply_beat(beat: Dictionary, index: int, beats: Array) -> void:
	var shot := _pick(beat, index, beats)
	var speaker_id := str(beat.get("speaker", "reed"))
	var target_value: Variant = beat.get("target", null)
	var speaker := _actor(speaker_id)
	var target := _actor(str(target_value) if target_value != null else "")
	match shot:
		"wide":
			cut_wide()
		"medium":
			_medium(speaker, target)
		"two_shot":
			_two_shot(speaker, target)
		"reaction":
			# During dialogue, preserve the speaker. The post-line reaction cut is
			# handled by reaction_hold().
			_medium(speaker, target)
		"dramatic_closeup":
			_close(speaker, target)
		_:
			_medium(speaker, target)
	_last_shot = shot
	_last_speaker = speaker_id


func reaction_hold(who: CharacterActor, from_actor: CharacterActor = null) -> void:
	if who == null:
		return
	_show_cast([who.character_id])
	var head := who.head_world()
	var side := -0.16
	if from_actor != null and from_actor.global_position.x < who.global_position.x:
		side = 0.16
	var pos := head + Vector3(side, 0.03, 2.45)
	_place(pos, head + Vector3(0.0, -0.18, 0.0), 31.0)
	_last_shot = "reaction"


func movement_wide(speaker: CharacterActor = null) -> void:
	_show_cast([])
	if speaker == null:
		cut_wide()
		return
	var x := clampf(speaker.global_position.x * 0.18, -0.55, 0.55)
	_place(Vector3(x, 2.02, 5.75), Vector3(speaker.global_position.x * 0.25, 1.0, -1.25), 42.0)
	_last_shot = "wide"


func _pick(beat: Dictionary, index: int, beats: Array) -> String:
	var requested := str(beat.get("camera", "auto"))
	if requested != "" and requested != "auto" and requested != "null":
		return requested
	var anim := str(beat.get("animation", "talking"))
	var emotion := str(beat.get("emotion", "calm"))
	var speaker := str(beat.get("speaker", ""))
	var target_value: Variant = beat.get("target", null)
	var has_target := target_value != null and str(target_value) != "" and str(target_value) != speaker
	if anim in ["enter", "leave", "walking"]:
		return "wide"
	if anim == "sitting":
		return "two_shot" if has_target else "wide"
	if emotion in ["shocked", "screaming"] or anim in ["shocked", "screaming"]:
		return "dramatic_closeup"
	if has_target and (anim in ["pointing", "arms_crossed", "shrug"] or emotion in ["annoyed", "serious", "scheming", "smug"]):
		return "two_shot"
	if index == 0:
		return "medium"
	# Re-establish geography occasionally, but never bounce wide on every line.
	if index > 0 and index % 5 == 0 and _last_shot != "wide":
		return "wide"
	if speaker == _last_speaker and _last_shot == "medium":
		return "two_shot" if has_target else "medium"
	return "medium"


func _actor(id: String) -> CharacterActor:
	if id == "" or not _cast.has(id):
		return null
	return _cast[id]


func cut_wide() -> void:
	_show_cast([])
	_place(Vector3(0.10, 2.05, 5.85), Vector3(0.0, 1.02, -1.48), 41.5)
	_last_shot = "wide"


func _medium(who: CharacterActor, target: CharacterActor = null) -> void:
	if who == null:
		cut_wide()
		return
	_show_cast([who.character_id])
	var head := who.head_world()
	var lateral := 0.12
	if target != null:
		lateral = -0.16 if target.global_position.x > who.global_position.x else 0.16
	var cam := Vector3(head.x + lateral, clampf(head.y + 0.02, 1.20, 2.25), head.z + 3.15)
	cam.z = clampf(cam.z, 1.05, 4.15)
	_place(cam, head + Vector3(0, -0.22, 0), 32.5)


func _close(who: CharacterActor, target: CharacterActor = null) -> void:
	if who == null:
		cut_wide()
		return
	_show_cast([who.character_id])
	var head := who.head_world()
	var lateral := 0.08
	if target != null:
		lateral = -0.12 if target.global_position.x > who.global_position.x else 0.12
	var cam := Vector3(head.x + lateral, head.y + 0.03, head.z + 2.05)
	cam.z = maxf(cam.z, 0.55)
	_place(cam, head + Vector3(0, -0.10, 0), 29.5)


func _two_shot(a: CharacterActor, b: CharacterActor) -> void:
	if a == null:
		cut_wide()
		return
	if b == null:
		_medium(a)
		return
	_show_cast([a.character_id, b.character_id])
	var ah := a.head_world()
	var bh := b.head_world()
	var mid := (ah + bh) * 0.5
	var horizontal_spread := absf(a.global_position.x - b.global_position.x)
	var depth_spread := absf(a.global_position.z - b.global_position.z)
	var distance := 3.1 + horizontal_spread * 0.62 + depth_spread * 0.28
	var cam := Vector3(mid.x, clampf(maxf(ah.y, bh.y) + 0.04, 1.35, 2.3), maxf(ah.z, bh.z) + distance)
	cam.z = clampf(cam.z, 1.65, 5.15)
	_place(cam, mid + Vector3(0, -0.22, 0), clampf(34.0 + horizontal_spread * 1.4, 34.0, 40.0))


func _place(pos: Vector3, look: Vector3, fov: float) -> void:
	if camera == null:
		return
	pos.x = clampf(pos.x, -4.55, 4.55)
	pos.y = clampf(pos.y, 0.95, 2.55)
	pos.z = clampf(pos.z, 0.45, 6.2)
	camera.global_position = pos
	camera.fov = fov
	var dir := look - pos
	if dir.length() < 0.05:
		return
	camera.look_at(look, Vector3.UP)


func _show_cast(included_ids: Array) -> void:
	# Cheap multicamera blocking: actors outside a single/two-shot are culled for
	# that cut. This prevents foreground limbs from crossing the lens while their
	# authored stage positions remain continuous for the next master shot.
	for id_value in _cast.keys():
		var id := str(id_value)
		var actor: CharacterActor = _cast[id_value]
		var on_stage := true
		if _staging != null and _staging.has_method("anchor_name_for"):
			on_stage = str(_staging.anchor_name_for(id)) != ""
		actor.visible = on_stage and (included_ids.is_empty() or id in included_ids)


func idle_master() -> void:
	cut_wide()
