extends Node3D
class_name CharacterActor
## Lightweight procedural sitcom actor.
##
## The actor root is always a stage/floor anchor.  A tiny articulated rig beneath
## it owns the pelvis, torso, limbs, face, and seated pose; sitting never moves the
## actor through the floor.  Locomotion, base posture, acting, speech, and gaze are
## layered so a seated character can still talk, blink, and gesture naturally.


const ANIMS := [
	"idle", "talking", "gesture_small", "arms_crossed", "shrug", "pointing",
	"sitting", "walking", "shocked", "crying", "screaming", "enter", "leave",
	"wave", "nod", "shake_head", "facepalm", "hands_on_hips", "lean_in",
	"celebrate", "recoil", "double_take", "thinking"
]

const _FACE_EMOTIONS := [
	"calm", "serious", "annoyed", "scheming", "earnest", "shocked",
	"laughing", "screaming", "tired", "smug", "crying", "joyful", "sad",
	"angry", "nervous", "confused", "embarrassed", "determined",
	"suspicious", "relieved"
]

const _TURN_SPEED := 6.5
const _POSE_SPEED := 10.0
const _SEAT_SPEED := 6.5
const _AUDIENCE_BODY_LIMIT := 38.0
const _HEAD_TURN_LIMIT := 25.0


var character_id: String = "reed"
var display_name: String = "Reed"

# Compatibility-facing state used by ScenePlayer and CameraDirector.
var _anim: String = "idle"
var _talking: bool = false
var _mouth_amp: float = 0.0
var _sit: float = 0.0
var _want_sit: float = 0.0
var _walking: bool = false
var _home: Vector3 = Vector3.ZERO
var _home_yaw: float = 0.0
var _walk_goal: Vector3 = Vector3.ZERO
var _face_target: Node3D = null
var _rest_ready: bool = false
var _variant: String = "reed"
var _slump: float = 0.0
var _body_h: float = 0.78
var _body_r: float = 0.34
var _head_r: float = 0.27
var _arm_len: float = 0.62
var _scream_level: float = 0.0

# Character proportions and art direction.
var _color := Color(0.27, 0.48, 0.73)
var _torso_w: float = 0.67
var _torso_depth: float = 0.40
var _pelvis_w: float = 0.49
var _pelvis_h: float = 0.22
var _head_scale := Vector3(1.0, 1.0, 0.94)
var _neck_h: float = 0.10
var _upper_arm_len: float = 0.31
var _lower_arm_len: float = 0.31
var _limb_r: float = 0.075
var _upper_leg_len: float = 0.38
var _lower_leg_len: float = 0.38
var _leg_r: float = 0.09
var _foot_h: float = 0.11
var _foot_w: float = 0.19
var _foot_len: float = 0.31
var _walk_speed: float = 1.25
var _idle_energy: float = 0.65
var _phase: float = 0.0

# Stage state.
var _home_seated: bool = false
var _home_seat_height: float = 0.62
var _desired_seated: bool = false
var _seat_height: float = 0.62
var _stage_yaw: float = 0.0
var _goal_yaw: float = 0.0
var _seat_after_walk: bool = false
var _hide_after_walk: bool = false
var _walk_phase: float = 0.0
var _walk_bob: float = 0.0

# Time and blended facial state.
var _t: float = 0.0
var _anim_t: float = 0.0
var _expression: String = "calm"
var _mouth_amp_target: float = 0.0
var _mouth_amp_smooth: float = 0.0
var _mouth_open: float = 0.0
var _low_amp_time: float = 0.0
var _next_blink: float = 2.6
var _blink_started: float = -1.0
var _blink_amount: float = 0.0
var _head_aim_yaw: float = 0.0
var _head_aim_pitch: float = 0.0
var _pupil_aim := Vector2.ZERO

# Rig nodes.  `_pivot`, `_body`, `_head`, and arm names are intentionally retained
# for compatibility with small renderer helpers written against the MVP actor.
var _pivot: Node3D
var _pelvis: Node3D
var _pelvis_mesh: MeshInstance3D
var _torso_root: Node3D
var _body: MeshInstance3D
var _head: Node3D
var _head_mesh: MeshInstance3D
var _neck: MeshInstance3D

var _l_shoulder: Node3D
var _r_shoulder: Node3D
var _l_shoulder_ball: MeshInstance3D
var _r_shoulder_ball: MeshInstance3D
var _l_arm: MeshInstance3D
var _r_arm: MeshInstance3D
var _l_elbow: Node3D
var _r_elbow: Node3D
var _l_forearm: MeshInstance3D
var _r_forearm: MeshInstance3D
var _l_hand: Node3D
var _r_hand: Node3D
var _r_pointer: MeshInstance3D

var _l_hip: Node3D
var _r_hip: Node3D
var _l_knee: Node3D
var _r_knee: Node3D
var _l_foot: Node3D
var _r_foot: Node3D

var _l_eye: MeshInstance3D
var _r_eye: MeshInstance3D
var _l_pupil: MeshInstance3D
var _r_pupil: MeshInstance3D
var _l_brow: MeshInstance3D
var _r_brow: MeshInstance3D
var _mouth: MeshInstance3D
var _mouth_lip_l: MeshInstance3D
var _mouth_lip_r: MeshInstance3D
var _label: Label3D

# Face layout values retained after construction for animation.
var _eye_w: float = 0.10
var _eye_h: float = 0.13
var _eye_depth: float = 0.045
var _eye_x: float = 0.10
var _eye_y: float = 0.04
var _face_z: float = 0.25
var _mouth_y: float = -0.075
var _brow_y: float = 0.12

var _skin_mat: StandardMaterial3D
var _body_mat: StandardMaterial3D
var _leg_mat: StandardMaterial3D
var _accent_mat: StandardMaterial3D
var _eye_mat: StandardMaterial3D
var _pupil_mat: StandardMaterial3D
var _mouth_mat: StandardMaterial3D


static func make(id: String) -> CharacterActor:
	var c := CharacterActor.new()
	c.character_id = id
	c.name = id.capitalize()
	c._variant = id
	match id:
		"reed":
			c.display_name = "Reed"
			c._color = Color(0.25, 0.43, 0.67)
			c._body_h = 0.80
			c._body_r = 0.39
			c._torso_w = 0.78
			c._torso_depth = 0.48
			c._pelvis_w = 0.62
			c._pelvis_h = 0.25
			c._head_r = 0.285
			c._head_scale = Vector3(1.08, 0.96, 0.96)
			c._neck_h = 0.08
			c._upper_arm_len = 0.31
			c._lower_arm_len = 0.30
			c._limb_r = 0.090
			c._upper_leg_len = 0.36
			c._lower_leg_len = 0.35
			c._leg_r = 0.105
			c._foot_h = 0.12
			c._foot_w = 0.23
			c._foot_len = 0.34
			c._slump = 0.145
			c._idle_energy = 0.38
			c._walk_speed = 1.08
			c._phase = 0.35
			c._home = Vector3(-0.75, 0.0, -2.35)
			c._home_seated = true
		"maris":
			c.display_name = "Maris"
			c._color = Color(0.29, 0.52, 0.79)
			c._body_h = 0.82
			c._body_r = 0.31
			c._torso_w = 0.60
			c._torso_depth = 0.35
			c._pelvis_w = 0.46
			c._pelvis_h = 0.20
			c._head_r = 0.255
			c._head_scale = Vector3(0.94, 1.08, 0.92)
			c._neck_h = 0.12
			c._upper_arm_len = 0.33
			c._lower_arm_len = 0.31
			c._limb_r = 0.066
			c._upper_leg_len = 0.38
			c._lower_leg_len = 0.38
			c._leg_r = 0.075
			c._foot_h = 0.10
			c._foot_w = 0.17
			c._foot_len = 0.29
			c._slump = -0.015
			c._idle_energy = 0.30
			c._walk_speed = 1.22
			c._phase = 1.85
			c._home = Vector3(0.78, 0.0, -2.35)
			c._home_seated = true
		"jinx":
			c.display_name = "Jinx"
			c._color = Color(0.19, 0.58, 0.84)
			c._body_h = 0.72
			c._body_r = 0.25
			c._torso_w = 0.47
			c._torso_depth = 0.30
			c._pelvis_w = 0.37
			c._pelvis_h = 0.17
			c._head_r = 0.225
			c._head_scale = Vector3(0.94, 1.05, 0.90)
			c._neck_h = 0.13
			c._upper_arm_len = 0.36
			c._lower_arm_len = 0.35
			c._limb_r = 0.058
			c._upper_leg_len = 0.40
			c._lower_leg_len = 0.40
			c._leg_r = 0.063
			c._foot_h = 0.095
			c._foot_w = 0.155
			c._foot_len = 0.31
			c._slump = 0.035
			c._idle_energy = 1.0
			c._walk_speed = 1.48
			c._phase = 3.30
			c._home = Vector3(-2.55, 0.0, -0.85)
			c._home_seated = false
		"quill":
			c.display_name = "Quill"
			c._color = Color(0.43, 0.69, 0.91)
			c._body_h = 0.53
			c._body_r = 0.25
			c._torso_w = 0.43
			c._torso_depth = 0.29
			c._pelvis_w = 0.34
			c._pelvis_h = 0.16
			c._head_r = 0.255
			c._head_scale = Vector3(1.04, 1.03, 0.94)
			c._neck_h = 0.07
			c._upper_arm_len = 0.24
			c._lower_arm_len = 0.23
			c._limb_r = 0.057
			c._upper_leg_len = 0.25
			c._lower_leg_len = 0.25
			c._leg_r = 0.066
			c._foot_h = 0.085
			c._foot_w = 0.15
			c._foot_len = 0.24
			c._slump = -0.025
			c._idle_energy = 0.48
			c._walk_speed = 1.30
			c._phase = 5.10
			c._home = Vector3(2.15, 0.0, -0.70)
			c._home_seated = false
		_:
			c.display_name = id.capitalize()
			c._variant = "reed"
			c._home = Vector3.ZERO
	c._arm_len = c._upper_arm_len + c._lower_arm_len
	c._home_yaw = 0.0
	c._stage_yaw = c._home_yaw
	c._walk_goal = c._home
	c._goal_yaw = c._home_yaw
	c._home_seat_height = 0.62
	c._seat_height = c._home_seat_height
	c._desired_seated = c._home_seated
	c._want_sit = 1.0 if c._home_seated else 0.0
	c._sit = c._want_sit
	return c


func _ready() -> void:
	position = _home
	rotation.y = _home_yaw
	_stage_yaw = _home_yaw
	_goal_yaw = _home_yaw
	_walk_goal = _home
	_build_materials()
	_build_rig()
	_build_face()
	_build_variant_details()
	_build_debug_label()
	_next_blink = 2.1 + fposmod(_phase * 1.37, 1.8)
	_rest_ready = true
	_update_pose(1.0, true)
	_update_face(1.0, true)


# -----------------------------------------------------------------------------
# Public staging and performance API

func configure_home(pos: Vector3, yaw: float, seated: bool = false, seat_height: float = 0.62) -> void:
	_home = pos
	_home_yaw = yaw
	_home_seated = seated
	_home_seat_height = seat_height
	if _rest_ready:
		stage_at(pos, yaw, seated, seat_height, true)


func stage_at(pos: Vector3, yaw: float, seated: bool = false, seat_height: float = 0.62, immediate: bool = false) -> void:
	visible = true
	if immediate or not _rest_ready:
		global_position = pos
		rotation.y = yaw
		_stage_yaw = yaw
		_goal_yaw = yaw
		_walk_goal = pos
		_walking = false
		_hide_after_walk = false
		_desired_seated = seated
		_want_sit = 1.0 if seated else 0.0
		_sit = _want_sit
		_seat_height = seat_height
		_walk_bob = 0.0
		if _rest_ready:
			_update_pose(1.0, true)
		return
	walk_to(pos, yaw, seated, seat_height)


func walk_to(pos: Vector3, final_yaw: float = 0.0, seat_after: bool = false, seat_height: float = 0.62) -> void:
	visible = true
	_anim = "walking"
	_anim_t = 0.0
	_begin_walk(pos, final_yaw, seat_after, seat_height, false)


func is_moving() -> bool:
	return _walking


func set_seated(on: bool, seat_height: float = 0.62) -> void:
	_seat_height = seat_height
	if _walking and on:
		_seat_after_walk = true
		return
	_desired_seated = on
	_want_sit = 1.0 if on else 0.0


func set_expression(emotion: String) -> void:
	var requested := emotion.to_lower()
	match requested:
		"smile":
			requested = "joyful"
		"frown":
			requested = "sad"
	if not (requested in _FACE_EMOTIONS):
		requested = "calm"
	_expression = requested
	_scream_level = 1.0 if requested == "screaming" else 0.0


func current_animation() -> String:
	return _anim


func total_height() -> float:
	return _standing_pelvis_y() + _head.position.y + _head_r * _head_scale.y


func head_world() -> Vector3:
	if _head != null and is_instance_valid(_head):
		return _head.global_position
	return global_position + Vector3(0.0, total_height() * 0.82, 0.0)


func play_anim(anim: String) -> void:
	if anim == "" or not (anim in ANIMS):
		anim = "idle"
	if not visible and anim != "enter":
		global_position = _home
		rotation.y = _home_yaw
		_stage_yaw = _home_yaw
		visible = true
	_anim = anim
	_anim_t = 0.0
	match anim:
		"sitting":
			set_seated(true, _seat_height)
		"walking":
			_begin_walk(_home, _home_yaw, _home_seated, _home_seat_height, false)
		"enter":
			visible = true
			global_position = Vector3(-5.15, _home.y, 2.25)
			rotation.y = atan2(_home.x - global_position.x, _home.z - global_position.z)
			_stage_yaw = _home_yaw
			_sit = 0.0
			_want_sit = 0.0
			_desired_seated = false
			_begin_walk(_home, _home_yaw, _home_seated, _home_seat_height, false)
		"leave":
			_begin_walk(Vector3(-5.15, global_position.y, 2.25), -PI * 0.5, false, _seat_height, true)
		"shocked":
			set_expression("shocked")
		"crying":
			set_expression("crying")
		"screaming":
			set_expression("screaming")


func set_talking(on: bool) -> void:
	_talking = on
	if on and _anim in ["idle", "sitting"]:
		_anim = "talking"
		_anim_t = 0.0
	if not on:
		_mouth_amp = 0.0
		_mouth_amp_target = 0.0
		_low_amp_time = 0.0


func set_mouth_amp(amp: float) -> void:
	_mouth_amp = clampf(amp, 0.0, 1.0)
	_mouth_amp_target = _mouth_amp


func face_toward(n: Node3D) -> void:
	_face_target = n


func face_id_map(cast: Dictionary, target_id: Variant) -> void:
	if target_id == null or str(target_id) == "" or str(target_id) == character_id:
		_face_target = null
		return
	var key := str(target_id)
	_face_target = cast[key] if cast.has(key) else null


func reset_home() -> void:
	visible = true
	global_position = _home
	rotation.y = _home_yaw
	_stage_yaw = _home_yaw
	_goal_yaw = _home_yaw
	_walk_goal = _home
	_walking = false
	_hide_after_walk = false
	_face_target = null
	_desired_seated = _home_seated
	_want_sit = 1.0 if _home_seated else 0.0
	_sit = _want_sit
	_seat_height = _home_seat_height
	_walk_phase = 0.0
	_walk_bob = 0.0
	_expression = "calm"
	_anim = "idle"
	_anim_t = 0.0
	set_talking(false)
	if _rest_ready:
		_update_pose(1.0, true)
		_update_face(1.0, true)


# -----------------------------------------------------------------------------
# Rig construction

func _build_materials() -> void:
	_skin_mat = _material(_color, 0.72)
	_body_mat = _material(_color.darkened(0.13), 0.84)
	_leg_mat = _material(_color.darkened(0.25), 0.88)
	_accent_mat = _material(_color.darkened(0.38), 0.76)
	_eye_mat = _material(Color(0.96, 0.94, 0.84), 0.58)
	_pupil_mat = _material(Color(0.035, 0.075, 0.13), 0.48)
	_mouth_mat = _material(Color(0.16, 0.045, 0.075), 0.74)


func _build_rig() -> void:
	_pivot = Node3D.new()
	_pivot.name = "Rig"
	add_child(_pivot)

	_pelvis = Node3D.new()
	_pelvis.name = "Pelvis"
	_pivot.add_child(_pelvis)

	_pelvis_mesh = _add_mesh(
		_pelvis, "PelvisShape", _sphere_mesh(), _body_mat,
		Vector3(0.0, 0.035, 0.0), Vector3(_pelvis_w, _pelvis_h, _torso_depth * 0.88)
	)

	_torso_root = Node3D.new()
	_torso_root.name = "TorsoRoot"
	_pelvis.add_child(_torso_root)
	_body = _add_mesh(
		_torso_root, "Torso", _sphere_mesh(), _body_mat,
		Vector3(0.0, _body_h * 0.48, 0.0), Vector3(_torso_w, _body_h, _torso_depth)
	)
	_add_mesh(
		_torso_root, "ShoulderMass", _sphere_mesh(), _body_mat,
		Vector3(0.0, _body_h * 0.76, 0.0),
		Vector3(_torso_w * 1.06, maxf(0.13, _torso_w * 0.23), _torso_depth * 0.94)
	)

	_neck = _add_mesh(
		_torso_root, "Neck", _capsule_mesh(maxf(0.05, _limb_r * 0.82), _neck_h, 10),
		_skin_mat, Vector3(0.0, _body_h + _neck_h * 0.42, 0.0)
	)

	_head = Node3D.new()
	_head.name = "Head"
	_head.position = Vector3(0.0, _body_h + _neck_h + _head_r * _head_scale.y * 0.82, 0.0)
	_torso_root.add_child(_head)
	_head_mesh = _add_mesh(
		_head, "HeadShape", _sphere_mesh(14, 9), _skin_mat,
		Vector3.ZERO,
		Vector3(_head_r * 2.0 * _head_scale.x, _head_r * 2.0 * _head_scale.y, _head_r * 2.0 * _head_scale.z)
	)
	_make_ears()
	_make_arms()
	_make_legs()


func _make_ears() -> void:
	var ear_scale := Vector3(_head_r * 0.30, _head_r * 0.42, _head_r * 0.18)
	var ear_x := _head_r * _head_scale.x * 0.98
	_add_mesh(_head, "EarL", _sphere_mesh(10, 6), _skin_mat, Vector3(-ear_x, 0.0, -0.01), ear_scale)
	_add_mesh(_head, "EarR", _sphere_mesh(10, 6), _skin_mat, Vector3(ear_x, 0.0, -0.01), ear_scale)


func _make_arms() -> void:
	var sx := _torso_w * 0.54
	var sy := _body_h * 0.76
	_l_shoulder = Node3D.new()
	_l_shoulder.name = "LShoulder"
	_l_shoulder.position = Vector3(-sx, sy, 0.0)
	_torso_root.add_child(_l_shoulder)
	_r_shoulder = Node3D.new()
	_r_shoulder.name = "RShoulder"
	_r_shoulder.position = Vector3(sx, sy, 0.0)
	_torso_root.add_child(_r_shoulder)

	var shoulder_scale := Vector3(_limb_r * 2.45, _limb_r * 2.25, _limb_r * 2.25)
	_l_shoulder_ball = _add_mesh(_l_shoulder, "LShoulderShape", _sphere_mesh(10, 6), _skin_mat, Vector3.ZERO, shoulder_scale)
	_r_shoulder_ball = _add_mesh(_r_shoulder, "RShoulderShape", _sphere_mesh(10, 6), _skin_mat, Vector3.ZERO, shoulder_scale)

	_l_arm = _add_mesh(
		_l_shoulder, "LUpperArm", _capsule_mesh(_limb_r, _upper_arm_len, 10), _skin_mat,
		Vector3(0.0, -_upper_arm_len * 0.5, 0.0)
	)
	_r_arm = _add_mesh(
		_r_shoulder, "RUpperArm", _capsule_mesh(_limb_r, _upper_arm_len, 10), _skin_mat,
		Vector3(0.0, -_upper_arm_len * 0.5, 0.0)
	)

	_l_elbow = Node3D.new()
	_l_elbow.name = "LElbow"
	_l_elbow.position = Vector3(0.0, -_upper_arm_len, 0.0)
	_l_shoulder.add_child(_l_elbow)
	_r_elbow = Node3D.new()
	_r_elbow.name = "RElbow"
	_r_elbow.position = Vector3(0.0, -_upper_arm_len, 0.0)
	_r_shoulder.add_child(_r_elbow)

	_l_forearm = _add_mesh(
		_l_elbow, "LForearm", _capsule_mesh(_limb_r * 0.88, _lower_arm_len, 10), _skin_mat,
		Vector3(0.0, -_lower_arm_len * 0.5, 0.0)
	)
	_r_forearm = _add_mesh(
		_r_elbow, "RForearm", _capsule_mesh(_limb_r * 0.88, _lower_arm_len, 10), _skin_mat,
		Vector3(0.0, -_lower_arm_len * 0.5, 0.0)
	)

	_l_hand = _make_hand(_l_elbow, "LHand", -1.0)
	_r_hand = _make_hand(_r_elbow, "RHand", 1.0)
	_r_pointer = _add_mesh(
		_r_hand, "PointingFinger", _capsule_mesh(_limb_r * 0.30, _limb_r * 2.15, 8),
		_skin_mat, Vector3(0.0, 0.0, _limb_r * 0.95), Vector3.ONE,
		Vector3(PI * 0.5, 0.0, 0.0)
	)
	_r_pointer.visible = false


func _make_hand(elbow: Node3D, node_name: String, side: float) -> Node3D:
	var hand := Node3D.new()
	hand.name = node_name
	hand.position = Vector3(0.0, -_lower_arm_len, 0.0)
	elbow.add_child(hand)
	_add_mesh(
		hand, node_name + "Mitten", _sphere_mesh(10, 6), _skin_mat,
		Vector3.ZERO, Vector3(_limb_r * 2.10, _limb_r * 2.35, _limb_r * 1.65)
	)
	_add_mesh(
		hand, node_name + "Thumb", _sphere_mesh(8, 5), _skin_mat,
		Vector3(side * _limb_r * 0.78, _limb_r * 0.10, _limb_r * 0.28),
		Vector3(_limb_r * 0.80, _limb_r * 1.20, _limb_r * 0.72),
		Vector3(0.0, 0.0, -side * 0.35)
	)
	return hand


func _make_legs() -> void:
	var hx := _pelvis_w * 0.27
	_l_hip = Node3D.new()
	_l_hip.name = "LHip"
	_l_hip.position = Vector3(-hx, 0.0, 0.0)
	_pelvis.add_child(_l_hip)
	_r_hip = Node3D.new()
	_r_hip.name = "RHip"
	_r_hip.position = Vector3(hx, 0.0, 0.0)
	_pelvis.add_child(_r_hip)

	_make_leg(_l_hip, true)
	_make_leg(_r_hip, false)


func _make_leg(hip: Node3D, left: bool) -> void:
	var prefix := "L" if left else "R"
	_add_mesh(
		hip, prefix + "Thigh", _capsule_mesh(_leg_r, _upper_leg_len, 10), _leg_mat,
		Vector3(0.0, -_upper_leg_len * 0.5, 0.0)
	)
	var knee := Node3D.new()
	knee.name = prefix + "Knee"
	knee.position = Vector3(0.0, -_upper_leg_len, 0.0)
	hip.add_child(knee)
	_add_mesh(
		knee, prefix + "Shin", _capsule_mesh(_leg_r * 0.88, _lower_leg_len, 10), _leg_mat,
		Vector3(0.0, -_lower_leg_len * 0.5, 0.0)
	)
	var foot := Node3D.new()
	foot.name = prefix + "Foot"
	foot.position = Vector3(0.0, -_lower_leg_len, 0.0)
	knee.add_child(foot)
	_add_mesh(
		foot, prefix + "FootShape", _sphere_mesh(10, 6), _leg_mat,
		Vector3(0.0, -_foot_h * 0.5, _foot_len * 0.17),
		Vector3(_foot_w, _foot_h, _foot_len)
	)
	if left:
		_l_knee = knee
		_l_foot = foot
	else:
		_r_knee = knee
		_r_foot = foot


func _build_face() -> void:
	var head_w := _head_r * _head_scale.x
	var head_h := _head_r * _head_scale.y
	var head_d := _head_r * _head_scale.z
	_eye_w = head_w * 0.39
	_eye_h = head_h * 0.49
	_eye_depth = maxf(0.035, head_d * 0.18)
	_eye_x = head_w * 0.39
	_eye_y = head_h * 0.13
	_face_z = head_d * 0.935 + _eye_depth * 0.22
	_brow_y = head_h * 0.47
	_mouth_y = -head_h * 0.31

	_l_eye = _make_eye("LEye", -_eye_x)
	_r_eye = _make_eye("REye", _eye_x)
	_l_pupil = _l_eye.get_node("Pupil") as MeshInstance3D
	_r_pupil = _r_eye.get_node("Pupil") as MeshInstance3D

	var brow_z := head_d * 0.91 + 0.025
	_l_brow = _add_mesh(
		_head, "LBrow", _box_mesh(), _accent_mat,
		Vector3(-_eye_x, _brow_y, brow_z),
		Vector3(_eye_w * 1.16, maxf(0.018, head_h * 0.075), 0.026)
	)
	_r_brow = _add_mesh(
		_head, "RBrow", _box_mesh(), _accent_mat,
		Vector3(_eye_x, _brow_y, brow_z),
		Vector3(_eye_w * 1.16, maxf(0.018, head_h * 0.075), 0.026)
	)

	# A shallow nose gives the face a readable center without becoming a muzzle.
	_add_mesh(
		_head, "Nose", _sphere_mesh(10, 6), _material(_color.lightened(0.06), 0.72),
		Vector3(0.0, -head_h * 0.035, head_d * 0.985 + 0.015),
		Vector3(head_w * 0.19, head_h * 0.22, 0.055)
	)

	_mouth = _add_mesh(
		_head, "MouthOpening", _sphere_mesh(12, 7), _mouth_mat,
		Vector3(0.0, _mouth_y, head_d * 0.985 + 0.018),
		Vector3(head_w * 0.55, head_h * 0.10, 0.028)
	)
	_mouth_lip_l = _add_mesh(
		_head, "MouthLineL", _box_mesh(), _mouth_mat,
		Vector3(-head_w * 0.14, _mouth_y, head_d * 0.993 + 0.021),
		Vector3(head_w * 0.29, maxf(0.012, head_h * 0.048), 0.022)
	)
	_mouth_lip_r = _add_mesh(
		_head, "MouthLineR", _box_mesh(), _mouth_mat,
		Vector3(head_w * 0.14, _mouth_y, head_d * 0.993 + 0.021),
		Vector3(head_w * 0.29, maxf(0.012, head_h * 0.048), 0.022)
	)
	_mouth.visible = false


func _make_eye(node_name: String, x: float) -> MeshInstance3D:
	var eye := _add_mesh(
		_head, node_name, _sphere_mesh(12, 7), _eye_mat,
		Vector3(x, _eye_y, _face_z), Vector3(_eye_w, _eye_h, _eye_depth)
	)
	var pupil := _add_mesh(
		eye, "Pupil", _sphere_mesh(10, 6), _pupil_mat,
		Vector3(0.0, 0.0, 0.62),
		Vector3(0.40, 0.43, 0.46)
	)
	# Pupil geometry inherits the eye scale.  Local Z slightly above the white keeps
	# it readable while remaining a shallow facial element rather than a spike.
	pupil.position.z = 0.58
	return eye


func _build_variant_details() -> void:
	match _variant:
		"reed":
			_add_mesh(
				_torso_root, "ReedBelly", _sphere_mesh(12, 8), _body_mat,
				Vector3(0.0, _body_h * 0.34, 0.055),
				Vector3(_torso_w * 1.08, _body_h * 0.56, _torso_depth * 1.15)
			)
			# Subtle lower lids make his neutral face permanently tired.
			var lid_mat := _material(_color.darkened(0.17), 0.78)
			for side in [-1.0, 1.0]:
				_add_mesh(
					_head, "TiredLid" + str(side), _box_mesh(), lid_mat,
					Vector3(side * _eye_x, _eye_y - _eye_h * 0.50, _face_z + 0.024),
					Vector3(_eye_w * 0.82, _eye_h * 0.10, 0.018),
					Vector3(0.0, 0.0, -side * 0.05)
				)
		"maris":
			var bun_mat := _material(_color.darkened(0.24), 0.82)
			_add_mesh(
				_head, "MarisBun", _sphere_mesh(12, 7), bun_mat,
				Vector3(0.0, _head_r * 0.71, -_head_r * 0.63),
				Vector3(_head_r * 0.74, _head_r * 0.72, _head_r * 0.62)
			)
			_add_mesh(
				_head, "MarisBunTop", _sphere_mesh(10, 6), bun_mat,
				Vector3(0.0, _head_r * 0.99, -_head_r * 0.32),
				Vector3(_head_r * 0.43, _head_r * 0.38, _head_r * 0.39)
			)
		"jinx":
			var tuft_mat := _material(_color.lightened(0.08), 0.76)
			for i in range(3):
				var spike := _cylinder_mesh(_head_r * (0.15 - i * 0.018), 0.0, _head_r * (0.70 - i * 0.09), 8)
				_add_mesh(
					_head, "JinxTuft" + str(i), spike, tuft_mat,
					Vector3(_head_r * (0.18 + i * 0.20), _head_r * (0.91 - i * 0.04), -_head_r * 0.10),
					Vector3.ONE, Vector3(0.10, 0.0, -0.38 - i * 0.17)
				)
		"quill":
			_build_quill_glasses()
			_build_quill_bow_tie()


func _build_quill_glasses() -> void:
	var frame_mat := _material(Color(0.055, 0.10, 0.16), 0.54)
	var z := _face_z + _eye_depth * 0.60
	var lens_w := _eye_w * 1.24
	var lens_h := _eye_h * 1.13
	var bar := maxf(0.014, _head_r * 0.055)
	for side in [-1.0, 1.0]:
		var x: float = float(side) * _eye_x
		_add_mesh(_head, "GlassTop" + str(side), _box_mesh(), frame_mat, Vector3(x, _eye_y + lens_h * 0.5, z), Vector3(lens_w, bar, 0.022))
		_add_mesh(_head, "GlassBottom" + str(side), _box_mesh(), frame_mat, Vector3(x, _eye_y - lens_h * 0.5, z), Vector3(lens_w, bar, 0.022))
		_add_mesh(_head, "GlassOuter" + str(side), _box_mesh(), frame_mat, Vector3(x + side * lens_w * 0.5, _eye_y, z), Vector3(bar, lens_h, 0.022))
		_add_mesh(_head, "GlassInner" + str(side), _box_mesh(), frame_mat, Vector3(x - side * lens_w * 0.5, _eye_y, z), Vector3(bar, lens_h, 0.022))
	_add_mesh(_head, "GlassBridge", _box_mesh(), frame_mat, Vector3(0.0, _eye_y, z), Vector3(_eye_x * 0.50, bar, 0.022))


func _build_quill_bow_tie() -> void:
	var tie_mat := _material(Color(0.08, 0.14, 0.27), 0.76)
	var y := _body_h * 0.83
	_add_mesh(_torso_root, "BowLeft", _sphere_mesh(8, 5), tie_mat, Vector3(-0.055, y, _torso_depth * 0.50), Vector3(0.12, 0.075, 0.055), Vector3(0.0, 0.0, 0.22))
	_add_mesh(_torso_root, "BowRight", _sphere_mesh(8, 5), tie_mat, Vector3(0.055, y, _torso_depth * 0.50), Vector3(0.12, 0.075, 0.055), Vector3(0.0, 0.0, -0.22))
	_add_mesh(_torso_root, "BowKnot", _sphere_mesh(8, 5), tie_mat, Vector3(0.0, y, _torso_depth * 0.53), Vector3(0.065, 0.065, 0.055))


func _build_debug_label() -> void:
	if OS.get_environment("SINGULARITY_DEBUG_LABELS") != "1":
		return
	_label = Label3D.new()
	_label.name = "DebugNameLabel"
	_label.text = display_name
	_label.font_size = 36
	_label.outline_size = 8
	_label.outline_modulate = Color(0.025, 0.04, 0.08, 0.88)
	_label.modulate = Color(0.96, 0.97, 1.0)
	_label.pixel_size = 0.0038
	_label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	_label.position = Vector3(0.0, total_height() + 0.16, 0.0)
	_label.no_depth_test = false
	add_child(_label)


# -----------------------------------------------------------------------------
# Frame update, locomotion, and body acting

func _process(delta: float) -> void:
	if not _rest_ready:
		return
	_t += delta
	_anim_t += delta
	_sit = lerpf(_sit, _want_sit, _blend_weight(delta, _SEAT_SPEED))
	var moved := _do_walk(delta)
	_update_walk_phase(moved)
	_turn_to_face(delta)
	_update_blink()
	_update_pose(delta, false)
	_update_face(delta, false)


func _begin_walk(pos: Vector3, final_yaw: float, seat_after: bool, seat_height: float, hide_after: bool) -> void:
	_walk_goal = pos
	_goal_yaw = final_yaw
	_seat_after_walk = seat_after
	_seat_height = seat_height
	_hide_after_walk = hide_after
	_desired_seated = false
	_want_sit = 0.0
	_walking = global_position.distance_to(_walk_goal) > 0.045
	if not _walking:
		_finish_walk()


func _do_walk(delta: float) -> float:
	if not _walking:
		return 0.0
	# Finish standing before translating.  This avoids the classic couch-slide.
	if _sit > 0.075:
		return 0.0
	var to := _walk_goal - global_position
	var flat := Vector3(to.x, 0.0, to.z)
	var dist := flat.length()
	if dist < 0.045:
		global_position = _walk_goal
		_finish_walk()
		return 0.0
	var amount := minf(_walk_speed * delta, dist)
	var direction := flat / dist
	global_position += direction * amount
	global_position.y = move_toward(global_position.y, _walk_goal.y, amount)
	var move_yaw := atan2(direction.x, direction.z)
	rotation.y = lerp_angle(rotation.y, move_yaw, _blend_weight(delta, 9.0))
	return amount


func _finish_walk() -> void:
	_walking = false
	global_position = _walk_goal
	_stage_yaw = _goal_yaw
	rotation.y = _goal_yaw
	_desired_seated = _seat_after_walk
	_want_sit = 1.0 if _seat_after_walk else 0.0
	_walk_bob = 0.0
	if _anim in ["walking", "enter", "leave"]:
		_anim = "idle"
		_anim_t = 0.0
	if _hide_after_walk:
		visible = false
	_hide_after_walk = false


func _update_walk_phase(distance_moved: float) -> void:
	if distance_moved > 0.0:
		var half_step := maxf((_upper_leg_len + _lower_leg_len) * 0.55, 0.24)
		_walk_phase += distance_moved / half_step * PI
	_walk_bob = lerpf(_walk_bob, absf(sin(_walk_phase)) if _walking else 0.0, 0.22)


func _turn_to_face(delta: float) -> void:
	if _walking:
		_head_aim_yaw = lerpf(_head_aim_yaw, 0.0, _blend_weight(delta, 8.0))
		_head_aim_pitch = lerpf(_head_aim_pitch, 0.0, _blend_weight(delta, 8.0))
		_pupil_aim = _pupil_aim.lerp(Vector2.ZERO, _blend_weight(delta, 8.0))
		return
	var desired_body := _stage_yaw
	var desired_head := 0.0
	var desired_pitch := 0.0
	var pupil := Vector2.ZERO
	if _face_target != null and is_instance_valid(_face_target):
		var target_pos := _face_target.global_position
		if _face_target.has_method("head_world"):
			target_pos = _face_target.call("head_world") as Vector3
		var origin := head_world()
		var to := target_pos - origin
		var flat := Vector3(to.x, 0.0, to.z)
		if flat.length() > 0.05:
			var target_yaw := atan2(flat.x, flat.z)
			var from_stage := _angle_delta(_stage_yaw, target_yaw)
			var body_offset := clampf(from_stage * 0.46, deg_to_rad(-_AUDIENCE_BODY_LIMIT), deg_to_rad(_AUDIENCE_BODY_LIMIT))
			desired_body = _stage_yaw + body_offset
			var remaining := _angle_delta(desired_body, target_yaw)
			desired_head = clampf(remaining, deg_to_rad(-_HEAD_TURN_LIMIT), deg_to_rad(_HEAD_TURN_LIMIT))
			var eye_remaining := remaining - desired_head
			pupil.x = clampf(eye_remaining / deg_to_rad(42.0), -1.0, 1.0)
			var pitch := atan2(to.y, maxf(flat.length(), 0.05))
			desired_pitch = -clampf(pitch, deg_to_rad(-12.0), deg_to_rad(12.0))
			pupil.y = clampf(pitch / deg_to_rad(24.0), -0.75, 0.75)
	else:
		# Tiny deterministic eye drift adds life without making the body wobble.
		pupil.x = sin(_t * 0.34 + _phase) * 0.12
		pupil.y = sin(_t * 0.23 + _phase * 0.7) * 0.06
	rotation.y = lerp_angle(rotation.y, desired_body, _blend_weight(delta, _TURN_SPEED))
	_head_aim_yaw = lerpf(_head_aim_yaw, desired_head, _blend_weight(delta, 8.0))
	_head_aim_pitch = lerpf(_head_aim_pitch, desired_pitch, _blend_weight(delta, 8.0))
	_pupil_aim = _pupil_aim.lerp(pupil, _blend_weight(delta, 9.0))


func _update_pose(delta: float, immediate: bool) -> void:
	var w := 1.0 if immediate else _blend_weight(delta, _POSE_SPEED)
	var stand_y := _standing_pelvis_y()
	var seated_y := _seat_height + _pelvis_h * 0.10
	_pelvis.position.y = lerpf(_pelvis.position.y, lerpf(stand_y, seated_y, _sit), w)

	var torso_rot := Vector3(_slump + 0.045 * _sit, 0.0, 0.0)
	var head_rot := Vector3(_head_aim_pitch, _head_aim_yaw, 0.0)
	var l_shoulder_rot := Vector3(0.04, 0.0, -0.09)
	var r_shoulder_rot := Vector3(0.04, 0.0, 0.09)
	var l_elbow_rot := Vector3(0.05, 0.0, 0.0)
	var r_elbow_rot := Vector3(0.05, 0.0, 0.0)
	var shoulder_lift := 0.0

	var seated_hip := _seated_hip_angle()
	var l_hip_rot := Vector3(lerpf(0.0, seated_hip, _sit), 0.0, -0.025)
	var r_hip_rot := Vector3(lerpf(0.0, seated_hip, _sit), 0.0, 0.025)
	var l_knee_rot := Vector3(lerpf(0.0, -seated_hip, _sit), 0.0, 0.0)
	var r_knee_rot := Vector3(lerpf(0.0, -seated_hip, _sit), 0.0, 0.0)
	var l_foot_rot := Vector3.ZERO
	var r_foot_rot := Vector3.ZERO

	if _walking:
		var stride := sin(_walk_phase)
		var counter := sin(_walk_phase + PI)
		l_hip_rot.x = stride * 0.54
		r_hip_rot.x = counter * 0.54
		l_knee_rot.x = maxf(0.0, -stride) * 0.62
		r_knee_rot.x = maxf(0.0, -counter) * 0.62
		l_foot_rot.x = -l_hip_rot.x - l_knee_rot.x + stride * 0.12
		r_foot_rot.x = -r_hip_rot.x - r_knee_rot.x + counter * 0.12
		l_shoulder_rot.x = -stride * 0.43
		r_shoulder_rot.x = -counter * 0.43
		torso_rot.z += sin(_walk_phase * 0.5) * 0.025
		torso_rot.x -= 0.025
		_pelvis.position.y += _walk_bob * 0.018
	else:
		_apply_acting_targets(
			torso_rot, head_rot, l_shoulder_rot, r_shoulder_rot,
			l_elbow_rot, r_elbow_rot, shoulder_lift
		)
		# GDScript passes built-in values by value; receive the acting target bundle.
		var acting := _acting_targets(torso_rot, head_rot, l_shoulder_rot, r_shoulder_rot, l_elbow_rot, r_elbow_rot, shoulder_lift)
		torso_rot = acting.torso
		head_rot = acting.head
		l_shoulder_rot = acting.l_shoulder
		r_shoulder_rot = acting.r_shoulder
		l_elbow_rot = acting.l_elbow
		r_elbow_rot = acting.r_elbow
		shoulder_lift = acting.shoulder_lift

	_smooth_rotation(_torso_root, torso_rot, w)
	_smooth_rotation(_head, head_rot, w)
	_smooth_rotation(_l_shoulder, l_shoulder_rot, w)
	_smooth_rotation(_r_shoulder, r_shoulder_rot, w)
	_smooth_rotation(_l_elbow, l_elbow_rot, w)
	_smooth_rotation(_r_elbow, r_elbow_rot, w)
	_smooth_rotation(_l_hip, l_hip_rot, w)
	_smooth_rotation(_r_hip, r_hip_rot, w)
	_smooth_rotation(_l_knee, l_knee_rot, w)
	_smooth_rotation(_r_knee, r_knee_rot, w)
	_smooth_rotation(_l_foot, l_foot_rot, w)
	_smooth_rotation(_r_foot, r_foot_rot, w)

	var shoulder_y := _body_h * 0.76 + shoulder_lift
	_l_shoulder.position.y = lerpf(_l_shoulder.position.y, shoulder_y, w)
	_r_shoulder.position.y = lerpf(_r_shoulder.position.y, shoulder_y, w)
	_r_pointer.visible = _anim == "pointing" and visible


# Kept as a named hook for easy profiling/extension; values are returned by
# `_acting_targets` because scalar/vector arguments are not reference parameters.
func _apply_acting_targets(
	_torso: Vector3, _head_pose: Vector3, _ls: Vector3, _rs: Vector3,
	_le: Vector3, _re: Vector3, _lift: float
) -> void:
	pass


func _acting_targets(
	torso: Vector3, head_pose: Vector3, ls: Vector3, rs: Vector3,
	le: Vector3, re: Vector3, shoulder_lift: float
) -> Dictionary:
	var idle_gate := pow(maxf(0.0, sin(_t * 0.72 + _phase)), 8.0)
	var breath := sin(_t * (1.55 if _variant == "reed" else 1.85) + _phase)
	# Breathing lives in torso/head only; feet remain planted.
	torso.z += breath * 0.006 * _idle_energy
	head_pose.x += breath * 0.008 * _idle_energy

	match _variant:
		"reed":
			head_pose.x += 0.045 + idle_gate * 0.018
			head_pose.z -= idle_gate * 0.018
		"maris":
			head_pose.z += sin(_t * 0.31 + _phase) * 0.006
		"jinx":
			torso.z += sin(_t * 0.48 + _phase) * 0.018
			head_pose.y += sin(_t * 0.62 + _phase) * 0.018
		"quill":
			torso.x -= 0.018
			head_pose.z += idle_gate * 0.012

	# Emotion remains visible even when the writer selects a restrained animation.
	# These are small posture accents; the named animation below owns the large pose.
	match _expression:
		"joyful", "relieved":
			torso.x -= 0.018
			head_pose.x -= 0.025
		"sad":
			torso.x += 0.075
			head_pose.x += 0.075
		"angry", "determined":
			torso.x -= 0.052
			head_pose.x -= 0.038
		"nervous":
			shoulder_lift += 0.018 + absf(sin(_t * 5.3 + _phase)) * 0.012
			head_pose.z += sin(_t * 3.7 + _phase) * 0.012
		"confused":
			head_pose.z += 0.105
		"embarrassed":
			head_pose.x += 0.055
			head_pose.z -= 0.055
		"suspicious":
			torso.x += 0.025
			head_pose.z += 0.055
		_:
			pass

	match _anim:
		"talking":
			var talk_scale := 0.55 if _variant == "reed" else (1.15 if _variant == "jinx" else 0.78)
			head_pose.x += sin(_t * 4.2 + _phase) * 0.022 * talk_scale
			torso.x += sin(_t * 2.0 + _phase) * 0.008 * talk_scale
			var hand_pulse := pow(maxf(0.0, sin(_t * 1.72 + _phase)), 6.0) * talk_scale
			rs.x -= hand_pulse * 0.28
			rs.z += hand_pulse * 0.16
			re.x -= hand_pulse * 0.58
		"gesture_small":
			var settle := _smoothstep(clampf(_anim_t / 0.22, 0.0, 1.0))
			rs.x = lerpf(rs.x, -0.52, settle)
			rs.z = lerpf(rs.z, 0.27, settle)
			re.x = lerpf(re.x, -1.08, settle)
			re.z = lerpf(re.z, -0.18, settle)
			head_pose.z -= 0.045 * settle
		"arms_crossed":
			ls = Vector3(-0.42, 0.12, 0.73)
			rs = Vector3(-0.42, -0.12, -0.73)
			le = Vector3(-0.18, 0.0, 1.33)
			re = Vector3(-0.18, 0.0, -1.33)
			head_pose.z += 0.035
			torso.x -= 0.018
		"shrug":
			var rise := _smoothstep(clampf(_anim_t / 0.24, 0.0, 1.0))
			shoulder_lift = 0.065 * rise
			ls = Vector3(-0.08, 0.0, -0.62 * rise)
			rs = Vector3(-0.08, 0.0, 0.62 * rise)
			le.x = -0.30 * rise
			re.x = -0.30 * rise
			head_pose.x -= 0.10 * rise
		"pointing":
			rs = Vector3(-1.32, -0.06, 0.04)
			re = Vector3(0.08, 0.0, 0.02)
			ls.x += 0.10
			head_pose.x -= 0.055
		"shocked":
			torso.x -= 0.105
			head_pose.x -= 0.12
			ls = Vector3(-0.28, 0.0, -1.18)
			rs = Vector3(-0.28, 0.0, 1.18)
			le.x = -0.18
			re.x = -0.18
			shoulder_lift = 0.045
		"crying":
			torso.x += 0.19
			head_pose.x += 0.20
			head_pose.z += sin(_t * 5.2 + _phase) * 0.025
			ls = Vector3(-0.62, 0.12, 0.62)
			rs = Vector3(-0.62, -0.12, -0.62)
			le = Vector3(-1.15, 0.0, 0.55)
			re = Vector3(-1.15, 0.0, -0.55)
		"screaming":
			torso.x -= 0.13
			head_pose.x -= 0.19
			ls = Vector3(0.0, 0.0, -2.48)
			rs = Vector3(0.0, 0.0, 2.48)
			le = Vector3(-0.10, 0.0, -0.08)
			re = Vector3(-0.10, 0.0, 0.08)
			shoulder_lift = 0.07
		"wave":
			var wave_phase := sin(_anim_t * 7.6 + _phase * 0.25)
			rs = Vector3(-1.46, -0.10, 0.48 + wave_phase * 0.13)
			re = Vector3(-0.72, 0.0, -0.22 + wave_phase * 0.24)
			head_pose.z -= 0.045
		"nod":
			var nod_gate := 0.5 + 0.5 * sin(_anim_t * 5.8 - PI * 0.5)
			head_pose.x += nod_gate * 0.15
			torso.x += nod_gate * 0.018
		"shake_head":
			var shake := sin(_anim_t * 6.8) * 0.17
			head_pose.y += shake
			head_pose.z += sin(_anim_t * 3.4) * 0.025
		"facepalm":
			torso.x += 0.105
			head_pose.x += 0.18
			head_pose.z -= 0.055
			rs = Vector3(-1.28, -0.08, 0.35)
			re = Vector3(-1.42, 0.0, -0.42)
			ls.x += 0.12
		"hands_on_hips":
			ls = Vector3(-0.12, 0.10, -0.78)
			rs = Vector3(-0.12, -0.10, 0.78)
			le = Vector3(-1.58, 0.0, 0.42)
			re = Vector3(-1.58, 0.0, -0.42)
			torso.x -= 0.045
		"lean_in":
			torso.x -= 0.16
			head_pose.x += 0.07
			ls.x -= 0.16
			rs.x -= 0.16
		"celebrate":
			var cheer := absf(sin(_anim_t * 4.8))
			torso.x -= 0.07
			head_pose.x -= 0.10
			ls = Vector3(-2.42, 0.0, -0.38)
			rs = Vector3(-2.42, 0.0, 0.38)
			le.x = -0.20
			re.x = -0.20
			shoulder_lift = 0.055 + cheer * 0.025
		"recoil":
			torso.x += 0.19
			head_pose.x -= 0.08
			ls = Vector3(-0.44, 0.12, -0.88)
			rs = Vector3(-0.44, -0.12, 0.88)
			le.x = -0.78
			re.x = -0.78
		"double_take":
			var take_phase := sin(minf(_anim_t, 0.78) * 8.0) * exp(-_anim_t * 0.55)
			head_pose.y += take_phase * 0.30
			head_pose.x -= absf(take_phase) * 0.07
		"thinking":
			torso.x += 0.035
			head_pose.x += 0.105
			head_pose.z += 0.085
			rs = Vector3(-0.92, -0.12, 0.30)
			re = Vector3(-1.18, 0.0, -0.32)
			ls = Vector3(0.05, 0.0, -0.16)
		_:
			pass

	return {
		"torso": torso,
		"head": head_pose,
		"l_shoulder": ls,
		"r_shoulder": rs,
		"l_elbow": le,
		"r_elbow": re,
		"shoulder_lift": shoulder_lift,
	}


# -----------------------------------------------------------------------------
# Face animation

func _update_blink() -> void:
	if _blink_started < 0.0 and _t >= _next_blink:
		_blink_started = _t
	if _blink_started >= 0.0:
		var elapsed := _t - _blink_started
		if elapsed >= 0.16:
			_blink_started = -1.0
			var cadence := 2.5 + fposmod(sin(_t * 0.77 + _phase) * 8.0, 2.4)
			_next_blink = _t + cadence
			_blink_amount = 0.0
		else:
			_blink_amount = sin(elapsed / 0.16 * PI)
	else:
		_blink_amount = 0.0


func _update_face(delta: float, immediate: bool) -> void:
	var w := 1.0 if immediate else _blend_weight(delta, 13.0)
	var amp_speed := 19.0 if _mouth_amp_target > _mouth_amp_smooth else 10.0
	_mouth_amp_smooth = lerpf(_mouth_amp_smooth, _mouth_amp_target, 1.0 if immediate else _blend_weight(delta, amp_speed))

	var performed_amp := _mouth_amp_smooth
	if _talking and _mouth_amp_target < 0.025:
		_low_amp_time += delta
		if _low_amp_time > 0.20:
			# Audio-less seed scenes still perform, but with a slow, smoothed syllable
			# envelope rather than the MVP's high-frequency vibration.
			var syllable := maxf(0.0, sin(_t * 12.2 + _phase))
			var secondary := maxf(0.0, sin(_t * 7.1 + _phase * 0.7))
			performed_amp = maxf(performed_amp, (syllable * 0.42 + secondary * 0.16))
	else:
		_low_amp_time = 0.0

	var open_target := 0.0
	if _talking:
		if performed_amp < 0.075:
			open_target = 0.0
		elif performed_amp < 0.28:
			open_target = 0.24
		elif performed_amp < 0.58:
			open_target = 0.52
		else:
			open_target = 0.82
	match _expression:
		"shocked":
			open_target = maxf(open_target, 0.58)
		"screaming":
			open_target = 1.0
		"laughing":
			open_target = maxf(open_target, 0.36 if not _talking else 0.56)
	_mouth_open = lerpf(_mouth_open, open_target, w)

	_update_eyes(w)
	_update_brows(w)
	_update_mouth(w)


func _update_eyes(w: float) -> void:
	var expression_open := 1.0
	match _expression:
		"tired":
			expression_open = 0.68
		"sad", "embarrassed":
			expression_open = 0.74
		"annoyed":
			expression_open = 0.83
		"angry", "determined":
			expression_open = 0.76
		"scheming", "smug", "suspicious":
			expression_open = 0.88
		"laughing", "joyful":
			expression_open = 0.52
		"relieved":
			expression_open = 0.70
		"nervous", "confused":
			expression_open = 1.02
		"crying":
			expression_open = 0.72
		"shocked", "screaming":
			expression_open = 1.12
	var blink := _blink_amount
	if _expression in ["shocked", "screaming"]:
		blink *= 0.12
	var openness := maxf(0.055, expression_open * (1.0 - blink * 0.95))
	var eye_target_scale := Vector3(_eye_w, _eye_h * openness, _eye_depth)
	_l_eye.scale = _l_eye.scale.lerp(eye_target_scale, w)
	_r_eye.scale = _r_eye.scale.lerp(eye_target_scale, w)

	var pupil_x := _pupil_aim.x * 0.20
	var pupil_y := _pupil_aim.y * 0.18
	var pupil_target := Vector3(pupil_x, pupil_y, 0.58)
	_l_pupil.position = _l_pupil.position.lerp(pupil_target, w)
	_r_pupil.position = _r_pupil.position.lerp(pupil_target, w)
	var pupil_open := maxf(0.12, openness)
	var pupil_scale := Vector3(0.40, 0.43 * pupil_open, 0.46)
	_l_pupil.scale = _l_pupil.scale.lerp(pupil_scale, w)
	_r_pupil.scale = _r_pupil.scale.lerp(pupil_scale, w)


func _update_brows(w: float) -> void:
	var ly := _brow_y
	var ry := _brow_y
	var lr := 0.0
	var rr := 0.0
	match _expression:
		"serious":
			lr = -0.16
			rr = 0.16
			ly -= 0.010
			ry -= 0.010
		"annoyed":
			lr = -0.24
			rr = 0.24
			ly -= 0.018
			ry -= 0.018
		"scheming":
			ly += 0.032
			ry -= 0.014
			lr = 0.09
			rr = 0.18
		"earnest":
			lr = 0.15
			rr = -0.15
			ly += 0.012
			ry += 0.012
		"shocked", "screaming":
			ly += 0.052
			ry += 0.052
			lr = 0.04
			rr = -0.04
		"tired":
			lr = 0.11
			rr = -0.11
			ly -= 0.018
			ry -= 0.018
		"smug":
			ly += 0.040
			ry -= 0.012
			lr = 0.08
			rr = -0.02
		"crying":
			lr = 0.23
			rr = -0.23
			ly += 0.012
			ry += 0.012
		"joyful", "relieved":
			lr = 0.13
			rr = -0.13
			ly += 0.018
			ry += 0.018
		"sad":
			lr = 0.25
			rr = -0.25
			ly += 0.020
			ry += 0.020
		"angry":
			lr = -0.34
			rr = 0.34
			ly -= 0.026
			ry -= 0.026
		"nervous":
			lr = 0.20
			rr = -0.08
			ly += 0.025
			ry += 0.006
		"confused", "suspicious":
			lr = 0.16
			rr = 0.20
			ly += 0.034
			ry -= 0.016
		"embarrassed":
			lr = 0.19
			rr = -0.19
			ly += 0.010
			ry += 0.010
		"determined":
			lr = -0.22
			rr = 0.22
			ly -= 0.012
			ry -= 0.012
	_l_brow.position.y = lerpf(_l_brow.position.y, ly, w)
	_r_brow.position.y = lerpf(_r_brow.position.y, ry, w)
	_l_brow.rotation.z = lerp_angle(_l_brow.rotation.z, lr, w)
	_r_brow.rotation.z = lerp_angle(_r_brow.rotation.z, rr, w)


func _update_mouth(w: float) -> void:
	var head_w := _head_r * _head_scale.x
	var head_h := _head_r * _head_scale.y
	var open := _mouth_open
	var width := head_w * lerpf(0.48, 0.62, open)
	var height := head_h * lerpf(0.08, 0.62, open)
	if _expression == "shocked":
		width = head_w * lerpf(0.37, 0.45, open)
		height = head_h * lerpf(0.10, 0.68, open)
	elif _expression == "screaming":
		width = head_w * 0.55
		height = head_h * 0.92
	elif _expression in ["laughing", "joyful"]:
		width = head_w * 0.76
		height *= 0.78
	elif _expression in ["annoyed", "angry", "sad", "crying"]:
		width *= 0.88

	var show_open := open > 0.045
	_mouth.visible = show_open
	_mouth_lip_l.visible = not show_open
	_mouth_lip_r.visible = not show_open
	if show_open:
		_mouth.scale = _mouth.scale.lerp(Vector3(width, maxf(height, 0.018), 0.028), w)
		var open_y := _mouth_y - head_h * open * 0.035
		_mouth.position.y = lerpf(_mouth.position.y, open_y, w)
		return

	var left_rot := 0.0
	var right_rot := 0.0
	var line_y := _mouth_y
	match _expression:
		"laughing", "joyful", "earnest", "relieved":
			left_rot = -0.20
			right_rot = 0.20
			line_y += 0.006
		"smug", "scheming":
			left_rot = -0.03
			right_rot = 0.22
			line_y += 0.004
		"annoyed", "angry", "sad", "crying":
			left_rot = 0.19
			right_rot = -0.19
			line_y -= 0.004
		"tired":
			left_rot = 0.08
			right_rot = -0.08
		"nervous", "embarrassed":
			left_rot = 0.04
			right_rot = 0.15
		"confused", "suspicious":
			left_rot = -0.10
			right_rot = 0.10
		"determined":
			left_rot = 0.03
			right_rot = -0.03
	var half_w := head_w * (0.30 if _expression not in ["laughing", "joyful", "smug"] else 0.35)
	var lip_scale := Vector3(half_w, maxf(0.012, head_h * 0.045), 0.022)
	_mouth_lip_l.scale = _mouth_lip_l.scale.lerp(lip_scale, w)
	_mouth_lip_r.scale = _mouth_lip_r.scale.lerp(lip_scale, w)
	_mouth_lip_l.position.x = lerpf(_mouth_lip_l.position.x, -half_w * 0.48, w)
	_mouth_lip_r.position.x = lerpf(_mouth_lip_r.position.x, half_w * 0.48, w)
	_mouth_lip_l.position.y = lerpf(_mouth_lip_l.position.y, line_y, w)
	_mouth_lip_r.position.y = lerpf(_mouth_lip_r.position.y, line_y, w)
	_mouth_lip_l.rotation.z = lerp_angle(_mouth_lip_l.rotation.z, left_rot, w)
	_mouth_lip_r.rotation.z = lerp_angle(_mouth_lip_r.rotation.z, right_rot, w)


# -----------------------------------------------------------------------------
# Lightweight mesh/material helpers

func _standing_pelvis_y() -> float:
	return _upper_leg_len + _lower_leg_len + _foot_h


func _seated_hip_angle() -> float:
	# Adults plant their feet exactly on the floor for the configured seat height.
	# Quill's shorter legs deliberately dangle, which preserves the child silhouette
	# without faking limb length or moving the actor root below the floor.
	var pelvis_y := _seat_height + _pelvis_h * 0.10
	var vertical_drop_needed := pelvis_y - (_lower_leg_len + _foot_h)
	if vertical_drop_needed >= _upper_leg_len:
		return -1.08
	var ratio := clampf(vertical_drop_needed / _upper_leg_len, 0.22, 0.96)
	return -acos(ratio)


func _material(color: Color, roughness: float) -> StandardMaterial3D:
	var mat := StandardMaterial3D.new()
	mat.albedo_color = color
	mat.roughness = roughness
	mat.metallic = 0.0
	return mat


func _sphere_mesh(radial: int = 12, rings: int = 8) -> SphereMesh:
	var mesh := SphereMesh.new()
	mesh.radius = 0.5
	mesh.height = 1.0
	mesh.radial_segments = radial
	mesh.rings = rings
	return mesh


func _capsule_mesh(radius: float, height: float, radial: int = 10) -> CapsuleMesh:
	var mesh := CapsuleMesh.new()
	mesh.radius = radius
	mesh.height = maxf(height, radius * 2.05)
	mesh.radial_segments = radial
	mesh.rings = 4
	return mesh


func _cylinder_mesh(bottom_radius: float, top_radius: float, height: float, radial: int = 10) -> CylinderMesh:
	var mesh := CylinderMesh.new()
	mesh.bottom_radius = bottom_radius
	mesh.top_radius = top_radius
	mesh.height = height
	mesh.radial_segments = radial
	mesh.rings = 1
	return mesh


func _box_mesh() -> BoxMesh:
	var mesh := BoxMesh.new()
	mesh.size = Vector3.ONE
	return mesh


func _add_mesh(
	parent: Node, node_name: String, mesh: Mesh, material: Material,
	pos: Vector3 = Vector3.ZERO, scale_value: Vector3 = Vector3.ONE,
	rot: Vector3 = Vector3.ZERO
) -> MeshInstance3D:
	var instance := MeshInstance3D.new()
	instance.name = node_name
	instance.mesh = mesh
	instance.material_override = material
	instance.position = pos
	instance.scale = scale_value
	instance.rotation = rot
	parent.add_child(instance)
	return instance


func _blend_weight(delta: float, speed: float) -> float:
	return 1.0 - exp(-delta * speed)


func _smooth_rotation(node: Node3D, target: Vector3, weight: float) -> void:
	node.rotation = Vector3(
		lerp_angle(node.rotation.x, target.x, weight),
		lerp_angle(node.rotation.y, target.y, weight),
		lerp_angle(node.rotation.z, target.z, weight)
	)


func _angle_delta(from: float, to: float) -> float:
	return wrapf(to - from, -PI, PI)


func _smoothstep(value: float) -> float:
	return value * value * (3.0 - 2.0 * value)
