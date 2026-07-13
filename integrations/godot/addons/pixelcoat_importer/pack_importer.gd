@tool
extends RefCounted
## Pack -> StandardMaterial3D. Pure logic, callable headless:
##   pack_importer.import_pack("res://materials/wall/wall.pack.json")
##
## pack/1 (pixel mode) and pack/2 (generation_7) both import; pack/2
## import_hints drive texture import settings and material wiring.
##
## Gen7 -> StandardMaterial3D mapping notes:
##  - Pixelcoat's specular/gloss workflow lands on Godot's metallic/
##    roughness: the roughness map is authored as exactly 1 - gloss, so
##    it drops straight in; the specular map has no per-pixel slot in
##    StandardMaterial3D and informs nothing here (kept in the pack for
##    ShaderMaterial users).
##  - surface_occlusion -> AO slot (it is surface cavity shading, not
##    baked scene AO — exactly what the slot is for on a material).
##  - detail tiles ride UV2 with uv2_scale = repeats_per_meter *
##    meters_per_tile, so meshes need UV2 (a plain unwrap copy of UV1 is
##    fine). Packs without tiles wire the full-res micro normal on UV1.
##  - "overlay" and "linear" detail blends approximate to MIX (the tile
##    is neutral mid-gray, so MIX at the mask's strength reads right);
##    "multiply" maps to MUL.
##  - Parallax stays off by default (2006 answer: it usually is not
##    worth the fill cost); flip ENABLE_HEIGHTMAP if wanted.

const ENABLE_HEIGHTMAP := false

const _DETAIL_BLEND := {
	"overlay": BaseMaterial3D.BLEND_MODE_MIX,
	"linear": BaseMaterial3D.BLEND_MODE_MIX,
	"multiply": BaseMaterial3D.BLEND_MODE_MUL,
}


static func import_pack(pack_path: String) -> Dictionary:
	var raw := FileAccess.get_file_as_string(pack_path)
	if raw.is_empty():
		return {"error": "cannot read %s" % pack_path}
	var pack: Variant = JSON.parse_string(raw)
	if typeof(pack) != TYPE_DICTIONARY or not pack.has("maps"):
		return {"error": "%s is not a pixelcoat pack" % pack_path}

	var dir := pack_path.get_base_dir()
	var maps: Dictionary = pack["maps"]
	var hints: Dictionary = pack.get("import_hints", {})
	var log: Array[String] = []

	var reimport := _fix_texture_imports(dir, maps, hints, log)
	if not reimport.is_empty() and Engine.is_editor_hint():
		EditorInterface.get_resource_filesystem() \
				.reimport_files(PackedStringArray(reimport))

	var asset: String = pack.get("asset_id", pack_path.get_file()
			.trim_suffix(".pack.json"))
	var dry := _build_material(dir, pack, maps, hints, false)
	var dry_path := dir.path_join("%s_material.tres" % asset)
	var err := ResourceSaver.save(dry, dry_path)
	if err != OK:
		return {"error": "saving %s failed (%d)" % [dry_path, err]}
	log.append("material -> %s" % dry_path)

	if maps.has("wet_albedo"):
		var wet := _build_material(dir, pack, maps, hints, true)
		var wet_path := dir.path_join("%s_material_wet.tres" % asset)
		err = ResourceSaver.save(wet, wet_path)
		if err != OK:
			return {"error": "saving %s failed (%d)" % [wet_path, err]}
		log.append("wet material -> %s" % wet_path)
	return {"log": log}


# ------------------------------------------------- texture import setup

static func _fix_texture_imports(dir: String, maps: Dictionary,
		hints: Dictionary, log: Array[String]) -> Array[String]:
	var normal_names := ["normal", "detail_normal", "wet_detail_normal"]
	var flip_green: bool = hints.get("normal_format", "opengl") == "directx"
	var gen_mips: bool = hints.get("generate_mipmaps", true)
	var normal_file: String = maps.get("normal", "")
	var changed: Array[String] = []

	for map_name: String in maps:
		var tex_path: String = dir.path_join(maps[map_name])
		var cfg := ConfigFile.new()
		var import_path := tex_path + ".import"
		cfg.load(import_path)  # missing file is fine; scan creates later
		cfg.set_value("remap", "importer", "texture")
		cfg.set_value("remap", "type", "CompressedTexture2D")
		cfg.set_value("params", "mipmaps/generate", gen_mips)
		cfg.set_value("params", "detect_3d/compress_to", 0)
		if map_name in normal_names:
			cfg.set_value("params", "compress/normal_map", 1)
			cfg.set_value("params", "process/normal_map_invert_y",
					flip_green)
		elif map_name.ends_with("roughness"):
			cfg.set_value("params", "roughness/mode", 2)  # red channel
			if not normal_file.is_empty():
				cfg.set_value("params", "roughness/src_normal",
						dir.path_join(normal_file))
		if cfg.save(import_path) == OK:
			changed.append(tex_path)
		else:
			log.append("could not write %s (will import with defaults)"
					% import_path)
	return changed


# ------------------------------------------------------ material wiring

static func _build_material(dir: String, pack: Dictionary,
		maps: Dictionary, hints: Dictionary,
		wet: bool) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_texture = _tex(dir, maps,
			"wet_albedo" if wet else "albedo")

	if maps.has("normal"):
		m.normal_enabled = true
		m.normal_texture = _tex(dir, maps, "normal")

	var rough_key := "wet_roughness" if wet and maps.has("wet_roughness") \
			else "roughness"
	if maps.has(rough_key):
		m.roughness = 1.0
		m.roughness_texture = _tex(dir, maps, rough_key)
		m.roughness_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_RED

	if maps.has("metallic"):
		m.metallic = 1.0
		m.metallic_texture = _tex(dir, maps, "metallic")
		m.metallic_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_RED

	if maps.has("surface_occlusion"):
		m.ao_enabled = true
		m.ao_texture = _tex(dir, maps, "surface_occlusion")
		m.ao_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_RED

	if ENABLE_HEIGHTMAP and maps.has("height"):
		m.heightmap_enabled = true
		m.heightmap_texture = _tex(dir, maps, "height")

	_wire_detail(m, dir, pack, maps, wet)

	if pack.get("tileable") != null:
		m.texture_repeat = true
	return m


static func _wire_detail(m: StandardMaterial3D, dir: String,
		pack: Dictionary, maps: Dictionary, wet: bool) -> void:
	var detail_key := "detail_normal"
	if wet and maps.has("wet_detail_normal"):
		detail_key = "wet_detail_normal"
	if not (maps.has(detail_key) or maps.has("detail_albedo")):
		return

	m.detail_enabled = true
	if maps.has("detail_albedo"):
		m.detail_albedo = _tex(dir, maps, "detail_albedo")
	if maps.has(detail_key):
		m.detail_normal = _tex(dir, maps, detail_key)
	if maps.has("detail_mask"):
		m.detail_mask = _tex(dir, maps, "detail_mask")

	if pack.has("detail"):
		# Repeating tile (pack/2 detail block): ride UV2, scaled.
		var d: Dictionary = pack["detail"]
		m.detail_blend_mode = _DETAIL_BLEND.get(
				d.get("blend_mode", "overlay"),
				BaseMaterial3D.BLEND_MODE_MIX)
		m.detail_uv_layer = BaseMaterial3D.DETAIL_UV_2
		var repeats: float = d.get("repeats_per_meter", 8.0) \
				* float(pack.get("meters_per_tile", 1.0))
		m.uv2_scale = Vector3(repeats, repeats, 1.0)
	else:
		# Full-res micro normal: same UVs as the base maps.
		m.detail_uv_layer = BaseMaterial3D.DETAIL_UV_1
		m.detail_blend_mode = BaseMaterial3D.BLEND_MODE_MIX


static func _tex(dir: String, maps: Dictionary, key: String) -> Texture2D:
	return load(dir.path_join(maps[key])) as Texture2D
