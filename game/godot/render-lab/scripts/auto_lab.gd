extends Node2D

## Phase 3 Finish Capture — pirate_navigator
## 2 directions x 4 states

const DIRECTIONS := ["right", "front_right"]
const STATES := ["baseline", "moonlight", "torch", "moon_particles_depth"]

var sprite: Sprite2D
var light_torch: PointLight2D
var light_moon: PointLight2D
var particles_ember: GPUParticles2D
var particles_dust: GPUParticles2D

var current_dir_idx := 0
var current_state_idx := 0
var frame_wait := 0
var captures_done := 0
var total_captures: int

var albedo_textures := {}
var normal_textures := {}
var canvas_textures := {}

var depth_shader: ShaderMaterial


## Directory the headless capture loop writes PNGs into. Created in _ready()
## if it does not exist, so standalone runs do not silently no-op on save.
const SCREENSHOTS_DIR := "res://screenshots"


func _fail(msg: String) -> void:
	# Single failure path: print an actionable error and exit non-zero so the
	# Python driver can detect failure by exit code, not stdout scraping.
	printerr("FINISH LAB FAILURE: %s" % msg)
	get_tree().quit(1)


func _ready() -> void:
	total_captures = DIRECTIONS.size() * STATES.size()
	_build_scene()

	# Ensure the screenshots output directory exists from inside Godot rather
	# than relying on an external caller to pre-create it (F-004).
	var shots_abs := ProjectSettings.globalize_path(SCREENSHOTS_DIR)
	if not DirAccess.dir_exists_absolute(shots_abs):
		var mk := DirAccess.make_dir_recursive_absolute(shots_abs)
		if mk != OK:
			_fail("could not create screenshots dir %s (err %d)" % [shots_abs, mk])
			return

	for dir_name in DIRECTIONS:
		var albedo_path := "res://assets/pirate_navigator_sprites/%s.png" % dir_name
		var normal_path := "res://assets/pirate_navigator_normals/%s_normal.png" % dir_name
		albedo_textures[dir_name] = load(albedo_path)
		normal_textures[dir_name] = load(normal_path)

		# Abort on a missing/failed texture load — never render blank captures
		# that would let a finish-verification pass "succeed" on nothing (F-003).
		if albedo_textures[dir_name] == null:
			_fail("albedo texture failed to load: %s" % albedo_path)
			return
		if normal_textures[dir_name] == null:
			_fail("normal texture failed to load: %s" % normal_path)
			return

		var ct := CanvasTexture.new()
		ct.diffuse_texture = albedo_textures[dir_name]
		ct.normal_texture = normal_textures[dir_name]
		ct.specular_color = Color(0.3, 0.3, 0.3, 1.0)
		ct.specular_shininess = 0.3
		canvas_textures[dir_name] = ct

	var depth_sh := Shader.new()
	depth_sh.code = """
shader_type canvas_item;

uniform float falloff_strength : hint_range(0.0, 1.0) = 0.35;
uniform vec4 atmosphere_color : source_color = vec4(0.4, 0.5, 0.7, 1.0);
uniform float rim_strength : hint_range(0.0, 2.0) = 0.5;
uniform vec4 rim_color : source_color = vec4(0.6, 0.7, 1.0, 1.0);

void fragment() {
	vec4 tex = texture(TEXTURE, UV);
	if (tex.a < 0.1) discard;
	float vert = UV.y;
	vec2 px = TEXTURE_PIXEL_SIZE;
	float a_l = texture(TEXTURE, UV + vec2(-px.x, 0)).a;
	float a_r = texture(TEXTURE, UV + vec2(px.x, 0)).a;
	float a_u = texture(TEXTURE, UV + vec2(0, -px.y)).a;
	float a_d = texture(TEXTURE, UV + vec2(0, px.y)).a;
	float edge = max(0.0, 1.0 - (a_l + a_r + a_u + a_d) / 4.0);
	vec3 result = mix(tex.rgb, atmosphere_color.rgb, vert * falloff_strength * 0.5);
	float rim_weight = (1.0 - vert * 0.6);
	result += rim_color.rgb * edge * rim_strength * rim_weight;
	COLOR = vec4(result, tex.a);
}
"""
	depth_shader = ShaderMaterial.new()
	depth_shader.shader = depth_sh

	_set_direction(0)
	_apply_state("baseline")
	print("Finish Lab: %d captures to make" % total_captures)


func _build_scene() -> void:
	var cam := Camera2D.new()
	cam.position = Vector2(256, 256)
	add_child(cam)

	var ground := ColorRect.new()
	ground.position = Vector2(0, 380)
	ground.size = Vector2(512, 132)
	ground.color = Color(0.12, 0.12, 0.15, 1)
	add_child(ground)

	sprite = Sprite2D.new()
	sprite.position = Vector2(256, 270)
	sprite.scale = Vector2(5, 5)
	sprite.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	add_child(sprite)

	light_moon = PointLight2D.new()
	light_moon.position = Vector2(200, 80)
	light_moon.color = Color(0.45, 0.6, 1.0, 1.0)
	light_moon.energy = 1.4
	light_moon.texture = _make_moon_texture()
	light_moon.texture_scale = 2.0
	light_moon.visible = false
	add_child(light_moon)

	light_torch = PointLight2D.new()
	light_torch.position = Vector2(320, 180)
	light_torch.color = Color(1.0, 0.6, 0.27, 1.0)
	light_torch.energy = 1.2
	light_torch.texture = _make_light_texture()
	light_torch.texture_scale = 2.5
	light_torch.visible = false
	add_child(light_torch)

	particles_ember = GPUParticles2D.new()
	particles_ember.position = Vector2(280, 420)
	particles_ember.amount = 8
	particles_ember.lifetime = 3.5
	particles_ember.emitting = false
	var ember_mat := ParticleProcessMaterial.new()
	ember_mat.direction = Vector3(0, -1, 0)
	ember_mat.spread = 30.0
	ember_mat.initial_velocity_min = 8.0
	ember_mat.initial_velocity_max = 20.0
	ember_mat.gravity = Vector3(0, -15, 0)
	ember_mat.scale_min = 1.0
	ember_mat.scale_max = 2.5
	ember_mat.color = Color(1.0, 0.6, 0.2, 0.85)
	particles_ember.process_material = ember_mat
	add_child(particles_ember)

	particles_dust = GPUParticles2D.new()
	particles_dust.position = Vector2(256, 240)
	particles_dust.amount = 6
	particles_dust.lifetime = 6.0
	particles_dust.emitting = false
	var dust_mat := ParticleProcessMaterial.new()
	dust_mat.direction = Vector3(1, -0.2, 0)
	dust_mat.spread = 120.0
	dust_mat.initial_velocity_min = 2.0
	dust_mat.initial_velocity_max = 5.0
	dust_mat.gravity = Vector3(0, 0, 0)
	dust_mat.scale_min = 2.0
	dust_mat.scale_max = 5.0
	dust_mat.color = Color(0.6, 0.7, 0.9, 0.25)
	particles_dust.process_material = dust_mat
	add_child(particles_dust)


func _make_light_texture() -> GradientTexture2D:
	var tex := GradientTexture2D.new()
	tex.width = 256
	tex.height = 256
	tex.fill = GradientTexture2D.FILL_RADIAL
	tex.fill_from = Vector2(0.5, 0.5)
	tex.fill_to = Vector2(0.5, 1.0)
	var grad := Gradient.new()
	grad.set_color(0, Color.WHITE)
	grad.set_color(1, Color.TRANSPARENT)
	tex.gradient = grad
	return tex


func _make_moon_texture() -> GradientTexture2D:
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


func _set_direction(idx: int) -> void:
	var dir_name: String = DIRECTIONS[idx]
	sprite.texture = canvas_textures[dir_name]


func _apply_state(state: String) -> void:
	light_torch.visible = false
	light_moon.visible = false
	particles_ember.emitting = false
	particles_dust.emitting = false
	sprite.material = null

	match state:
		"baseline":
			pass
		"torch":
			light_torch.visible = true
		"moonlight":
			light_moon.visible = true
		"moon_particles_depth":
			light_moon.visible = true
			particles_dust.emitting = true
			particles_ember.emitting = true
			sprite.material = depth_shader


func _process(_delta: float) -> void:
	if current_dir_idx >= DIRECTIONS.size():
		return

	frame_wait += 1
	if frame_wait < 3:
		return
	frame_wait = 0

	var dir_name: String = DIRECTIONS[current_dir_idx]
	var state_name: String = STATES[current_state_idx]

	var img := get_viewport().get_texture().get_image()
	var path := "%s/pirate_navigator_%s_%s.png" % [SCREENSHOTS_DIR, dir_name, state_name]
	var save_err := img.save_png(path)
	if save_err != OK:
		_fail("save_png failed for %s (err %d)" % [path, save_err])
		return
	captures_done += 1
	print("[%d/%d] Captured: %s" % [captures_done, total_captures, path])

	current_state_idx += 1
	if current_state_idx >= STATES.size():
		current_state_idx = 0
		current_dir_idx += 1
		if current_dir_idx < DIRECTIONS.size():
			_set_direction(current_dir_idx)

	if current_dir_idx >= DIRECTIONS.size():
		print("\n=== ALL CAPTURES COMPLETE ===")
		await get_tree().create_timer(0.5).timeout
		# Only report success (exit 0) if every expected capture was written;
		# otherwise exit non-zero so the driver detects the shortfall (F-005).
		if captures_done == total_captures:
			get_tree().quit(0)
		else:
			_fail("incomplete: %d of %d captures written" % [captures_done, total_captures])
	else:
		_apply_state(STATES[current_state_idx])
