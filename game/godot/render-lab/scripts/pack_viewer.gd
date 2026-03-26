extends Node2D

## Phase 6B — Export Pack Consumer Spike
## Loads a foundry export pack via manifest.json and displays all 8 directions.
## Arrow keys or A/D to rotate. Space to cycle subjects.

const EXPECTED_SCHEMA := "1.0.0"

@export var pack_paths: Array[String] = []

var packs: Array[Dictionary] = []  # [{manifest, albedos, normals, canvas_textures}]
var current_pack_idx := 0
var current_dir_idx := 0

var sprite: Sprite2D
var label_dir: Label
var label_subject: Label
var label_status: Label


func _ready() -> void:
	_build_scene()

	if pack_paths.is_empty():
		_set_status("ERROR: No pack_paths configured")
		return

	# Load all packs
	for pack_path in pack_paths:
		var result := _load_pack(pack_path)
		if result.has("error"):
			_set_status("FAIL: %s — %s" % [pack_path.get_file(), result.error])
			return
		packs.append(result)

	_set_status("Loaded %d packs. Space=cycle subject, A/D=rotate direction" % packs.size())
	_apply_pack(0)
	_apply_direction(0)


func _load_pack(base_path: String) -> Dictionary:
	# Read manifest
	var manifest_path := base_path.path_join("manifest.json")
	var file := FileAccess.open(manifest_path, FileAccess.READ)
	if file == null:
		return {"error": "Cannot open manifest: %s" % manifest_path}

	var json := JSON.new()
	var err := json.parse(file.get_as_text())
	file.close()
	if err != OK:
		return {"error": "Invalid JSON in manifest"}

	var manifest: Dictionary = json.data
	if not manifest.has("schema_version"):
		return {"error": "Missing schema_version in manifest"}
	if manifest.schema_version != EXPECTED_SCHEMA:
		return {"error": "Schema mismatch: expected %s, got %s" % [EXPECTED_SCHEMA, manifest.schema_version]}

	# Validate required sections
	for section in ["identity", "render_contract", "files"]:
		if not manifest.has(section):
			return {"error": "Missing section: %s" % section}

	var directions: Array = manifest.render_contract.direction_order
	if directions.size() != 8:
		return {"error": "Expected 8 directions, got %d" % directions.size()}

	# Load textures
	var albedos := {}
	var normals := {}
	var canvas_textures := {}

	for dir_name in directions:
		var albedo_rel := "albedo/%s.png" % dir_name
		var normal_rel := "normal/%s.png" % dir_name

		# Verify files listed in manifest
		if not manifest.files.has(albedo_rel):
			return {"error": "Manifest missing file entry: %s" % albedo_rel}

		var albedo_path := base_path.path_join(albedo_rel)
		var normal_path := base_path.path_join(normal_rel)

		# Load albedo (required)
		var albedo_tex := _load_texture(albedo_path)
		if albedo_tex == null:
			return {"error": "Cannot load: %s" % albedo_path}
		albedos[dir_name] = albedo_tex

		# Load normal (optional — don't fail if missing)
		var normal_tex := _load_texture(normal_path)
		if normal_tex != null:
			normals[dir_name] = normal_tex

		# Build CanvasTexture
		var ct := CanvasTexture.new()
		ct.diffuse_texture = albedo_tex
		if normal_tex != null:
			ct.normal_texture = normal_tex
			ct.specular_color = Color(0.3, 0.3, 0.3, 1.0)
			ct.specular_shininess = 0.3
		canvas_textures[dir_name] = ct

	var pack := {
		"manifest": manifest,
		"albedos": albedos,
		"normals": normals,
		"canvas_textures": canvas_textures,
		"directions": directions,
		"display_name": manifest.identity.display_name,
	}
	print("Pack loaded: %s (%d albedos, %d normals)" % [
		pack.display_name, albedos.size(), normals.size()
	])
	return pack


func _load_texture(path: String) -> ImageTexture:
	var img := Image.new()
	var err := img.load(path)
	if err != OK:
		return null
	var tex := ImageTexture.create_from_image(img)
	return tex


func _build_scene() -> void:
	var cam := Camera2D.new()
	cam.position = Vector2(256, 256)
	add_child(cam)

	# Ground plane
	var ground := ColorRect.new()
	ground.position = Vector2(0, 380)
	ground.size = Vector2(512, 132)
	ground.color = Color(0.12, 0.12, 0.15, 1)
	add_child(ground)

	# Sprite
	sprite = Sprite2D.new()
	sprite.position = Vector2(256, 270)
	sprite.scale = Vector2(5, 5)
	sprite.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	add_child(sprite)

	# Moonlight for normal map visibility
	var light := PointLight2D.new()
	light.position = Vector2(200, 80)
	light.color = Color(0.45, 0.6, 1.0, 1.0)
	light.energy = 1.2
	light.texture = _make_light_texture()
	light.texture_scale = 2.5
	add_child(light)

	# Direction label
	label_dir = Label.new()
	label_dir.position = Vector2(10, 10)
	label_dir.add_theme_font_size_override("font_size", 18)
	label_dir.add_theme_color_override("font_color", Color.WHITE)
	add_child(label_dir)

	# Subject label
	label_subject = Label.new()
	label_subject.position = Vector2(10, 35)
	label_subject.add_theme_font_size_override("font_size", 14)
	label_subject.add_theme_color_override("font_color", Color(0.7, 0.7, 0.7))
	add_child(label_subject)

	# Status label
	label_status = Label.new()
	label_status.position = Vector2(10, 480)
	label_status.add_theme_font_size_override("font_size", 12)
	label_status.add_theme_color_override("font_color", Color(0.5, 0.5, 0.5))
	add_child(label_status)


func _make_light_texture() -> GradientTexture2D:
	var tex := GradientTexture2D.new()
	tex.width = 256
	tex.height = 256
	tex.fill = GradientTexture2D.FILL_RADIAL
	tex.fill_from = Vector2(0.5, 0.5)
	tex.fill_to = Vector2(0.5, 0.8)
	var grad := Gradient.new()
	grad.set_color(0, Color.WHITE)
	grad.add_point(0.6, Color(0.5, 0.5, 0.5, 0.5))
	grad.set_color(1, Color.TRANSPARENT)
	tex.gradient = grad
	return tex


func _apply_pack(idx: int) -> void:
	current_pack_idx = idx
	var pack: Dictionary = packs[idx]
	label_subject.text = "%s [%d/%d]" % [pack.display_name, idx + 1, packs.size()]


func _apply_direction(idx: int) -> void:
	current_dir_idx = idx
	var pack: Dictionary = packs[current_pack_idx]
	var dir_name: String = pack.directions[idx]
	sprite.texture = pack.canvas_textures[dir_name]
	label_dir.text = dir_name


func _set_status(msg: String) -> void:
	if label_status:
		label_status.text = msg
	print(msg)


func _input(event: InputEvent) -> void:
	if packs.is_empty():
		return

	if event is InputEventKey and event.pressed:
		var pack: Dictionary = packs[current_pack_idx]
		match event.keycode:
			KEY_D, KEY_RIGHT:
				_apply_direction((current_dir_idx + 1) % pack.directions.size())
			KEY_A, KEY_LEFT:
				_apply_direction((current_dir_idx - 1 + pack.directions.size()) % pack.directions.size())
			KEY_SPACE:
				_apply_pack((current_pack_idx + 1) % packs.size())
				_apply_direction(0)
			KEY_ESCAPE:
				get_tree().quit()
