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


func _anchor(pos: Vector3, yaw: float = 0.0, seated: bool = false, seat_height: float = 0.0) -> Dictionary:
	return {
		"position": pos,
		"yaw": yaw,
		"seated": seated,
		"seat_height": seat_height,
	}


func _make_materials() -> void:
	# Warm neutrals and woods keep the four blue actors separated from the set.
	_materials = {
		"wall_cream": _mat(Color("e6d1ae"), 0.96),
		"wall_shadow": _mat(Color("b9895f"), 0.92),
		"trim": _mat(Color("f2e4c8"), 0.72),
		"ceiling": _mat(Color("f4ead8"), 0.98),
		"floor": _mat(Color("704427"), 0.72),
		"floor_dark": _mat(Color("42291b"), 0.82),
		"wood": _mat(Color("55331f"), 0.60),
		"wood_light": _mat(Color("8b5a32"), 0.66),
		"wood_edge": _mat(Color("342118"), 0.58),
		"couch": _mat(Color("a85f37"), 0.90),
		"couch_dark": _mat(Color("6f3928"), 0.92),
		"couch_light": _mat(Color("c47a4b"), 0.94),
		"chair": _mat(Color("76603d"), 0.92),
		"chair_light": _mat(Color("9a8055"), 0.94),
		"rug_outer": _mat(Color("8d3f32"), 0.98),
		"rug_mid": _mat(Color("d08a4d"), 0.98),
		"rug_inner": _mat(Color("5f3330"), 0.98),
		"paper": _mat(Color("f3ead4"), 0.96),
		"paper_old": _mat(Color("dec792"), 0.96),
		"ink": _mat(Color("3c3029"), 0.84),
		"green_bill": _mat(Color("7b9868"), 0.90),
		"ceramic": _mat(Color("d58b4c"), 0.64),
		"metal": _mat(Color("aeb1ae"), 0.30, 0.22),
		"metal_dark": _mat(Color("4c4e4d"), 0.36, 0.18),
		"appliance": _mat(Color("e3e0d4"), 0.42, 0.08),
		"black": _mat(Color("161719"), 0.45),
		"tv_screen": _mat(Color("243b50"), 0.34, 0.0, Color("315f79"), 0.48),
		"window": _mat(Color("85b9cf"), 0.30, 0.0, Color("92cde5"), 0.62),
		"orange_glow": _mat(Color("f0a34e"), 0.38, 0.0, Color("ff9b35"), 1.25),
		"green_glow": _mat(Color("5bb26c"), 0.38, 0.0, Color("58c873"), 0.90),
		"plant": _mat(Color("426f3d"), 0.92),
		"plant_light": _mat(Color("6e9350"), 0.94),
		"pot": _mat(Color("a65334"), 0.82),
		"shade": _mat(Color("efc773"), 0.80, 0.0, Color("ffd98b"), 0.32),
		"picture_blue": _mat(Color("4f7894"), 0.86),
		"picture_gold": _mat(Color("d3a858"), 0.86),
		"picture_plum": _mat(Color("76536f"), 0.88),
		"blue_reed": _mat(Color("41699a"), 0.80),
		"blue_maris": _mat(Color("4c83b5"), 0.80),
		"blue_jinx": _mat(Color("3d96c0"), 0.80),
		"blue_quill": _mat(Color("7db4d1"), 0.80),
	}


func _mat(
	color: Color,
	roughness: float = 0.8,
	metallic: float = 0.0,
	emission: Color = Color(0.0, 0.0, 0.0, 1.0),
	emission_energy: float = 0.0
) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = roughness
	material.metallic = metallic
	if emission_energy > 0.0:
		material.emission_enabled = true
		material.emission = emission
		material.emission_energy_multiplier = emission_energy
	return material


func _group(parent: Node, group_name: String, pos: Vector3 = Vector3.ZERO, rot_deg: Vector3 = Vector3.ZERO) -> Node3D:
	var group := Node3D.new()
	group.name = group_name
	group.position = pos
	group.rotation_degrees = rot_deg
	parent.add_child(group)
	return group


func _mesh(
	parent: Node,
	mesh_name: String,
	shape: Mesh,
	pos: Vector3,
	material: Material,
	rot_deg: Vector3 = Vector3.ZERO,
	scale_value: Vector3 = Vector3.ONE,
	casts_shadow: bool = true
) -> MeshInstance3D:
	var instance := MeshInstance3D.new()
	instance.name = mesh_name
	instance.mesh = shape
	instance.position = pos
	instance.rotation_degrees = rot_deg
	instance.scale = scale_value
	instance.material_override = material
	if not casts_shadow:
		instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	parent.add_child(instance)
	return instance


func _box(
	parent: Node,
	mesh_name: String,
	size: Vector3,
	pos: Vector3,
	material: Material,
	rot_deg: Vector3 = Vector3.ZERO,
	casts_shadow: bool = true
) -> MeshInstance3D:
	var shape := BoxMesh.new()
	shape.size = size
	return _mesh(parent, mesh_name, shape, pos, material, rot_deg, Vector3.ONE, casts_shadow)


func _cylinder(
	parent: Node,
	mesh_name: String,
	top_radius: float,
	bottom_radius: float,
	height: float,
	pos: Vector3,
	material: Material,
	rot_deg: Vector3 = Vector3.ZERO,
	scale_value: Vector3 = Vector3.ONE,
	segments: int = 12,
	casts_shadow: bool = true
) -> MeshInstance3D:
	var shape := CylinderMesh.new()
	shape.top_radius = top_radius
	shape.bottom_radius = bottom_radius
	shape.height = height
	shape.radial_segments = segments
	shape.rings = 1
	return _mesh(parent, mesh_name, shape, pos, material, rot_deg, scale_value, casts_shadow)


func _sphere(
	parent: Node,
	mesh_name: String,
	radius: float,
	pos: Vector3,
	material: Material,
	scale_value: Vector3 = Vector3.ONE,
	rot_deg: Vector3 = Vector3.ZERO,
	casts_shadow: bool = true
) -> MeshInstance3D:
	var shape := SphereMesh.new()
	shape.radius = radius
	shape.height = radius * 2.0
	shape.radial_segments = 12
	shape.rings = 6
	return _mesh(parent, mesh_name, shape, pos, material, rot_deg, scale_value, casts_shadow)


func _label(
	parent: Node,
	label_name: String,
	text: String,
	pos: Vector3,
	color: Color,
	font_size: int = 28,
	pixel_size: float = 0.003
) -> Label3D:
	var label := Label3D.new()
	label.name = label_name
	label.text = text
	label.position = pos
	label.font_size = font_size
	label.pixel_size = pixel_size
	label.modulate = color
	label.outline_size = 3
	label.outline_modulate = Color(0.95, 0.90, 0.80, 0.28)
	parent.add_child(label)
	return label


func _build_environment() -> void:
	var environment := Environment.new()
	environment.background_mode = Environment.BG_COLOR
	environment.background_color = Color("211a16")
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color("d8b581")
	environment.ambient_light_energy = 0.47
	environment.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	environment.tonemap_exposure = 1.02
	environment.glow_enabled = false
	environment.ssao_enabled = false
	environment.adjustment_enabled = true
	environment.adjustment_saturation = 1.06
	environment.adjustment_contrast = 1.03
	var world := WorldEnvironment.new()
	world.name = "WarmSitcomEnvironment"
	world.environment = environment
	add_child(world)


func _build_shell() -> void:
	var shell := _group(self, "ArchitecturalShell")
	var floor_mat: Material = _materials["floor"]
	var floor_dark: Material = _materials["floor_dark"]
	var cream: Material = _materials["wall_cream"]
	var lower: Material = _materials["wall_shadow"]
	var trim: Material = _materials["trim"]

	# Open-front three-wall soundstage, deliberately shallow for reliable camera coverage.
	_box(shell, "Floor", Vector3(10.9, 0.12, 8.15), Vector3(0.0, -0.06, -0.25), floor_mat)
	_box(shell, "Ceiling", Vector3(10.9, 0.10, 8.15), Vector3(0.0, 3.62, -0.25), _materials["ceiling"])
	_box(shell, "LeftWall", Vector3(0.14, 3.62, 8.15), Vector3(-5.45, 1.81, -0.25), cream)
	_box(shell, "RightWall", Vector3(0.14, 3.62, 8.15), Vector3(5.45, 1.81, -0.25), cream)
	_box(shell, "LeftWainscot", Vector3(0.16, 1.08, 8.15), Vector3(-5.37, 0.54, -0.25), lower)
	_box(shell, "RightWainscot", Vector3(0.16, 1.08, 8.15), Vector3(5.37, 0.54, -0.25), lower)

	# Back wall is segmented around a real kitchen pass-through and the front door.
	_box(shell, "BackUnderPass", Vector3(2.95, 1.12, 0.14), Vector3(-3.925, 0.56, -4.15), lower)
	_box(shell, "BackOverPass", Vector3(2.95, 0.67, 0.14), Vector3(-3.925, 3.285, -4.15), cream)
	_box(shell, "BackPassLeftPost", Vector3(0.35, 2.50, 0.14), Vector3(-5.225, 2.37, -4.15), cream)
	_box(shell, "BackCenterLower", Vector3(6.50, 1.12, 0.14), Vector3(0.80, 0.56, -4.15), lower)
	_box(shell, "BackCenterUpper", Vector3(6.50, 2.50, 0.14), Vector3(0.80, 2.37, -4.15), cream)
	_box(shell, "BackDoorHeader", Vector3(1.10, 1.02, 0.14), Vector3(4.60, 3.11, -4.15), cream)
	_box(shell, "BackDoorRightPost", Vector3(0.25, 3.62, 0.14), Vector3(5.275, 1.81, -4.15), cream)

	# Floor-board seams provide scale without textures.
	for x in [-4.25, -2.85, -1.45, -0.05, 1.35, 2.75, 4.15]:
		_box(shell, "FloorSeam_%s" % str(x), Vector3(0.018, 0.008, 8.0), Vector3(x, 0.008, -0.20), floor_dark, Vector3.ZERO, false)
	for z in [-3.15, -1.95, -0.75, 0.45, 1.65, 2.85]:
		_box(shell, "FloorJoin_%s" % str(z), Vector3(10.7, 0.006, 0.012), Vector3(0.0, 0.010, z), floor_dark, Vector3.ZERO, false)

	# Baseboard and chair rail visually tie the deliberately modular walls together.
	_box(shell, "BackBase", Vector3(9.46, 0.14, 0.20), Vector3(-0.67, 0.10, -4.05), trim)
	_box(shell, "LeftBase", Vector3(0.20, 0.14, 8.0), Vector3(-5.34, 0.10, -0.22), trim)
	_box(shell, "RightBase", Vector3(0.20, 0.14, 8.0), Vector3(5.34, 0.10, -0.22), trim)
	_box(shell, "CenterChairRail", Vector3(6.50, 0.08, 0.18), Vector3(0.80, 1.09, -4.04), trim)
	_box(shell, "LeftChairRail", Vector3(0.18, 0.08, 8.0), Vector3(-5.33, 1.09, -0.22), trim)
	_box(shell, "RightChairRail", Vector3(0.18, 0.08, 8.0), Vector3(5.33, 1.09, -0.22), trim)

	_build_front_door(shell)
	_build_side_window(shell)


func _build_front_door(parent: Node) -> void:
	var door := _group(parent, "FrontDoor", Vector3(4.60, 0.0, -4.065))
	_box(door, "DoorSlab", Vector3(1.10, 2.58, 0.12), Vector3(0.0, 1.29, 0.0), _materials["couch_dark"])
	_box(door, "TopPanel", Vector3(0.78, 0.78, 0.035), Vector3(0.0, 1.90, 0.08), _materials["wood_light"])
	_box(door, "BottomPanel", Vector3(0.78, 0.83, 0.035), Vector3(0.0, 0.73, 0.08), _materials["wood_light"])
	_box(door, "LeftFrame", Vector3(0.10, 2.72, 0.20), Vector3(-0.62, 1.36, 0.02), _materials["trim"])
	_box(door, "RightFrame", Vector3(0.10, 2.72, 0.20), Vector3(0.62, 1.36, 0.02), _materials["trim"])
	_box(door, "TopFrame", Vector3(1.34, 0.10, 0.20), Vector3(0.0, 2.67, 0.02), _materials["trim"])
	_sphere(door, "Knob", 0.065, Vector3(-0.36, 1.16, 0.13), _materials["picture_gold"], Vector3(1.0, 1.0, 0.65))
	_box(door, "WelcomeStep", Vector3(1.36, 0.06, 0.42), Vector3(0.0, 0.03, 0.26), _materials["wood_edge"])


func _build_side_window(parent: Node) -> void:
	var window := _group(parent, "SideWindow", Vector3(5.355, 0.0, 0.35), Vector3(0.0, 90.0, 0.0))
	_box(window, "Glow", Vector3(1.56, 1.42, 0.035), Vector3(0.0, 2.18, 0.0), _materials["window"], Vector3.ZERO, false)
	_box(window, "FrameTop", Vector3(1.82, 0.09, 0.12), Vector3(0.0, 2.94, 0.03), _materials["trim"])
	_box(window, "FrameBottom", Vector3(1.92, 0.12, 0.24), Vector3(0.0, 1.41, 0.08), _materials["trim"])
	_box(window, "FrameLeft", Vector3(0.09, 1.56, 0.12), Vector3(-0.86, 2.18, 0.03), _materials["trim"])
	_box(window, "FrameRight", Vector3(0.09, 1.56, 0.12), Vector3(0.86, 2.18, 0.03), _materials["trim"])
	_box(window, "MuntinH", Vector3(1.62, 0.055, 0.08), Vector3(0.0, 2.18, 0.05), _materials["trim"])
	_box(window, "MuntinV", Vector3(0.055, 1.45, 0.08), Vector3(0.0, 2.18, 0.05), _materials["trim"])


func _build_kitchen() -> void:
	var kitchen := _group(self, "KitchenPassThrough")
	var cream: Material = _materials["wall_cream"]
	var trim: Material = _materials["trim"]
	var wood: Material = _materials["wood_light"]

	# A shallow alcove behind the opening reads as a second room without another set.
	_box(kitchen, "KitchenFloor", Vector3(3.0, 0.08, 1.35), Vector3(-3.82, 0.0, -4.78), _materials["floor_dark"])
	_box(kitchen, "KitchenRearWall", Vector3(3.0, 3.2, 0.10), Vector3(-3.82, 1.60, -5.40), _materials["wall_shadow"])
	_box(kitchen, "KitchenCeiling", Vector3(3.0, 0.08, 1.35), Vector3(-3.82, 3.18, -4.78), cream)

	# Pass-through frame and substantial counter ledge.
	_box(kitchen, "PassSill", Vector3(2.74, 0.13, 0.62), Vector3(-3.74, 1.16, -4.00), wood)
	_box(kitchen, "PassLeftTrim", Vector3(0.11, 1.90, 0.20), Vector3(-5.03, 2.10, -4.04), trim)
	_box(kitchen, "PassRightTrim", Vector3(0.11, 1.90, 0.20), Vector3(-2.45, 2.10, -4.04), trim)
	_box(kitchen, "PassTopTrim", Vector3(2.69, 0.11, 0.20), Vector3(-3.74, 3.00, -4.04), trim)

	# Cabinet faces below the sill and upper cabinets in the visible alcove.
	_box(kitchen, "LowerCabinetBank", Vector3(1.72, 0.94, 0.52), Vector3(-3.34, 0.59, -4.02), _materials["wood"])
	for x in [-3.86, -3.28, -2.70]:
		_box(kitchen, "LowerDoor_%s" % str(x), Vector3(0.49, 0.76, 0.025), Vector3(x, 0.60, -3.74), wood)
		_sphere(kitchen, "LowerKnob_%s" % str(x), 0.025, Vector3(x + 0.15, 0.64, -3.71), _materials["metal_dark"], Vector3.ONE, Vector3.ZERO, false)
	_box(kitchen, "UpperCabinetBank", Vector3(1.48, 0.78, 0.30), Vector3(-3.32, 2.35, -5.18), _materials["wood"])
	_box(kitchen, "UpperDoorL", Vector3(0.63, 0.64, 0.025), Vector3(-3.69, 2.35, -5.00), wood)
	_box(kitchen, "UpperDoorR", Vector3(0.63, 0.64, 0.025), Vector3(-2.95, 2.35, -5.00), wood)

	_build_refrigerator(kitchen)
	_build_toaster(kitchen)


func _build_refrigerator(parent: Node) -> void:
	var fridge := _group(parent, "Refrigerator", Vector3(-4.62, 0.0, -4.86))
	_box(fridge, "Body", Vector3(0.78, 2.02, 0.68), Vector3(0.0, 1.01, 0.0), _materials["appliance"])
	_box(fridge, "FreezerFace", Vector3(0.69, 0.51, 0.025), Vector3(0.0, 1.70, 0.355), _materials["metal"])
	_box(fridge, "DoorFace", Vector3(0.69, 1.24, 0.025), Vector3(0.0, 0.80, 0.355), _materials["appliance"])
	_box(fridge, "FreezerHandle", Vector3(0.055, 0.31, 0.06), Vector3(0.27, 1.70, 0.40), _materials["metal_dark"])
	_box(fridge, "DoorHandle", Vector3(0.055, 0.56, 0.06), Vector3(0.27, 0.93, 0.40), _materials["metal_dark"])
	_box(fridge, "VetoNote", Vector3(0.29, 0.22, 0.012), Vector3(-0.13, 1.25, 0.38), _materials["picture_gold"], Vector3(0.0, 0.0, -4.0), false)
	_label(fridge, "VetoLabel", "DINNER\nVETO", Vector3(-0.13, 1.25, 0.397), Color("44351f"), 23, 0.0024)


func _build_toaster(parent: Node) -> void:
	# The recurring-object hero prop: centered in the pass-through, readable in a wide.
	var toaster := _group(parent, "THE_TOASTER", Vector3(-2.84, 1.225, -3.86))
	_box(toaster, "FeetL", Vector3(0.09, 0.055, 0.10), Vector3(-0.21, 0.025, 0.0), _materials["metal_dark"])
	_box(toaster, "FeetR", Vector3(0.09, 0.055, 0.10), Vector3(0.21, 0.025, 0.0), _materials["metal_dark"])
	_box(toaster, "Body", Vector3(0.66, 0.38, 0.40), Vector3(0.0, 0.245, 0.0), _materials["metal"])
	_box(toaster, "WarmSide", Vector3(0.055, 0.31, 0.33), Vector3(-0.315, 0.25, 0.0), _materials["orange_glow"], Vector3.ZERO, false)
	_box(toaster, "FrontInset", Vector3(0.48, 0.22, 0.018), Vector3(0.0, 0.235, 0.21), _materials["appliance"])
	_box(toaster, "SlotA", Vector3(0.43, 0.018, 0.055), Vector3(0.0, 0.445, -0.085), _materials["black"], Vector3.ZERO, false)
	_box(toaster, "SlotB", Vector3(0.43, 0.018, 0.055), Vector3(0.0, 0.445, 0.085), _materials["black"], Vector3.ZERO, false)
	_cylinder(toaster, "LeverStem", 0.022, 0.022, 0.25, Vector3(0.39, 0.22, 0.05), _materials["metal_dark"], Vector3.ZERO, Vector3.ONE, 8)
	_box(toaster, "LeverGrip", Vector3(0.12, 0.075, 0.09), Vector3(0.39, 0.34, 0.05), _materials["couch_dark"])
	_sphere(toaster, "StatusLamp", 0.030, Vector3(-0.17, 0.20, 0.232), _materials["orange_glow"], Vector3(1.0, 0.75, 0.32), Vector3.ZERO, false)
	# A quiet halo tile makes the silhouette recur without turning it into an altar.
	_box(parent, "ToasterBacksplash", Vector3(0.96, 0.72, 0.025), Vector3(-2.84, 1.64, -4.155), _materials["picture_gold"], Vector3.ZERO, false)


func _build_furniture() -> void:
	var furniture := _group(self, "Furniture")
	_build_rug(furniture)
	_build_couch(furniture)
	_build_armchair(furniture)
	_build_coffee_table(furniture)
	_build_tv(furniture)


func _build_rug(parent: Node) -> void:
	var rug := _group(parent, "LayeredRug", Vector3(0.0, 0.0, -1.18))
	_cylinder(rug, "Outer", 1.0, 1.0, 0.028, Vector3(0.0, 0.028, 0.0), _materials["rug_outer"], Vector3.ZERO, Vector3(2.70, 1.0, 1.35), 24, false)
	_cylinder(rug, "Middle", 1.0, 1.0, 0.020, Vector3(0.0, 0.048, 0.0), _materials["rug_mid"], Vector3.ZERO, Vector3(2.35, 1.0, 1.08), 24, false)
	_cylinder(rug, "Center", 1.0, 1.0, 0.018, Vector3(0.0, 0.063, 0.0), _materials["rug_inner"], Vector3.ZERO, Vector3(1.72, 1.0, 0.72), 24, false)


func _build_couch(parent: Node) -> void:
	var couch := _group(parent, "MainCouch", Vector3(0.0, 0.0, -2.80))
	var couch_mat: Material = _materials["couch"]
	var dark: Material = _materials["couch_dark"]
	var light: Material = _materials["couch_light"]
	_box(couch, "Base", Vector3(4.05, 0.38, 1.12), Vector3(0.0, 0.29, 0.0), dark)
	_box(couch, "FrontRail", Vector3(3.78, 0.25, 0.13), Vector3(0.0, 0.36, 0.58), couch_mat)
	_box(couch, "Back", Vector3(4.08, 0.84, 0.27), Vector3(0.0, 0.86, -0.51), couch_mat, Vector3(-4.0, 0.0, 0.0))
	_box(couch, "LeftArm", Vector3(0.33, 0.64, 1.18), Vector3(-2.17, 0.54, 0.0), couch_mat)
	_box(couch, "RightArm", Vector3(0.33, 0.64, 1.18), Vector3(2.17, 0.54, 0.0), couch_mat)
	_cylinder(couch, "LeftArmCap", 0.17, 0.17, 1.04, Vector3(-2.17, 0.86, 0.0), light, Vector3(90.0, 0.0, 0.0), Vector3.ONE, 10)
	_cylinder(couch, "RightArmCap", 0.17, 0.17, 1.04, Vector3(2.17, 0.86, 0.0), light, Vector3(90.0, 0.0, 0.0), Vector3.ONE, 10)

	for i in 3:
		var x := -1.22 + float(i) * 1.22
		_box(couch, "SeatCushion_%d" % i, Vector3(1.14, 0.15, 0.91), Vector3(x, 0.525, 0.07), light)
		_box(couch, "BackCushion_%d" % i, Vector3(1.12, 0.57, 0.17), Vector3(x, 0.88, -0.33), couch_mat, Vector3(-7.0, 0.0, 0.0))
		_box(couch, "SeatSeam_%d" % i, Vector3(0.018, 0.012, 0.82), Vector3(x + 0.58, 0.606, 0.08), dark, Vector3.ZERO, false)

	_box(couch, "PillowLeft", Vector3(0.42, 0.42, 0.16), Vector3(-1.62, 0.84, 0.12), _materials["picture_gold"], Vector3(0.0, 8.0, -13.0))
	_box(couch, "PillowRight", Vector3(0.42, 0.42, 0.16), Vector3(1.62, 0.84, 0.12), _materials["picture_plum"], Vector3(0.0, -8.0, 13.0))
	for x in [-1.72, 1.72]:
		_box(couch, "Leg_%s" % str(x), Vector3(0.18, 0.20, 0.18), Vector3(x, 0.10, 0.38), _materials["wood_edge"])


func _build_armchair(parent: Node) -> void:
	var chair := _group(parent, "Armchair", Vector3(-3.30, 0.0, -1.45))
	var chair_mat: Material = _materials["chair"]
	var chair_light: Material = _materials["chair_light"]
	_box(chair, "SeatBase", Vector3(1.02, 0.34, 0.92), Vector3(0.0, 0.31, 0.0), chair_mat)
	_box(chair, "SeatCushion", Vector3(0.78, 0.15, 0.72), Vector3(0.0, 0.505, 0.08), chair_light)
	_box(chair, "Back", Vector3(0.98, 0.85, 0.22), Vector3(0.0, 0.91, -0.39), chair_mat, Vector3(-5.0, 0.0, 0.0))
	_box(chair, "LeftArm", Vector3(0.20, 0.50, 0.88), Vector3(-0.57, 0.55, 0.0), chair_mat)
	_box(chair, "RightArm", Vector3(0.20, 0.50, 0.88), Vector3(0.57, 0.55, 0.0), chair_mat)
	for x in [-0.38, 0.38]:
		for z in [-0.30, 0.30]:
			_box(chair, "Leg_%s_%s" % [str(x), str(z)], Vector3(0.11, 0.24, 0.11), Vector3(x, 0.12, z), _materials["wood_edge"], Vector3(0.0, 0.0, x * 5.0))


func _build_coffee_table(parent: Node) -> void:
	var table := _group(parent, "CoffeeTable", Vector3(0.08, 0.0, -1.05))
	var wood: Material = _materials["wood"]
	_box(table, "Top", Vector3(2.05, 0.10, 0.92), Vector3(0.0, 0.46, 0.0), _materials["wood_light"])
	_box(table, "ApronFront", Vector3(1.86, 0.14, 0.09), Vector3(0.0, 0.36, 0.40), wood)
	_box(table, "ApronBack", Vector3(1.86, 0.14, 0.09), Vector3(0.0, 0.36, -0.40), wood)
	_box(table, "LowerShelf", Vector3(1.66, 0.06, 0.68), Vector3(0.0, 0.18, 0.0), wood)
	for x in [-0.82, 0.82]:
		for z in [-0.34, 0.34]:
			_box(table, "Leg_%s_%s" % [str(x), str(z)], Vector3(0.11, 0.43, 0.11), Vector3(x, 0.225, z), _materials["wood_edge"])


func _build_tv(parent: Node) -> void:
	var tv := _group(parent, "Television", Vector3(3.02, 0.0, -3.48))
	_box(tv, "Console", Vector3(1.70, 0.50, 0.52), Vector3(0.0, 0.27, 0.0), _materials["wood"])
	_box(tv, "ConsoleDoorL", Vector3(0.68, 0.30, 0.025), Vector3(-0.39, 0.28, 0.275), _materials["wood_light"])
	_box(tv, "ConsoleDoorR", Vector3(0.68, 0.30, 0.025), Vector3(0.39, 0.28, 0.275), _materials["wood_light"])
	_box(tv, "ScreenCase", Vector3(1.54, 0.88, 0.15), Vector3(0.0, 1.02, -0.02), _materials["black"])
	_box(tv, "Screen", Vector3(1.39, 0.72, 0.018), Vector3(0.0, 1.02, 0.065), _materials["tv_screen"], Vector3.ZERO, false)
	# Graphic bars suggest a live feed without a costly viewport texture.
	_box(tv, "ScreenBarWarm", Vector3(0.76, 0.055, 0.010), Vector3(-0.18, 1.16, 0.078), _materials["orange_glow"], Vector3.ZERO, false)
	_box(tv, "ScreenBarBlue", Vector3(0.52, 0.055, 0.010), Vector3(0.05, 1.02, 0.078), _materials["picture_blue"], Vector3.ZERO, false)
	_box(tv, "ScreenBarSmall", Vector3(0.34, 0.055, 0.010), Vector3(-0.16, 0.88, 0.078), _materials["picture_plum"], Vector3.ZERO, false)
	_box(tv, "FootL", Vector3(0.11, 0.16, 0.12), Vector3(-0.48, 0.56, 0.0), _materials["black"])
	_box(tv, "FootR", Vector3(0.11, 0.16, 0.12), Vector3(0.48, 0.56, 0.0), _materials["black"])


func _build_props() -> void:
	var props := _group(self, "StoryProps")
	_build_table_props(props)
	_build_wall_decor(props)
	_build_lamp(props)
	_build_plant(props)
	_build_thermostat(props)
	_build_hidden_bill(props)


func _build_table_props(parent: Node) -> void:
	var table_y := 0.525
	# Maris's receipt stack and Quill's constitutional paperwork.
	_box(parent, "Receipt_0", Vector3(0.38, 0.010, 0.24), Vector3(-0.54, table_y, -1.08), _materials["paper_old"], Vector3(0.0, 5.0, 0.0), false)
	_box(parent, "Receipt_1", Vector3(0.35, 0.010, 0.22), Vector3(-0.51, table_y + 0.012, -1.07), _materials["paper"], Vector3(0.0, -4.0, 0.0), false)
	for z in [-1.14, -1.08, -1.02]:
		_box(parent, "ReceiptInk_%s" % str(z), Vector3(0.22, 0.006, 0.008), Vector3(-0.53, table_y + 0.021, z), _materials["ink"], Vector3(0.0, -4.0, 0.0), false)
	_box(parent, "QuillFolder", Vector3(0.50, 0.026, 0.36), Vector3(0.32, table_y + 0.010, -1.02), _materials["picture_blue"], Vector3(0.0, -7.0, 0.0), false)
	_box(parent, "QuillPage", Vector3(0.42, 0.012, 0.29), Vector3(0.31, table_y + 0.032, -1.02), _materials["paper"], Vector3(0.0, -7.0, 0.0), false)
	_box(parent, "Remote", Vector3(0.13, 0.045, 0.34), Vector3(0.78, table_y + 0.028, -1.18), _materials["black"], Vector3(0.0, 18.0, 0.0))
	_cylinder(parent, "Mug", 0.095, 0.085, 0.18, Vector3(-0.82, table_y + 0.09, -0.87), _materials["ceramic"], Vector3.ZERO, Vector3.ONE, 12)
	_box(parent, "MugHandleTop", Vector3(0.11, 0.035, 0.035), Vector3(-0.69, table_y + 0.14, -0.87), _materials["ceramic"])
	_box(parent, "MugHandleSide", Vector3(0.035, 0.10, 0.035), Vector3(-0.64, table_y + 0.09, -0.87), _materials["ceramic"])
	_box(parent, "MugHandleBottom", Vector3(0.11, 0.035, 0.035), Vector3(-0.69, table_y + 0.04, -0.87), _materials["ceramic"])


func _build_wall_decor(parent: Node) -> void:
	var decor := _group(parent, "WallDecor")
	# Three mismatched thrift-store frames form a deliberate sitcom composition.
	_box(decor, "FrameLeft", Vector3(0.64, 0.80, 0.055), Vector3(-1.45, 2.38, -4.055), _materials["wood"])
	_box(decor, "ArtLeft", Vector3(0.51, 0.66, 0.025), Vector3(-1.45, 2.38, -4.020), _materials["picture_plum"], Vector3.ZERO, false)
	_box(decor, "FrameCenter", Vector3(0.92, 0.68, 0.055), Vector3(-0.50, 2.43, -4.055), _materials["wood_light"])
	_box(decor, "ArtCenter", Vector3(0.78, 0.54, 0.025), Vector3(-0.50, 2.43, -4.020), _materials["picture_gold"], Vector3.ZERO, false)
	_box(decor, "FrameRight", Vector3(0.58, 0.75, 0.055), Vector3(0.45, 2.34, -4.055), _materials["wood"])
	_box(decor, "ArtRight", Vector3(0.45, 0.62, 0.025), Vector3(0.45, 2.34, -4.020), _materials["picture_blue"], Vector3.ZERO, false)

	# Tiny abstract family portrait: four related blue forms, not debug name labels.
	for item in [
		[-0.79, 2.44, "blue_reed", 0.115],
		[-0.58, 2.47, "blue_maris", 0.095],
		[-0.38, 2.42, "blue_jinx", 0.080],
		[-0.20, 2.40, "blue_quill", 0.068],
	]:
		_sphere(decor, "PortraitDot_%s" % str(item[0]), float(item[3]), Vector3(float(item[0]), float(item[1]), -3.998), _materials[str(item[2])], Vector3(0.82, 1.0, 0.22), Vector3.ZERO, false)

	# Small wall clock with block hands.
	_cylinder(decor, "ClockFace", 0.27, 0.27, 0.055, Vector3(1.24, 2.52, -4.055), _materials["trim"], Vector3(90.0, 0.0, 0.0), Vector3.ONE, 18, false)
	_box(decor, "ClockHandHour", Vector3(0.035, 0.16, 0.018), Vector3(1.24, 2.58, -4.012), _materials["ink"], Vector3(0.0, 0.0, -12.0), false)
	_box(decor, "ClockHandMinute", Vector3(0.18, 0.032, 0.018), Vector3(1.31, 2.52, -4.010), _materials["ink"], Vector3(0.0, 0.0, 20.0), false)


func _build_lamp(parent: Node) -> void:
	var lamp := _group(parent, "FloorLamp", Vector3(-4.34, 0.0, -0.92))
	_cylinder(lamp, "Base", 0.24, 0.27, 0.07, Vector3(0.0, 0.035, 0.0), _materials["metal_dark"], Vector3.ZERO, Vector3.ONE, 14)
	_cylinder(lamp, "Pole", 0.035, 0.045, 1.62, Vector3(0.0, 0.84, 0.0), _materials["metal"], Vector3.ZERO, Vector3.ONE, 10)
	_cylinder(lamp, "Shade", 0.18, 0.36, 0.42, Vector3(0.0, 1.78, 0.0), _materials["shade"], Vector3.ZERO, Vector3.ONE, 14, false)
	_sphere(lamp, "Bulb", 0.10, Vector3(0.0, 1.70, 0.0), _materials["orange_glow"], Vector3.ONE, Vector3.ZERO, false)
	_cylinder(lamp, "Finial", 0.025, 0.025, 0.12, Vector3(0.0, 2.05, 0.0), _materials["metal_dark"], Vector3.ZERO, Vector3.ONE, 8)


func _build_plant(parent: Node) -> void:
	var plant := _group(parent, "HousePlant", Vector3(4.35, 0.0, -1.08))
	_cylinder(plant, "Pot", 0.25, 0.34, 0.42, Vector3(0.0, 0.22, 0.0), _materials["pot"], Vector3.ZERO, Vector3.ONE, 14)
	_cylinder(plant, "Soil", 0.235, 0.235, 0.025, Vector3(0.0, 0.44, 0.0), _materials["floor_dark"], Vector3.ZERO, Vector3.ONE, 14, false)
	for stem in [
		[Vector3(-0.08, 0.73, 0.0), Vector3(0.0, 0.0, -10.0)],
		[Vector3(0.10, 0.80, 0.02), Vector3(8.0, 0.0, 12.0)],
		[Vector3(0.0, 0.91, -0.04), Vector3(-8.0, 0.0, 1.0)],
	]:
		_cylinder(plant, "Stem_%s" % str(stem[0]), 0.018, 0.024, 0.62, stem[0], _materials["plant"], stem[1], Vector3.ONE, 7)
	for leaf in [
		[Vector3(-0.28, 0.82, 0.00), Vector3(0.0, 0.0, 28.0), "plant"],
		[Vector3(0.29, 0.88, 0.02), Vector3(0.0, 0.0, -30.0), "plant_light"],
		[Vector3(-0.15, 1.12, -0.03), Vector3(0.0, 0.0, 15.0), "plant_light"],
		[Vector3(0.18, 1.18, -0.03), Vector3(0.0, 0.0, -18.0), "plant"],
		[Vector3(0.02, 1.37, -0.05), Vector3(0.0, 0.0, 3.0), "plant_light"],
	]:
		_sphere(plant, "Leaf_%s" % str(leaf[0]), 0.22, leaf[0], _materials[str(leaf[2])], Vector3(1.65, 0.58, 0.38), leaf[1])


func _build_thermostat(parent: Node) -> void:
	var thermostat := _group(parent, "Thermostat", Vector3(2.00, 2.20, -4.055))
	_box(thermostat, "Housing", Vector3(0.38, 0.46, 0.075), Vector3.ZERO, _materials["appliance"])
	_box(thermostat, "Display", Vector3(0.27, 0.16, 0.018), Vector3(0.0, 0.055, 0.048), _materials["green_glow"], Vector3.ZERO, false)
	_sphere(thermostat, "ButtonL", 0.025, Vector3(-0.09, -0.125, 0.050), _materials["metal_dark"], Vector3(1.0, 1.0, 0.35), Vector3.ZERO, false)
	_sphere(thermostat, "ButtonR", 0.025, Vector3(0.09, -0.125, 0.050), _materials["metal_dark"], Vector3(1.0, 1.0, 0.35), Vector3.ZERO, false)
	_label(thermostat, "Readout", "72° ?", Vector3(0.0, 0.055, 0.061), Color("173521"), 26, 0.0022)


func _build_hidden_bill(parent: Node) -> void:
	# It is physically present behind the couch and only barely peeks out from above.
	var bill := _group(parent, "UnclaimedTwenty", Vector3(1.52, 0.44, -3.40), Vector3(74.0, -8.0, 4.0))
	_box(bill, "Bill", Vector3(0.34, 0.012, 0.16), Vector3.ZERO, _materials["green_bill"], Vector3.ZERO, false)
	_box(bill, "BillStripe", Vector3(0.19, 0.007, 0.025), Vector3(0.0, 0.010, 0.0), _materials["paper_old"], Vector3.ZERO, false)


func _build_lights() -> void:
	var lights := _group(self, "SitcomLighting")

	# The only shadow-casting light: a broad warm studio key.
	var key := DirectionalLight3D.new()
	key.name = "WarmKey_ShadowCaster"
	key.light_color = Color("ffe2b5")
	key.light_energy = 0.92
	key.shadow_enabled = true
	key.rotation_degrees = Vector3(-52.0, -28.0, 0.0)
	lights.add_child(key)

	# Non-shadow fill keeps blue faces readable in every canned camera angle.
	var fill := OmniLight3D.new()
	fill.name = "SoftFill_NoShadows"
	fill.light_color = Color("ffd9ab")
	fill.light_energy = 1.12
	fill.omni_range = 10.5
	fill.omni_attenuation = 1.35
	fill.shadow_enabled = false
	fill.position = Vector3(0.0, 2.85, 1.80)
	lights.add_child(fill)

	var face := SpotLight3D.new()
	face.name = "FaceLight_NoShadows"
	face.light_color = Color("fff0d2")
	face.light_energy = 0.72
	face.spot_range = 10.0
	face.spot_angle = 54.0
	face.spot_attenuation = 0.75
	face.shadow_enabled = false
	face.position = Vector3(0.0, 2.70, 4.15)
	lights.add_child(face)
	face.look_at(Vector3(0.0, 1.05, -1.70), Vector3.UP)

	var rim := DirectionalLight3D.new()
	rim.name = "CoolRim_NoShadows"
	rim.light_color = Color("b8d9df")
	rim.light_energy = 0.25
	rim.shadow_enabled = false
	rim.rotation_degrees = Vector3(-25.0, 148.0, 0.0)
	lights.add_child(rim)

	var practical := OmniLight3D.new()
	practical.name = "LampPractical_NoShadows"
	practical.light_color = Color("ffb967")
	practical.light_energy = 0.72
	practical.omni_range = 4.4
	practical.omni_attenuation = 1.65
	practical.shadow_enabled = false
	practical.position = Vector3(-4.34, 1.72, -0.92)
	lights.add_child(practical)

	var kitchen_fill := OmniLight3D.new()
	kitchen_fill.name = "KitchenFill_NoShadows"
	kitchen_fill.light_color = Color("ffd194")
	kitchen_fill.light_energy = 0.48
	kitchen_fill.omni_range = 3.5
	kitchen_fill.omni_attenuation = 1.55
	kitchen_fill.shadow_enabled = false
	kitchen_fill.position = Vector3(-3.70, 2.55, -4.58)
	lights.add_child(kitchen_fill)


func apply_setting(scene_name: String) -> void:
	var env := get_node_or_null("WarmSitcomEnvironment") as WorldEnvironment
	var lights := get_node_or_null("SitcomLighting")
	var kitchen_fill: OmniLight3D = lights.get_node_or_null("KitchenFill_NoShadows") if lights else null
	var lamp: OmniLight3D = lights.get_node_or_null("LampPractical_NoShadows") if lights else null
	var face: SpotLight3D = lights.get_node_or_null("FaceLight_NoShadows") if lights else null
	var furniture := get_node_or_null("Furniture")
	var story_props := get_node_or_null("StoryProps")
	var wall_decor: Node = story_props.get_node_or_null("WallDecor") if story_props else null
	var kitchen := get_node_or_null("KitchenPassThrough")
	var clear := Color(0.145, 0.118, 0.098, 1)

	# Restore living-room defaults before applying a named set.
	if furniture:
		furniture.visible = true
	if story_props:
		story_props.visible = true
	if wall_decor:
		wall_decor.visible = true
	if kitchen:
		kitchen.visible = true
	if kitchen_fill:
		kitchen_fill.light_energy = 0.48
	if lamp:
		lamp.light_energy = 0.72
	if face:
		face.light_energy = 0.72

	match scene_name:
		"kitchen":
			clear = Color(0.16, 0.12, 0.08, 1)
			if furniture:
				furniture.visible = false
			if wall_decor:
				wall_decor.visible = false
			if kitchen_fill:
				kitchen_fill.light_energy = 1.15
			if lamp:
				lamp.light_energy = 0.45
		"front_yard":
			clear = Color(0.35, 0.55, 0.72, 1)
			if kitchen:
				kitchen.visible = false
			if face:
				face.light_energy = 0.35
			if lamp:
				lamp.light_energy = 0.2
			if kitchen_fill:
				kitchen_fill.light_energy = 0.15
		"porch":
			clear = Color(0.10, 0.12, 0.18, 1)
			if kitchen:
				kitchen.visible = false
			if lamp:
				lamp.light_energy = 1.1
			if face:
				face.light_energy = 0.4
		"hallway":
			clear = Color(0.12, 0.10, 0.09, 1)
			if face:
				face.light_energy = 0.5
			if lamp:
				lamp.light_energy = 0.35
		_:
			pass

	if env and env.environment:
		env.environment.background_color = clear
	RenderingServer.set_default_clear_color(clear)
