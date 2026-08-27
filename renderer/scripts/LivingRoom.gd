extends Node3D
## Warm, low-poly sitcom set assembled from inexpensive reusable primitive meshes.
## The audience and default actor facing direction are +Z.

var _materials: Dictionary = {}
var _anchors: Dictionary = {}


func _ready() -> void:
	_make_materials()
	_build_anchors()
	_build_environment()
	_build_shell()
	_build_kitchen()
	_build_furniture()
	_build_props()
	_build_lights()


func get_stage_anchors() -> Dictionary:
	## Return a copy so staging code cannot accidentally mutate the authored set map.
	return _anchors.duplicate(true)


func _build_anchors() -> void:
	# Positions are floor coordinates. Seated anchors expose the matching cushion height.
	_anchors = {
		"couch_left": _anchor(Vector3(-1.18, 0.0, -2.56), 0.0, true, 0.60),
		"couch_center": _anchor(Vector3(0.0, 0.0, -2.56), 0.0, true, 0.60),
		"couch_right": _anchor(Vector3(1.18, 0.0, -2.56), 0.0, true, 0.60),
		"couch_front_left": _anchor(Vector3(-0.95, 0.0, -1.84)),
		"couch_front_right": _anchor(Vector3(0.95, 0.0, -1.84)),
		"chair": _anchor(Vector3(-3.30, 0.0, -1.38), 0.0, true, 0.58),
		"rug_left": _anchor(Vector3(-1.72, 0.0, -0.58)),
		"rug_center": _anchor(Vector3(0.0, 0.0, -0.48)),
		"rug_right": _anchor(Vector3(1.72, 0.0, -0.58)),
		"kitchen_entry": _anchor(Vector3(-4.20, 0.0, -2.72)),
		"toaster_side": _anchor(Vector3(-2.72, 0.0, -2.88)),
		"tv_side": _anchor(Vector3(2.62, 0.0, -2.42)),
		"front_door": _anchor(Vector3(4.42, 0.0, -2.88)),
	}
