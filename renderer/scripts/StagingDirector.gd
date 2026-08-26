extends Node
class_name StagingDirector
## Authored blocking for the living-room stage. Scene JSON stays semantic; this
## layer owns positions, seats, occupancy, and simple entrance/exit paths.

var _cast: Dictionary = {}
var _room: Node = null
var _anchors: Dictionary = {}
var _actor_anchor: Dictionary = {}
var _occupancy: Dictionary = {}
var _last_speaker: String = ""
var _previous_speaker: String = ""

const HOME_ANCHORS := {
	"reed": "couch_front_left",
	"maris": "couch_front_right",
	"jinx": "rug_left",
	"quill": "rug_right",
}

const SEAT_CHOICES := ["couch_center", "couch_left", "couch_right", "chair"]
const FLOOR_CHOICES := ["rug_center", "rug_left", "rug_right", "tv_side", "toaster_side"]


func setup(cast: Dictionary, room: Node) -> void:
	_cast = cast
	_room = room
	if _room != null and _room.has_method("get_stage_anchors"):
		_anchors = _room.get_stage_anchors()
	if _anchors.is_empty():
		_anchors = _fallback_anchors()
	reset_cast()


func reset_cast() -> void:
	_actor_anchor.clear()
	_occupancy.clear()
	_last_speaker = ""
	_previous_speaker = ""
	for id in _cast.keys():
		var anchor_name := str(HOME_ANCHORS.get(id, "rug_center"))
		var a := _anchor(anchor_name)
		_claim(str(id), anchor_name)
		var actor: CharacterActor = _cast[id]
		actor.configure_home(
			a.get("position", Vector3.ZERO),
			float(a.get("yaw", 0.0)),
			bool(a.get("seated", false)),
			float(a.get("seat_height", 0.62))
		)
		actor.reset_home()
		actor.set_expression("calm")
		actor.face_toward(null)


func prepare_beat(beat: Dictionary, _index: int) -> CharacterActor:
	var speaker_id := str(beat.get("speaker", "reed")).to_lower()
	var speaker: CharacterActor = _actor(speaker_id)
	if speaker == null:
		return null
	var target_id := str(beat.get("target", "") if beat.get("target", null) != null else "").to_lower()
	var target: CharacterActor = _actor(target_id)
	var anim := str(beat.get("animation", "talking"))
	var emotion := str(beat.get("emotion", "calm"))

	# Reset the ensemble softly, then let listeners focus the person with the floor.
	for id in _cast.keys():
		var actor: CharacterActor = _cast[id]
		if str(id) == speaker_id:
			actor.set_expression(emotion)
			actor.face_toward(target)
		else:
			actor.set_expression(_listener_expression(emotion, str(id) == target_id))
			actor.face_toward(speaker)

	match anim:
		"enter":
			_stage_entrance(speaker_id, speaker)
		"walking":
			_stage_walk(speaker_id, speaker, target_id)
		"sitting":
			_stage_sit(speaker_id, speaker)
		_:
			# If somebody spoke after a prior exit, bring them back at their home
			# mark instead of letting an off-screen voice continue indefinitely.
			if not _actor_anchor.has(speaker_id):
				var home_name := str(HOME_ANCHORS.get(speaker_id, "rug_center"))
				var home := _anchor(home_name)
				_claim(speaker_id, home_name)
				speaker.stage_at(
					home.get("position", Vector3.ZERO),
					float(home.get("yaw", 0.0)),
					bool(home.get("seated", false)),
					float(home.get("seat_height", 0.62)),
					true
				)

	_previous_speaker = _last_speaker
	_last_speaker = speaker_id
	return speaker


func finish_beat(beat: Dictionary) -> CharacterActor:
	var speaker_id := str(beat.get("speaker", "reed")).to_lower()
	var speaker := _actor(speaker_id)
	if speaker == null:
		return null
	if str(beat.get("animation", "")) == "leave":
		_release(speaker_id)
		var exit_anchor := _anchor("front_door")
		var exit_pos: Vector3 = exit_anchor.get("position", Vector3(-4.6, 0.0, 1.4))
		# Travel past the door so the silhouette clears frame instead of freezing there.
		var outside_x := 1.25 if exit_pos.x >= 0.0 else -1.25
		exit_pos += Vector3(outside_x, 0.0, -0.30)
		speaker.walk_to(exit_pos, -0.35, false, 0.62)
	return speaker


func reaction_actor(beat: Dictionary) -> CharacterActor:
	var speaker_id := str(beat.get("speaker", "reed")).to_lower()
	var target_value: Variant = beat.get("target", null)
	if target_value != null:
		var explicit := _actor(str(target_value).to_lower())
		if explicit != null and explicit.character_id != speaker_id:
			_apply_reaction_face(explicit, str(beat.get("emotion", "calm")))
			return explicit
	if _previous_speaker != "" and _previous_speaker != speaker_id:
		var previous := _actor(_previous_speaker)
		if previous != null:
			_apply_reaction_face(previous, str(beat.get("emotion", "calm")))
			return previous
	# Stable fallback gives the family a recurring deadpan responder.
	for id in ["maris", "reed", "quill", "jinx"]:
		if id != speaker_id:
			var actor := _actor(id)
			if actor != null:
				_apply_reaction_face(actor, str(beat.get("emotion", "calm")))
				return actor
	return null


func anchor_name_for(id: String) -> String:
	return str(_actor_anchor.get(id, ""))


func _stage_entrance(id: String, actor: CharacterActor) -> void:
	_release(id)
	var door := _anchor("front_door")
	var door_pos: Vector3 = door.get("position", Vector3(-4.35, 0.0, 1.15))
	var outside_x := 1.15 if door_pos.x >= 0.0 else -1.15
	actor.stage_at(door_pos + Vector3(outside_x, 0.0, -0.28), -0.3, false, 0.62, true)
	var destination_name := _best_free(FLOOR_CHOICES, "rug_left")
	var destination := _anchor(destination_name)
	_claim(id, destination_name)
	actor.walk_to(destination.get("position", Vector3.ZERO), float(destination.get("yaw", 0.0)), false, 0.62)


func _stage_walk(id: String, actor: CharacterActor, target_id: String) -> void:
	var preferred: Array[String] = []
	if target_id != "" and _actor_anchor.has(target_id):
		var target_anchor := str(_actor_anchor[target_id])
		if target_anchor.begins_with("couch"):
			preferred = ["rug_center", "rug_left", "rug_right"]
		elif target_anchor == "toaster_side" or target_anchor == "kitchen_entry":
			preferred = ["kitchen_entry", "toaster_side", "rug_left"]
	if preferred.is_empty():
		preferred = FLOOR_CHOICES.duplicate()
	var destination_name := _best_free(preferred, str(_actor_anchor.get(id, "rug_center")))
	if destination_name == str(_actor_anchor.get(id, "")):
		return
	_release(id)
	var destination := _anchor(destination_name)
	_claim(id, destination_name)
	actor.set_seated(false)
	actor.walk_to(destination.get("position", Vector3.ZERO), float(destination.get("yaw", 0.0)), false, 0.62)


func _stage_sit(id: String, actor: CharacterActor) -> void:
	var current := str(_actor_anchor.get(id, ""))
	if current != "" and bool(_anchor(current).get("seated", false)):
		var current_data := _anchor(current)
		actor.set_seated(true, float(current_data.get("seat_height", 0.62)))
		return
	var destination_name := _best_free(SEAT_CHOICES, "chair")
	var destination := _anchor(destination_name)
	_release(id)
	_claim(id, destination_name)
	actor.walk_to(
		destination.get("position", Vector3.ZERO),
		float(destination.get("yaw", 0.0)),
		true,
		float(destination.get("seat_height", 0.62))
	)


func _best_free(candidates: Array, fallback: String) -> String:
	for name_value in candidates:
		var name := str(name_value)
		if _anchors.has(name) and not _occupancy.has(name):
			return name
	if _anchors.has(fallback) and not _occupancy.has(fallback):
		return fallback
	# Never merge actors. If all authored marks are occupied, retain the caller's
	# existing mark rather than stealing somebody else's place.
	return fallback


func _claim(id: String, anchor_name: String) -> void:
	_actor_anchor[id] = anchor_name
	_occupancy[anchor_name] = id


func _release(id: String) -> void:
	if not _actor_anchor.has(id):
		return
	var old := str(_actor_anchor[id])
	_actor_anchor.erase(id)
	if _occupancy.get(old, "") == id:
		_occupancy.erase(old)


func _actor(id: String) -> CharacterActor:
	if id == "" or not _cast.has(id):
		return null
	return _cast[id]


func _anchor(name: String) -> Dictionary:
	if _anchors.has(name) and typeof(_anchors[name]) == TYPE_DICTIONARY:
		return _anchors[name]
	return {
		"position": Vector3.ZERO,
		"yaw": 0.0,
		"seated": false,
		"seat_height": 0.62,
	}


func _listener_expression(speaker_emotion: String, is_target: bool) -> String:
	if not is_target:
		return "calm"
	match speaker_emotion:
		"screaming", "shocked":
			return "shocked"
		"scheming", "smug":
			return "annoyed"
		"tired":
			return "tired"
		_:
			return "calm"


func _apply_reaction_face(actor: CharacterActor, speaker_emotion: String) -> void:
	match speaker_emotion:
		"screaming", "shocked":
			actor.set_expression("shocked")
		"scheming", "smug", "laughing":
			actor.set_expression("annoyed")
		_:
			actor.set_expression("tired")


func _fallback_anchors() -> Dictionary:
	return {
		"couch_left": _a(Vector3(-0.86, 0, -2.48), true, 0.68),
		"couch_center": _a(Vector3(0.0, 0, -2.48), true, 0.68),
		"couch_right": _a(Vector3(0.86, 0, -2.48), true, 0.68),
		"couch_front_left": _a(Vector3(-0.95, 0, -1.84)),
		"couch_front_right": _a(Vector3(0.95, 0, -1.84)),
		"chair": _a(Vector3(-2.75, 0, -1.62), true, 0.64, -0.16),
		"rug_left": _a(Vector3(-2.25, 0, -0.35)),
		"rug_center": _a(Vector3(0.0, 0, -0.25)),
		"rug_right": _a(Vector3(2.05, 0, -0.30)),
		"kitchen_entry": _a(Vector3(-3.8, 0, -1.0)),
		"toaster_side": _a(Vector3(-3.25, 0, -2.05), false, 0.62, 0.18),
		"tv_side": _a(Vector3(3.25, 0, -1.35), false, 0.62, -0.18),
		"front_door": _a(Vector3(-4.35, 0, 1.25), false, 0.62, -0.30),
	}


func _a(pos: Vector3, seated: bool = false, seat_height: float = 0.62, yaw: float = 0.0) -> Dictionary:
	return {"position": pos, "yaw": yaw, "seated": seated, "seat_height": seat_height}
