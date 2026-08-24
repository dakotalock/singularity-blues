extends Node3D
## Deterministic sitcom camera: cuts, not dollies.

@onready var camera: Camera3D = $Camera3D

var _cast: Dictionary = {}
var _look: Vector3 = Vector3(0, 1.1, -1.5)

func setup(cast: Dictionary) -> void:
	_cast = cast
	cut_wide()


func apply_beat(beat: Dictionary, index: int, beats: Array) -> void:
	var shot := _pick(beat, index, beats)
	var speaker_id := str(beat.get("speaker", "reed"))
	var target_id: Variant = beat.get("target", null)
	var speaker: CharacterActor = _actor(speaker_id)
	var target: CharacterActor = _actor(str(target_id) if target_id != null else "")
	match shot:
		"wide":
			cut_wide()
		"medium":
			_medium(speaker)
		"two_shot":
			_two_shot(speaker, target)
		"reaction":
			if target:
				_close(target)
			elif speaker:
				_close(speaker)
			else:
				cut_wide()
		"dramatic_closeup":
			_close(speaker)
		_:
			_medium(speaker)


func _pick(beat: Dictionary, index: int, beats: Array) -> String:
	var requested := str(beat.get("camera", "auto"))
	if requested != "" and requested != "auto" and requested != "null":
		return requested
	var anim := str(beat.get("animation", "talking"))
	var emotion := str(beat.get("emotion", "calm"))
	var speaker := str(beat.get("speaker", ""))
	var target: Variant = beat.get("target", null)
	if anim == "enter" or anim == "leave":
		return "wide"
	if index == 0:
		return "medium"
	if index == beats.size() - 1:
		return "reaction"
	if emotion == "shocked" or emotion == "screaming" or anim == "shocked" or anim == "screaming":
		return "dramatic_closeup"
	var has_target := target != null and str(target) != "" and str(target) != speaker
	if has_target and (anim in ["pointing", "arms_crossed", "shrug"] or emotion in ["annoyed", "serious", "scheming"]):
		return "two_shot"
	# 10% closeup, deterministic on beat index.
	if ((index * 17) + 11) % 10 == 0:
		return "dramatic_closeup"
	return "medium"


func _actor(id: String) -> CharacterActor:
	if id == "" or not _cast.has(id):
		return null
	return _cast[id]


func cut_wide() -> void:
	_place(Vector3(0.15, 1.78, 5.55), Vector3(0.0, 1.05, -1.6))


func _medium(who: CharacterActor) -> void:
	if who == null:
		cut_wide()
		return
	var head := who.head_world()
	var cam := head + Vector3(0.12, 0.08, 2.15)
	# Keep camera on audience side (+Z).
	cam.z = maxf(cam.z, 1.6)
	cam.y = clampf(cam.y, 1.15, 1.85)
	_place(cam, head + Vector3(0, -0.05, 0))


func _close(who: CharacterActor) -> void:
	if who == null:
		cut_wide()
		return
	var head := who.head_world()
	var cam := head + Vector3(0.18, 0.04, 0.95)
	cam.z = maxf(cam.z, 0.4)
	_place(cam, head + Vector3(0, -0.02, 0))


func _two_shot(a: CharacterActor, b: CharacterActor) -> void:
	if a == null:
		cut_wide()
		return
	if b == null:
		_medium(a)
		return
	var mid: Vector3 = (a.head_world() + b.head_world()) * 0.5
	var spread: float = a.global_position.distance_to(b.global_position)
	var z := 2.4 + clampf(spread * 0.45, 0.0, 2.0)
	_place(Vector3(mid.x, mid.y + 0.12, maxf(mid.z + z, 2.0)), mid)


func _place(pos: Vector3, look: Vector3) -> void:
	if camera == null:
		return
	pos.x = clampf(pos.x, -4.6, 4.6)
	pos.y = clampf(pos.y, 0.7, 2.6)
	pos.z = clampf(pos.z, 0.3, 6.2)
	camera.global_position = pos
	_look = look
	var dir := look - pos
	if dir.length() < 0.05:
		return
	var up := Vector3.UP
	if absf(dir.normalized().dot(up)) > 0.95:
		up = Vector3.RIGHT
	camera.look_at(look, up)


func idle_master() -> void:
	cut_wide()
