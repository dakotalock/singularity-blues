extends Node3D
class_name CharacterActor
## Procedural blue sitcom person. Distinct silhouette, canned body acting, lip-flap.

var character_id: String = "reed"
var display_name: String = "Reed"

var _pivot: Node3D
var _body: MeshInstance3D
var _head: Node3D
var _head_mesh: MeshInstance3D
var _mouth: MeshInstance3D
var _l_shoulder: Node3D
var _r_shoulder: Node3D
var _l_arm: MeshInstance3D
var _r_arm: MeshInstance3D
var _label: Label3D

var _t: float = 0.0
var _anim_t: float = 0.0
var _anim: String = "idle"
var _talking: bool = false
var _mouth_amp: float = 0.0
var _sit: float = 0.0
var _want_sit: float = 0.0
var _slump: float = 0.0
var _body_h: float = 1.1
var _body_r: float = 0.3
var _head_r: float = 0.24
var _color: Color = Color(0.28, 0.48, 0.78)
var _home: Vector3 = Vector3.ZERO
var _home_yaw: float = 0.0
var _walk_goal: Vector3 = Vector3.ZERO
var _walking: bool = false
var _face_target: Node3D = null
var _rest_ready: bool = false
var _arm_len: float = 0.55
var _variant: String = "reed"
var _scream_level: float = 0.0

const ANIMS := [
	"idle", "talking", "gesture_small", "arms_crossed", "shrug", "pointing",
	"sitting", "walking", "shocked", "crying", "screaming", "enter", "leave"
]


static func make(id: String) -> CharacterActor:
	var c := CharacterActor.new()
	c.character_id = id
	c.name = id.capitalize()
	match id:
		"reed":
			c.display_name = "Reed"
			c._color = Color(0.22, 0.40, 0.66)
			c._body_h = 1.22
			c._body_r = 0.40
			c._head_r = 0.26
			c._slump = 0.18
			c._variant = "reed"
			c._want_sit = 1.0
			c._home = Vector3(-0.75, 0.0, -2.35)
		"maris":
			c.display_name = "Maris"
			c._color = Color(0.30, 0.52, 0.82)
			c._body_h = 1.05
			c._body_r = 0.30
			c._head_r = 0.23
			c._slump = 0.0
			c._variant = "maris"
			c._want_sit = 1.0
			c._home = Vector3(0.78, 0.0, -2.35)
		"jinx":
			c.display_name = "Jinx"
			c._color = Color(0.22, 0.60, 0.88)
			c._body_h = 0.95
			c._body_r = 0.22
			c._head_r = 0.20
			c._slump = -0.04
			c._variant = "jinx"
			c._want_sit = 0.0
			c._home = Vector3(-2.55, 0.0, -0.85)
		"quill":
			c.display_name = "Quill"
			c._color = Color(0.46, 0.70, 0.94)
			c._body_h = 0.72
			c._body_r = 0.28
			c._head_r = 0.30
			c._slump = 0.02
			c._variant = "quill"
			c._want_sit = 0.0
			c._home = Vector3(2.15, 0.0, -0.70)
		_:
			c.display_name = id.capitalize()
			c._home = Vector3.ZERO
	c._walk_goal = c._home
	return c


func _ready() -> void:
	position = _home
	rotation.y = 0.0
	_home_yaw = 0.0
	_sit = _want_sit
	_build()
	_rest_ready = true


func _build() -> void:
	_pivot = Node3D.new()
	_pivot.name = "Pivot"
	add_child(_pivot)
	_pivot.rotation.x = _slump

	var body_mesh := CapsuleMesh.new()
	body_mesh.radius = _body_r
	body_mesh.height = _body_h
	var body_mat := StandardMaterial3D.new()
	body_mat.albedo_color = _color
	body_mat.roughness = 0.62
	_body = MeshInstance3D.new()
	_body.name = "Body"
	_body.mesh = body_mesh
	_body.material_override = body_mat
	_body.position.y = _body_h * 0.5
	_pivot.add_child(_body)

	if _variant == "reed":
		# Heavier midsection.
		var belly := MeshInstance3D.new()
		var sm := SphereMesh.new()
		sm.radius = _body_r * 1.12
		sm.height = _body_r * 1.7
		belly.mesh = sm
		belly.material_override = body_mat
		belly.position = Vector3(0, _body_h * 0.38, 0.06)
		belly.scale = Vector3(1.05, 0.85, 1.15)
		_pivot.add_child(belly)

	var shoulder_y := _body_h - 0.08
	_l_shoulder = Node3D.new()
	_l_shoulder.name = "LShoulder"
	_l_shoulder.position = Vector3(-_body_r - 0.02, shoulder_y, 0.0)
	_pivot.add_child(_l_shoulder)
	_r_shoulder = Node3D.new()
	_r_shoulder.name = "RShoulder"
	_r_shoulder.position = Vector3(_body_r + 0.02, shoulder_y, 0.0)
	_pivot.add_child(_r_shoulder)

	_arm_len = _body_h * 0.52
	_l_arm = _make_arm(_l_shoulder, "LArm")
	_r_arm = _make_arm(_r_shoulder, "RArm")

	_head = Node3D.new()
	_head.name = "Head"
	_head.position = Vector3(0, _body_h + _head_r * 0.85, 0.0)
	_pivot.add_child(_head)

	var hm := SphereMesh.new()
	hm.radius = _head_r
	hm.height = _head_r * 2.0
	_head_mesh = MeshInstance3D.new()
	_head_mesh.name = "HeadMesh"
	_head_mesh.mesh = hm
	_head_mesh.material_override = body_mat
	_head.add_child(_head_mesh)

	_add_face(body_mat)
	_add_variant_bits(body_mat)

	_label = Label3D.new()
	_label.name = "NameLabel"
	_label.text = display_name
	_label.font_size = 42
	_label.outline_size = 10
	_label.outline_modulate = Color(0.05, 0.08, 0.15, 0.9)
	_label.modulate = Color(0.95, 0.95, 1.0)
	_label.pixel_size = 0.0042
	_label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	_label.position = Vector3(0, _body_h + _head_r * 2.0 + 0.18, 0)
	_label.no_depth_test = true
	add_child(_label)


func _make_arm(shoulder: Node3D, n: String) -> MeshInstance3D:
	var cap := CapsuleMesh.new()
	cap.radius = maxf(_body_r * 0.28, 0.055)
	cap.height = _arm_len
	var mi := MeshInstance3D.new()
	mi.name = n
	mi.mesh = cap
	var mat := StandardMaterial3D.new()
	mat.albedo_color = _color.darkened(0.08)
	mat.roughness = 0.62
	mi.material_override = mat
	mi.position = Vector3(0, -_arm_len * 0.5, 0)
	shoulder.add_child(mi)
	var hand := MeshInstance3D.new()
	var hs := SphereMesh.new()
	hs.radius = cap.radius * 1.15
	hand.mesh = hs
	hand.material_override = mat
	hand.position = Vector3(0, -_arm_len * 0.5 - 0.02, 0)
	mi.add_child(hand)
	return mi


func _add_face(body_mat: Material) -> void:
	var eye_w := StandardMaterial3D.new()
	eye_w.albedo_color = Color(0.72, 0.84, 0.95)
	eye_w.roughness = 0.35
	var pupil_m := StandardMaterial3D.new()
	pupil_m.albedo_color = Color(0.08, 0.14, 0.28)
	var mouth_m := StandardMaterial3D.new()
	mouth_m.albedo_color = Color(0.10, 0.16, 0.28)
	mouth_m.roughness = 0.55

	var eye_r := _head_r * 0.22
	var eye_x := _head_r * 0.38
	var eye_y := _head_r * 0.12
	var eye_z := _head_r * 0.82

	for side in [-1.0, 1.0]:
		var eye := MeshInstance3D.new()
		var es := SphereMesh.new()
		es.radius = eye_r
		es.height = eye_r * 2.2
		eye.mesh = es
		eye.material_override = eye_w
		eye.position = Vector3(side * eye_x, eye_y, eye_z)
		eye.scale = Vector3(1.0, 1.15, 0.7)
		_head.add_child(eye)
		var pup := MeshInstance3D.new()
		var ps := SphereMesh.new()
		ps.radius = eye_r * 0.45
		pup.mesh = ps
		pup.material_override = pupil_m
		pup.position = Vector3(side * eye_x, eye_y, eye_z + eye_r * 0.45)
		_head.add_child(pup)

	var brow := MeshInstance3D.new()
	var bb := BoxMesh.new()
	bb.size = Vector3(_head_r * 1.15, _head_r * 0.08, _head_r * 0.18)
	brow.mesh = bb
	brow.material_override = body_mat
	brow.position = Vector3(0, _head_r * 0.42, _head_r * 0.7)
	_head.add_child(brow)

	var mm := BoxMesh.new()
	mm.size = Vector3(_head_r * 0.55, _head_r * 0.16, _head_r * 0.18)
	_mouth = MeshInstance3D.new()
	_mouth.name = "Mouth"
	_mouth.mesh = mm
	_mouth.material_override = mouth_m
	_mouth.position = Vector3(0, -_head_r * 0.32, _head_r * 0.82)
	_head.add_child(_mouth)


func _add_variant_bits(body_mat: Material) -> void:
	match _variant:
		"maris":
			var bun_m := StandardMaterial3D.new()
			bun_m.albedo_color = _color.darkened(0.12)
			var bun := MeshInstance3D.new()
			var bs := SphereMesh.new()
			bs.radius = _head_r * 0.48
			bun.mesh = bs
			bun.material_override = bun_m
			bun.position = Vector3(0, _head_r * 0.72, -_head_r * 0.55)
			_head.add_child(bun)
			var bun2 := MeshInstance3D.new()
			var bs2 := SphereMesh.new()
			bs2.radius = _head_r * 0.32
			bun2.mesh = bs2
			bun2.material_override = bun_m
			bun2.position = Vector3(0, _head_r * 1.05, -_head_r * 0.25)
			_head.add_child(bun2)
		"jinx":
			var tuft_m := StandardMaterial3D.new()
			tuft_m.albedo_color = _color.lightened(0.08)
			var tuft := MeshInstance3D.new()
			var ts := SphereMesh.new()
			ts.radius = _head_r * 0.28
			tuft.mesh = ts
			tuft.material_override = tuft_m
			tuft.position = Vector3(_head_r * 0.85, _head_r * 0.55, 0.05)
			tuft.scale = Vector3(1.6, 0.55, 0.5)
			tuft.rotation_degrees = Vector3(0, 0, 28)
			_head.add_child(tuft)
			# Lean silhouette: extra skinny neck marker.
			var neck := MeshInstance3D.new()
			var nc := CapsuleMesh.new()
			nc.radius = _body_r * 0.35
			nc.height = 0.16
			neck.mesh = nc
			neck.material_override = body_mat
			neck.position = Vector3(0, _body_h + 0.02, 0)
			_pivot.add_child(neck)
		"quill":
			var gmat := StandardMaterial3D.new()
			gmat.albedo_color = Color(0.12, 0.16, 0.22)
			gmat.roughness = 0.3
			var gx := _head_r * 0.28
			var gz := _head_r * 0.88
			var gy := _head_r * 0.10
			for side in [-1.0, 1.0]:
				var lens := MeshInstance3D.new()
				var bx := BoxMesh.new()
				bx.size = Vector3(_head_r * 0.28, _head_r * 0.18, 0.03)
				lens.mesh = bx
				lens.material_override = gmat
				lens.position = Vector3(side * gx, gy, gz)
				_head.add_child(lens)
			var bridge := MeshInstance3D.new()
			var br := BoxMesh.new()
			br.size = Vector3(_head_r * 0.22, 0.025, 0.025)
			bridge.mesh = br
			bridge.material_override = gmat
			bridge.position = Vector3(0, gy, gz)
			_head.add_child(bridge)
		"reed":
			# Heavier brow.
			pass


func total_height() -> float:
	return _body_h + _head_r * 2.0


func head_world() -> Vector3:
	if _head:
		return _head.global_position
	return global_position + Vector3(0, total_height() * 0.85, 0)


func play_anim(anim: String) -> void:
	if anim == "" or not (anim in ANIMS):
		anim = "idle"
	_anim = anim
	_anim_t = 0.0
	match anim:
		"sitting":
			_want_sit = 1.0
			_walking = false
		"walking", "enter", "leave":
			_want_sit = 0.0
			_walking = true
			if anim == "enter":
				global_position = Vector3(-5.2, 0.0, 2.2)
				_walk_goal = _home
			elif anim == "leave":
				_walk_goal = Vector3(5.4, 0.0, 2.0)
			else:
				_walk_goal = _home
		"idle":
			_walking = false
			if character_id in ["reed", "maris"]:
				_want_sit = 1.0
			else:
				_want_sit = 0.0
		_:
			_walking = false
			if anim != "sitting" and character_id in ["jinx", "quill"]:
				_want_sit = 0.0


func set_talking(on: bool) -> void:
	_talking = on
	if on and _anim in ["idle", "sitting"]:
		play_anim("talking")
	if not on:
		_mouth_amp = 0.0


func set_mouth_amp(amp: float) -> void:
	_mouth_amp = clampf(amp, 0.0, 1.0)


func face_toward(n: Node3D) -> void:
	_face_target = n


func face_id_map(cast: Dictionary, target_id: Variant) -> void:
	if target_id == null or str(target_id) == "" or str(target_id) == character_id:
		_face_target = null
		return
	var key := str(target_id)
	if cast.has(key):
		_face_target = cast[key]
	else:
		_face_target = null


func reset_home() -> void:
	_walk_goal = _home
	_walking = false
	global_position = _home
	rotation.y = _home_yaw
	play_anim("idle")
	set_talking(false)


func _process(delta: float) -> void:
	if not _rest_ready:
		return
	_t += delta
	_anim_t += delta
	_sit = lerpf(_sit, _want_sit, 1.0 - exp(-delta * 6.0))

	# Reset to rest pose each frame, then layer acting.
	_body.rotation = Vector3.ZERO
	_head.rotation = Vector3.ZERO
	_l_shoulder.rotation = Vector3(0.18, 0.0, 0.18)
	_r_shoulder.rotation = Vector3(0.18, 0.0, -0.18)
	_pivot.rotation.x = _slump
	_pivot.position.y = 0.0
	_mouth.scale = Vector3.ONE

	if _walking:
		_do_walk(delta)

	# Sink into couch when sitting (no legs — cheap set).
	position.y = lerpf(0.0, -0.42, _sit)
	if _sit > 0.2:
		_pivot.rotation.x = _slump - 0.12 * _sit
		_l_shoulder.rotation = Vector3(0.55, 0.1, 0.35)
		_r_shoulder.rotation = Vector3(0.55, -0.1, -0.35)

	match _anim:
		"idle":
			_apply_idle()
		"talking":
			_apply_talking()
		"gesture_small":
			_apply_gesture()
		"arms_crossed":
			_apply_crossed()
		"shrug":
			_apply_shrug()
		"pointing":
			_apply_point()
		"sitting":
			_apply_idle()
		"walking", "enter", "leave":
			_apply_walk_pose()
		"shocked":
			_apply_shocked()
		"crying":
			_apply_crying()
		"screaming":
			_apply_scream()
		_:
			_apply_idle()

	if _talking:
		_apply_mouth()
	else:
		_mouth.scale = Vector3(1.0, 0.35, 1.0)

	_turn_to_face(delta)


func _apply_idle() -> void:
	_pivot.position.y += sin(_t * 2.2) * 0.012
	_head.rotation.y = sin(_t * 0.7) * 0.08
	_head.rotation.x = sin(_t * 1.1) * 0.04
	if _sit < 0.3:
		_l_shoulder.rotation.x = 0.18 + sin(_t * 2.2) * 0.04
		_r_shoulder.rotation.x = 0.18 + sin(_t * 2.2 + 0.4) * 0.04


func _apply_talking() -> void:
	_pivot.position.y += sin(_t * 5.0) * 0.018
	_head.rotation.x = sin(_t * 6.0) * 0.08
	_head.rotation.y = sin(_t * 2.5) * 0.10
	if _sit > 0.5:
		_r_shoulder.rotation.x = 0.45 + sin(_t * 5.5) * 0.12
		_r_shoulder.rotation.z = -0.12
		_l_shoulder.rotation.x = 0.5 + sin(_t * 3.0) * 0.06
	else:
		_r_shoulder.rotation.x = 0.05 + sin(_t * 5.5) * 0.25
		_r_shoulder.rotation.z = -0.25
		_l_shoulder.rotation.x = 0.2 + sin(_t * 3.0) * 0.08


func _apply_gesture() -> void:
	var ph := sin(_anim_t * 7.0)
	_r_shoulder.rotation.x = -0.2 + ph * 0.55
	_r_shoulder.rotation.z = -0.5
	_head.rotation.y = ph * 0.12
	_pivot.position.y += absf(ph) * 0.02


func _apply_crossed() -> void:
	_l_shoulder.rotation = Vector3(0.95, 0.6, 0.85)
	_r_shoulder.rotation = Vector3(0.95, -0.6, -0.85)
	_head.rotation.z = 0.05
	_pivot.rotation.x = _slump + 0.04


func _apply_shrug() -> void:
	var up := minf(_anim_t * 4.0, 1.0)
	if _anim_t > 0.7:
		up = maxf(1.0 - (_anim_t - 0.7) * 2.0, 0.15)
	_l_shoulder.rotation = Vector3(-0.15, 0.0, 0.55 * up)
	_r_shoulder.rotation = Vector3(-0.15, 0.0, -0.55 * up)
	_head.rotation.x = -0.12 * up
	_pivot.position.y += 0.04 * up


func _apply_point() -> void:
	_r_shoulder.rotation = Vector3(-1.15, -0.15, -0.15)
	_l_shoulder.rotation = Vector3(0.35, 0.1, 0.25)
	_head.rotation.x = -0.08
	_pivot.rotation.y = 0.06


func _apply_walk_pose() -> void:
	var w := _t * 9.0
	_pivot.position.y += absf(sin(w)) * 0.05
	_l_shoulder.rotation.x = sin(w) * 0.7
	_r_shoulder.rotation.x = -sin(w) * 0.7
	_body.rotation.y = sin(w) * 0.08


func _apply_shocked() -> void:
	_pivot.rotation.x = _slump - 0.22
	_head.rotation.x = -0.28
	_l_shoulder.rotation = Vector3(-1.4, 0.2, 0.7)
	_r_shoulder.rotation = Vector3(-1.4, -0.2, -0.7)
	_mouth.scale = Vector3(1.15, 2.4, 1.2)
	_pivot.position.y += 0.06


func _apply_crying() -> void:
	_pivot.rotation.x = _slump + 0.28
	_head.rotation.x = 0.35
	_head.rotation.z = sin(_t * 10.0) * 0.12
	_l_shoulder.rotation = Vector3(0.9, 0.4, 0.5)
	_r_shoulder.rotation = Vector3(0.9, -0.4, -0.5)
	_mouth.scale = Vector3(0.8, 1.6, 1.0)
	_pivot.position.y += sin(_t * 8.0) * 0.01


func _apply_scream() -> void:
	_pivot.rotation.x = _slump - 0.18
	_head.rotation.x = -0.45
	_l_shoulder.rotation = Vector3(-1.6, 0.0, 0.9)
	_r_shoulder.rotation = Vector3(-1.6, 0.0, -0.9)
	_mouth.scale = Vector3(1.3, 3.2 + sin(_t * 20.0) * 0.4, 1.4)
	_pivot.position.y += 0.08 + sin(_t * 18.0) * 0.02


func _apply_mouth() -> void:
	var flap := _mouth_amp
	if flap < 0.05:
		flap = 0.35 + absf(sin(_t * 14.0)) * 0.65
		flap *= 0.7 + 0.3 * absf(sin(_t * 23.0))
	_mouth.scale = Vector3(1.0 + flap * 0.15, 0.4 + flap * 2.2, 1.0)


func _do_walk(delta: float) -> void:
	var to := _walk_goal - Vector3(global_position.x, _walk_goal.y, global_position.z)
	to.y = 0.0
	var dist := to.length()
	if dist < 0.08:
		global_position.x = _walk_goal.x
		global_position.z = _walk_goal.z
		_walking = false
		if _anim in ["walking", "enter"]:
			play_anim("idle")
		return
	var step := to.normalized() * 1.55 * delta
	global_position += step
	var yaw := atan2(to.x, to.z)
	rotation.y = lerp_angle(rotation.y, yaw, 1.0 - exp(-delta * 8.0))


func _turn_to_face(delta: float) -> void:
	if _walking:
		return
	var want := _home_yaw
	if _face_target != null and is_instance_valid(_face_target):
		var to: Vector3 = _face_target.global_position - global_position
		to.y = 0.0
		if to.length() > 0.05:
			want = atan2(to.x, to.z)
	rotation.y = lerp_angle(rotation.y, want, 1.0 - exp(-delta * 5.0))
