extends Node

## Auto-launcher that discovers export packs and spawns PackViewer.
## Set as main scene or autoload to test export packs without manual config.

const EXPORTS_DIR := "F:/AI/star-freight-foundry/exports"


func _ready() -> void:
	var packs := _discover_packs()
	if packs.is_empty():
		print("ERROR: No export packs found in %s" % EXPORTS_DIR)
		get_tree().quit()
		return

	print("Discovered %d export packs:" % packs.size())
	for p in packs:
		print("  %s" % p)

	# Load the viewer scene
	var viewer_scene := load("res://scenes/pack_viewer.tscn")
	var viewer: Node2D = viewer_scene.instantiate()
	viewer.pack_paths = packs
	get_tree().root.call_deferred("add_child", viewer)

	# Remove self
	call_deferred("queue_free")


func _discover_packs() -> Array[String]:
	var result: Array[String] = []
	var dir := DirAccess.open(EXPORTS_DIR)
	if dir == null:
		return result

	# exports/{subject_slug}/{run_id}/manifest.json
	dir.list_dir_begin()
	var subject_dir := dir.get_next()
	while subject_dir != "":
		if dir.current_is_dir():
			var subject_path := EXPORTS_DIR.path_join(subject_dir)
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
