extends Node3D
## Cheap warm sitcom living-room set. Readable at 1280x720.

func _ready() -> void:
	_build_environment()
	_build_shell()
	_build_furniture()
	_build_props()
	_build_lights()


func _mat(color: Color, rough: float = 0.78, emission: Color = Color(0, 0, 0, 1), emission_energy: float = 0.0) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_color = color
	m.roughness = rough
	m.metallic = 0.0
	if emission_energy > 0.0:
		m.emission_enabled = true
		m.emission = emission
		m.emission_energy_multiplier = emission_energy
	return m


func _box(parent: Node, name: String, size: Vector3, pos: Vector3, mat: Material, rot_deg: Vector3 = Vector3.ZERO) -> CSGBox3D:
	var b := CSGBox3D.new()
	b.name = name
	b.size = size
	b.position = pos
	b.rotation_degrees = rot_deg
	b.material = mat
	parent.add_child(b)
	return b


func _sphere(parent: Node, name: String, radius: float, pos: Vector3, mat: Material) -> CSGSphere3D:
	var s := CSGSphere3D.new()
	s.name = name
	s.radius = radius
	s.radial_segments = 12
	s.rings = 8
	s.position = pos
	s.material = mat
	parent.add_child(s)
	return s


func _cyl(parent: Node, name: String, radius: float, height: float, pos: Vector3, mat: Material) -> CSGCylinder3D:
	var c := CSGCylinder3D.new()
	c.name = name
	c.radius = radius
	c.height = height
	c.sides = 12
	c.position = pos
	c.material = mat
	parent.add_child(c)
	return c


func _build_environment() -> void:
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.16, 0.13, 0.11)
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.92, 0.78, 0.58)
	env.ambient_light_energy = 0.42
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	env.tonemap_exposure = 1.05
	env.glow_enabled = false
	env.ssao_enabled = false
	env.adjustment_enabled = true
	env.adjustment_saturation = 1.12
	var we := WorldEnvironment.new()
	we.name = "WorldEnvironment"
	we.environment = env
	add_child(we)


func _build_shell() -> void:
	var wood := _mat(Color(0.42, 0.28, 0.16), 0.7)
	var carpet := _mat(Color(0.55, 0.38, 0.26), 0.92)
	var rug := _mat(Color(0.38, 0.22, 0.18), 0.9)
	var wall_up := _mat(Color(0.93, 0.84, 0.70), 0.88)
	var wall_lo := _mat(Color(0.62, 0.42, 0.28), 0.74)
	var trim := _mat(Color(0.86, 0.78, 0.62), 0.65)
	var ceiling := _mat(Color(0.96, 0.90, 0.80), 0.9)

	_box(self, "Floor", Vector3(11.0, 0.12, 8.4), Vector3(0, -0.06, 0.2), wood)
	_box(self, "Carpet", Vector3(9.6, 0.04, 6.6), Vector3(0, 0.02, 0.1), carpet)
	_box(self, "Rug", Vector3(4.2, 0.03, 2.4), Vector3(0.1, 0.05, -0.7), rug)

	# Back, left, right walls. Open toward +Z (audience).
	_box(self, "WallBack", Vector3(11.0, 3.4, 0.14), Vector3(0, 1.7, -3.95), wall_up)
	_box(self, "WainscotBack", Vector3(11.0, 1.05, 0.16), Vector3(0, 0.52, -3.93), wall_lo)
	_box(self, "WallLeft", Vector3(0.14, 3.4, 8.4), Vector3(-5.5, 1.7, 0.2), wall_up)
	_box(self, "WainscotLeft", Vector3(0.16, 1.05, 8.4), Vector3(-5.48, 0.52, 0.2), wall_lo)
	_box(self, "WallRight", Vector3(0.14, 3.4, 8.4), Vector3(5.5, 1.7, 0.2), wall_up)
	_box(self, "WainscotRight", Vector3(0.16, 1.05, 8.4), Vector3(5.48, 0.52, 0.2), wall_lo)
	_box(self, "Ceiling", Vector3(11.0, 0.1, 8.4), Vector3(0, 3.42, 0.2), ceiling)

	_box(self, "BaseBack", Vector3(11.0, 0.12, 0.18), Vector3(0, 0.08, -3.86), trim)
	_box(self, "BaseLeft", Vector3(0.18, 0.12, 8.4), Vector3(-5.40, 0.08, 0.2), trim)
	_box(self, "BaseRight", Vector3(0.18, 0.12, 8.4), Vector3(5.40, 0.08, 0.2), trim)
	_box(self, "ChairRailBack", Vector3(11.0, 0.06, 0.12), Vector3(0, 1.05, -3.86), trim)

	# Window on right wall — daytime sitcom glow.
	var frame := _mat(Color(0.9, 0.86, 0.74), 0.5)
	var glass := _mat(Color(0.55, 0.72, 0.92), 0.15, Color(0.65, 0.82, 1.0), 0.85)
	_box(self, "WindowFrame", Vector3(0.12, 1.7, 1.7), Vector3(5.42, 2.05, 0.4), frame)
	_box(self, "WindowGlass", Vector3(0.04, 1.45, 1.45), Vector3(5.34, 2.05, 0.4), glass)
	_box(self, "WindowMuntinH", Vector3(0.06, 0.05, 1.45), Vector3(5.36, 2.05, 0.4), frame)
	_box(self, "WindowMuntinV", Vector3(0.06, 1.45, 0.05), Vector3(5.36, 2.05, 0.4), frame)
	_box(self, "Sill", Vector3(0.28, 0.08, 1.9), Vector3(5.28, 1.18, 0.4), frame)

	# Door opening on left toward -X / +Z corner.
	var door := _mat(Color(0.45, 0.28, 0.16), 0.6)
	_box(self, "Door", Vector3(0.08, 2.2, 0.95), Vector3(-5.42, 1.12, 2.35), door)
	_box(self, "DoorFrame", Vector3(0.12, 2.32, 1.12), Vector3(-5.44, 1.16, 2.35), trim)
	_sphere(self, "Doorknob", 0.04, Vector3(-5.34, 1.05, 2.65), _mat(Color(0.82, 0.7, 0.28), 0.35))


func _build_furniture() -> void:
	var couch_col := _mat(Color(0.52, 0.38, 0.22), 0.82)
	var cushion := _mat(Color(0.58, 0.42, 0.24), 0.86)
	var wood := _mat(Color(0.36, 0.22, 0.12), 0.55)
	var fridge := _mat(Color(0.88, 0.90, 0.92), 0.35)
	var fridge_dark := _mat(Color(0.55, 0.58, 0.62), 0.4)
	var tv_black := _mat(Color(0.12, 0.12, 0.14), 0.5)
	var screen := _mat(Color(0.2, 0.35, 0.55), 0.3, Color(0.25, 0.45, 0.7), 0.6)

	# Couch against back wall, facing audience (+Z).
	_box(self, "CouchBase", Vector3(3.6, 0.42, 1.15), Vector3(0.0, 0.32, -2.55), couch_col)
	_box(self, "CouchBack", Vector3(3.6, 0.85, 0.28), Vector3(0.0, 0.82, -3.05), couch_col)
	_box(self, "CouchArmL", Vector3(0.28, 0.62, 1.15), Vector3(-1.9, 0.62, -2.55), couch_col)
	_box(self, "CouchArmR", Vector3(0.28, 0.62, 1.15), Vector3(1.9, 0.62, -2.55), couch_col)
	_box(self, "CushionL", Vector3(1.55, 0.16, 0.9), Vector3(-0.78, 0.56, -2.48), cushion)
	_box(self, "CushionR", Vector3(1.55, 0.16, 0.9), Vector3(0.78, 0.56, -2.48), cushion)

	# Coffee table.
	_box(self, "TableTop", Vector3(1.7, 0.08, 0.85), Vector3(0.05, 0.42, -1.15), wood)
	_box(self, "LegFL", Vector3(0.08, 0.4, 0.08), Vector3(-0.7, 0.20, -0.82), wood)
	_box(self, "LegFR", Vector3(0.08, 0.4, 0.08), Vector3(0.8, 0.20, -0.82), wood)
	_box(self, "LegBL", Vector3(0.08, 0.4, 0.08), Vector3(-0.7, 0.20, -1.48), wood)
	_box(self, "LegBR", Vector3(0.08, 0.4, 0.08), Vector3(0.8, 0.20, -1.48), wood)

	# Fridge, kitchen nook on left.
	_box(self, "Fridge", Vector3(0.85, 1.85, 0.75), Vector3(-4.55, 0.95, -2.55), fridge)
	_box(self, "FridgeHandle", Vector3(0.04, 0.55, 0.04), Vector3(-4.10, 1.15, -2.25), fridge_dark)
	_box(self, "FridgeFreezerLine", Vector3(0.86, 0.02, 0.76), Vector3(-4.55, 1.45, -2.55), fridge_dark)
	# Dinner-veto sticky note.
	_box(self, "VetoNote", Vector3(0.22, 0.16, 0.01), Vector3(-4.12, 1.55, -2.18), _mat(Color(0.95, 0.9, 0.35), 0.7))
	var veto := Label3D.new()
	veto.name = "VetoLabel"
	veto.text = "DINNER\nVETO"
	veto.font_size = 28
	veto.pixel_size = 0.004
	veto.position = Vector3(-4.10, 1.55, -2.15)
	veto.rotation_degrees = Vector3(0, 90, 0)
	veto.modulate = Color(0.15, 0.1, 0.05)
	add_child(veto)

	# Sideboard + TV along right-back.
	_box(self, "TVStand", Vector3(1.6, 0.45, 0.5), Vector3(3.55, 0.25, -3.35), wood)
	_box(self, "TV", Vector3(1.35, 0.78, 0.12), Vector3(3.55, 0.95, -3.48), tv_black)
	_box(self, "TVScreen", Vector3(1.22, 0.66, 0.02), Vector3(3.55, 0.95, -3.41), screen)

	# Armchair stage-left of couch.
	_box(self, "ChairSeat", Vector3(0.85, 0.38, 0.85), Vector3(-2.85, 0.28, -1.55), _mat(Color(0.45, 0.22, 0.18), 0.8))
	_box(self, "ChairBack", Vector3(0.85, 0.7, 0.16), Vector3(-2.85, 0.72, -1.92), _mat(Color(0.45, 0.22, 0.18), 0.8))


func _build_props() -> void:
	var ceramic := _mat(Color(0.85, 0.55, 0.28), 0.4)
	var paper := _mat(Color(0.93, 0.91, 0.84), 0.85)
	var thermo := _mat(Color(0.82, 0.82, 0.78), 0.45)
	var led := _mat(Color(0.3, 0.95, 0.45), 0.2, Color(0.2, 1.0, 0.35), 2.2)
	var plant := _mat(Color(0.22, 0.48, 0.22), 0.7)
	var pot := _mat(Color(0.55, 0.28, 0.18), 0.6)
	var shade := _mat(Color(0.95, 0.82, 0.55), 0.7, Color(1.0, 0.82, 0.5), 0.35)
	var lamp_stem := _mat(Color(0.7, 0.68, 0.62), 0.4)

	_cyl(self, "Mug", 0.05, 0.09, Vector3(0.35, 0.51, -1.05), ceramic)
	_box(self, "ScriptPages", Vector3(0.28, 0.01, 0.2), Vector3(-0.35, 0.47, -1.2), paper)

	# Thermostat on back wall, audience-readable.
	_box(self, "Thermostat", Vector3(0.22, 0.28, 0.06), Vector3(1.85, 2.15, -3.86), thermo)
	_box(self, "ThermoLED", Vector3(0.14, 0.08, 0.02), Vector3(1.85, 2.18, -3.82), led)
	var tlab := Label3D.new()
	tlab.name = "ThermoLabel"
	tlab.text = "72°  ?"
	tlab.font_size = 32
	tlab.pixel_size = 0.0035
	tlab.position = Vector3(1.85, 2.02, -3.80)
	tlab.modulate = Color(0.15, 0.4, 0.2)
	add_child(tlab)

	_cyl(self, "PlantPot", 0.14, 0.22, Vector3(4.55, 0.14, -2.4), pot)
	_sphere(self, "PlantA", 0.22, Vector3(4.55, 0.42, -2.4), plant)
	_sphere(self, "PlantB", 0.16, Vector3(4.68, 0.55, -2.32), plant)
	_sphere(self, "PlantC", 0.14, Vector3(4.40, 0.52, -2.48), plant)

	# Floor lamp near armchair.
	_cyl(self, "LampPole", 0.03, 1.7, Vector3(-4.15, 0.85, -1.15), lamp_stem)
	_cyl(self, "LampShade", 0.22, 0.28, Vector3(-4.15, 1.78, -1.15), shade)
	_cyl(self, "LampBase", 0.16, 0.06, Vector3(-4.15, 0.04, -1.15), lamp_stem)

	# Picture frames on back wall.
	var frame := _mat(Color(0.45, 0.3, 0.15), 0.5)
	var pic := _mat(Color(0.35, 0.55, 0.75), 0.6)
	_box(self, "Frame1", Vector3(0.55, 0.7, 0.04), Vector3(-2.2, 2.25, -3.87), frame)
	_box(self, "Pic1", Vector3(0.45, 0.58, 0.02), Vector3(-2.2, 2.25, -3.84), pic)
	_box(self, "Frame2", Vector3(0.45, 0.45, 0.04), Vector3(-1.4, 2.35, -3.87), frame)
	_box(self, "Pic2", Vector3(0.36, 0.36, 0.02), Vector3(-1.4, 2.35, -3.84), _mat(Color(0.55, 0.45, 0.7), 0.6))


func _build_lights() -> void:
	var key := DirectionalLight3D.new()
	key.name = "KeyLight"
	key.light_color = Color(1.0, 0.90, 0.72)
	key.light_energy = 0.85
	key.shadow_enabled = false
	key.rotation_degrees = Vector3(-48, 25, 0)
	add_child(key)

	var fill := OmniLight3D.new()
	fill.name = "Fill"
	fill.light_color = Color(1.0, 0.86, 0.68)
	fill.light_energy = 1.6
	fill.omni_range = 11.0
	fill.omni_attenuation = 1.4
	fill.position = Vector3(0.2, 2.9, 1.4)
	add_child(fill)

	var lamp := OmniLight3D.new()
	lamp.name = "PracticalLamp"
	lamp.light_color = Color(1.0, 0.72, 0.42)
	lamp.light_energy = 1.15
	lamp.omni_range = 5.5
	lamp.position = Vector3(-4.15, 1.7, -1.15)
	add_child(lamp)

	var window_light := OmniLight3D.new()
	window_light.name = "WindowLight"
	window_light.light_color = Color(0.75, 0.88, 1.0)
	window_light.light_energy = 0.7
	window_light.omni_range = 6.0
	window_light.position = Vector3(4.6, 2.0, 0.4)
	add_child(window_light)

	var rim := DirectionalLight3D.new()
	rim.name = "Rim"
	rim.light_color = Color(1.0, 0.78, 0.55)
	rim.light_energy = 0.28
	rim.rotation_degrees = Vector3(-20, -140, 0)
	add_child(rim)
