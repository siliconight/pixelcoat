@tool
extends EditorPlugin
## Pixelcoat Importer — Slice 5 of the Generation 7 roadmap.
##
## Adds "Project > Tools > Pixelcoat: Import Pack..." which turns a
## <asset>.pack.json into ready StandardMaterial3D resources (dry and,
## when the pack carries wet maps, wet), fixing each texture's import
## settings first so normals import as normals, roughness gets
## normal-aware mip filtering, and DirectX-convention packs flip green.
## Everything is driven by pack metadata, never filename guessing.

const MENU_LABEL := "Pixelcoat: Import Pack..."

var _dialog: EditorFileDialog


func _enter_tree() -> void:
	add_tool_menu_item(MENU_LABEL, _open_dialog)


func _exit_tree() -> void:
	remove_tool_menu_item(MENU_LABEL)
	if is_instance_valid(_dialog):
		_dialog.queue_free()


func _open_dialog() -> void:
	if not is_instance_valid(_dialog):
		_dialog = EditorFileDialog.new()
		_dialog.file_mode = EditorFileDialog.FILE_MODE_OPEN_FILE
		_dialog.access = EditorFileDialog.ACCESS_RESOURCES
		_dialog.add_filter("*.pack.json", "Pixelcoat packs")
		_dialog.title = "Import Pixelcoat Pack"
		_dialog.file_selected.connect(_on_pack_selected)
		EditorInterface.get_base_control().add_child(_dialog)
	_dialog.popup_centered_ratio(0.6)


func _on_pack_selected(path: String) -> void:
	var importer := preload("res://addons/pixelcoat_importer/pack_importer.gd")
	var result: Dictionary = importer.import_pack(path)
	if result.has("error"):
		push_error("Pixelcoat: %s" % result["error"])
		return
	for line: String in result.get("log", []):
		print("Pixelcoat: %s" % line)
	EditorInterface.get_resource_filesystem().scan()
