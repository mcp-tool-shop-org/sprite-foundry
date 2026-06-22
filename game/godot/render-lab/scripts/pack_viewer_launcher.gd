extends Node

## Auto-launcher that discovers export packs and spawns PackViewer.
## Set as main scene or autoload to test export packs without manual config.
##
## The exports directory is resolved at runtime (NOT hardcoded to any one rig),
## in priority order:
##   1. --exports=<path> command-line argument
##   2. SPRITE_FOUNDRY_EXPORTS environment variable
##   3. project-relative fallback: <project_dir>/../../../exports
##      (render-lab/ lives at game/godot/render-lab inside the repo, so three
##       levels up from the project dir is the repo root; the Python driver
##       writes export packs under <repo>/exports).
## If the resolved directory cannot be opened, _ready() prints an actionable
## error listing every probe location and quits — it never silently "succeeds".


func _resolve_exports_dir() -> String:
	# 1. CLI arg: --exports=<path>
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--exports="):
			return arg.substr("--exports=".length()).strip_edges()
	for arg in OS.get_cmdline_args():
		if arg.begins_with("--exports="):
			return arg.substr("--exports=".length()).strip_edges()

	# 2. Environment variable
	var env_dir := OS.get_environment("SPRITE_FOUNDRY_EXPORTS")
	if env_dir != "":
		return env_dir.strip_edges()

	# 3. Project-relative fallback (repo-root/exports), portable across rigs
	var project_dir := ProjectSettings.globalize_path("res://")
	return project_dir.path_join("../../../exports").simplify_path()


func _ready() -> void:
	var exports_dir := _resolve_exports_dir()

	if DirAccess.open(exports_dir) == null:
		printerr("ERROR: exports directory could not be opened: %s" % exports_dir)
		printerr("  Set it explicitly via one of:")
		printerr("    - command line:  --exports=<absolute-path-to>/exports")
		printerr("    - environment:   SPRITE_FOUNDRY_EXPORTS=<absolute-path-to>/exports")
		printerr("    - or place export packs at the project-relative default above.")
		get_tree().quit(1)
		return

	var packs := _discover_packs(exports_dir)
	if packs.is_empty():
		printerr("ERROR: No export packs found in %s" % exports_dir)
		printerr("  Expected layout: <exports>/{subject_slug}/{run_id}/manifest.json")
		get_tree().quit(1)
		return

	print("Discovered %d export packs:" % packs.size())
	for p in packs:
		print("  %s" % p)

	# Load the viewer scene
	var viewer_scene := load("res://scenes/pack_viewer.tscn")
	if viewer_scene == null:
		printerr("ERROR: could not load res://scenes/pack_viewer.tscn")
		get_tree().quit(1)
		return
	var viewer: Node2D = viewer_scene.instantiate()
	viewer.pack_paths = packs
	get_tree().root.call_deferred("add_child", viewer)

	# Remove self
	call_deferred("queue_free")


func _discover_packs(exports_dir: String) -> Array[String]:
	var result: Array[String] = []
	var dir := DirAccess.open(exports_dir)
	if dir == null:
		return result

	# exports/{subject_slug}/{run_id}/manifest.json
	dir.list_dir_begin()
	var subject_dir := dir.get_next()
	while subject_dir != "":
		if dir.current_is_dir():
			var subject_path := exports_dir.path_join(subject_dir)
			var sub := DirAccess.open(subject_path)
			if sub:
				sub.list_dir_begin()
				var run_dir := sub.get_next()
				while run_dir != "":
					if sub.current_is_dir():
						var pack_path := subject_path.path_join(run_dir)
						var manifest_path := pack_path.path_join("manifest.json")
						if FileAccess.file_exists(manifest_path):
							result.append(pack_path)
					run_dir = sub.get_next()
				sub.list_dir_end()
		subject_dir = dir.get_next()
	dir.list_dir_end()
	return result
