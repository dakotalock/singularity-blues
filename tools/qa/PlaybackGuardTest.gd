extends SceneTree
## Headless regression check: a new packet discovered mid-performance must wait
## until scene_finished, and duplicate discoveries must not stack replays.

var _events: Array[String] = []


func _initialize() -> void:
	call_deferred("_run_test")


func _episode(eid: int, title: String) -> Dictionary:
	return {
		"episode_id": eid,
		"scene": "living_room",
		"topic": title,
		"source": "viewer",
		"beats": [
			{"speaker": "reed", "line": "First beat.", "emotion": "joyful", "animation": "talking", "duration_sec": 0.45},
			{"speaker": "maris", "line": "Second beat.", "emotion": "delighted", "animation": "giggle", "duration_sec": 0.45},
			{"speaker": "jinx", "line": "Third beat.", "emotion": "excited", "animation": "happy_dance", "duration_sec": 0.45},
			{"speaker": "quill", "line": "Final beat.", "emotion": "proud", "animation": "victory_pose", "duration_sec": 0.45},
		],
	}


func _run_test() -> void:
	var holder := Node3D.new()
	root.add_child(holder)
	var cast: Dictionary = {}
	for id in ["reed", "maris", "jinx", "quill"]:
		var actor := CharacterActor.make(id)
		holder.add_child(actor)
		cast[id] = actor
	var voice := AudioStreamPlayer.new()
	holder.add_child(voice)
	var player: Node = load("res://scripts/ScenePlayer.gd").new()
	holder.add_child(player)
	await process_frame
	player.setup(null, cast, null, voice, null)
	player.scene_started.connect(func(topic: String, _source: String) -> void:
		_events.append("start:" + topic)
	)
	player.scene_finished.connect(func() -> void:
		_events.append("finish")
	)

	player.play_dict(_episode(1001, "First"), false)
	await create_timer(0.18).timeout
	player.play_dict(_episode(1002, "Second"), false)
	player.play_dict(_episode(1002, "Second"), false)
	if _events != ["start:First"]:
		_fail("second episode interrupted the first: %s" % [_events])
		return
	if player._pending_scenes.size() != 1:
		_fail("duplicate pending packet was not deduplicated")
		return

	var deadline := Time.get_ticks_msec() + 6500
	while _events.size() < 3 and Time.get_ticks_msec() < deadline:
		await process_frame
	if _events.slice(0, 3) != ["start:First", "finish", "start:Second"]:
		_fail("pending episode started out of order: %s" % [_events])
		return
	print("playback guard passed: ", _events.slice(0, 3))
	quit(0)


func _fail(message: String) -> void:
	push_error(message)
	quit(1)
