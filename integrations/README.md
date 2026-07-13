# Pixelcoat integrations (Slice 5)

Importers driven by pack metadata (`<asset>.pack.json`), never filename
guessing. Both read pack/1 (pixel mode) and pack/2 (generation_7).

## Godot 4.7 — `godot/addons/pixelcoat_importer/`

Install: copy `addons/pixelcoat_importer/` into your project's `addons/`
folder and enable it in Project Settings > Plugins. Put the whole pack
folder (PNGs + `.pack.json`) anywhere under `res://` first and let the
initial import scan finish.

Use: **Project > Tools > Pixelcoat: Import Pack...** and pick the
`.pack.json`. The importer:

1. Fixes each texture's import settings from `import_hints` — normals
   import as normal maps (green flipped for directx packs), the
   roughness map gets Godot's normal-aware roughness mip filtering via
   `roughness/src_normal`, mipmaps follow the pack — then reimports.
2. Writes `<asset>_material.tres` (StandardMaterial3D) next to the
   pack: albedo, normal, roughness (R channel, drops straight in since
   Pixelcoat authors roughness as exactly `1 - gloss`), metallic when
   present, `surface_occlusion` on the AO slot.
3. Detail: pack/2 tiles ride **UV2** with
   `uv2_scale = repeats_per_meter x meters_per_tile` — meshes need a
   UV2 (a copy of UV1 is fine). Packs without tiles wire the full-res
   micro normal on UV1. `overlay`/`linear` blends approximate to MIX
   (tiles are neutral mid-gray so this reads correctly); `multiply`
   maps to MUL.
4. When the pack carries wet maps, `<asset>_material_wet.tres` is also
   written (wet albedo/roughness, wet detail response).

Parallax is off by default (`ENABLE_HEIGHTMAP` in `pack_importer.gd`).
The specular map has no per-pixel StandardMaterial3D slot; it stays in
the pack for ShaderMaterial users.

`pack_importer.gd` is pure logic — usable headless or from your own
tools: `pack_importer.import_pack("res://path/to/x.pack.json")`.

## Blender 4.x — `blender/pixelcoat_import.py`

Install: Edit > Preferences > Add-ons > Install... > pick the file,
enable "Pixelcoat Pack Importer".

Use: **File > Import > Pixelcoat Pack (.pack.json)**. Builds a
Principled BSDF material (plus `<asset>_wet` when wet maps exist):
albedo sRGB, every data map Non-Color, AO multiplied into base color,
normals through a Normal Map node (green flipped for directx packs),
detail tiles repeated by a Mapping node and blended through the detail
mask. Detail normals mix with the base normal by mask before the Normal
Map node — a linear approximation, fine at Gen7 fidelity.

## Variation exports

`generation_7.variations: ["darker", "lighter", "dirtier", "damaged"]`
adds one-recipe albedo variants (plus roughness where the variant
shifts gloss) to the pack with identical UV boundaries — listed under
`pack.variants`. Wet is the fifth variant and remains its own toggle.
Importers currently wire base + wet; variant materials are one texture
swap away.
