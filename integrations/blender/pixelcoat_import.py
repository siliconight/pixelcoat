"""Pixelcoat pack importer for Blender 4.x (Slice 5).

Install: Edit > Preferences > Add-ons > Install... > this file.
Use:     File > Import > Pixelcoat Pack (.pack.json)

Builds a Principled BSDF material from pack metadata (pack/1 or pack/2),
never filename guessing: albedo is sRGB, every data map is Non-Color,
normals go through a Normal Map node (with Y flipped when the pack says
directx), surface_occlusion multiplies into base color the usual way,
and roughness drops straight into the Roughness socket because
Pixelcoat authors it as exactly 1 - gloss.

Detail tiles (pack/2 "detail" block) repeat via a Mapping node scaled to
repeats_per_meter x meters_per_tile and blend over the base color
through the detail mask. Detail normals mix with the base normal by the
same mask before the Normal Map node — a linear approximation, fine at
Gen7 fidelity; swap in reoriented normal mapping if it ever matters.

When the pack carries wet maps a second "<asset>_wet" material is built
so dry/wet previews match what the Godot importer exposes.
"""

bl_info = {
    "name": "Pixelcoat Pack Importer",
    "author": "GabagoolStudios",
    "version": (0, 5, 0),
    "blender": (4, 0, 0),
    "location": "File > Import > Pixelcoat Pack",
    "description": "Import pixelcoat-pack/1 and pack/2 manifests as "
                   "Principled BSDF materials",
    "category": "Import-Export",
}

import json
import os

import bpy
from bpy_extras.io_utils import ImportHelper


def _load_image(pack_dir, fname, non_color):
    img = bpy.data.images.load(os.path.join(pack_dir, fname),
                               check_existing=True)
    if non_color:
        img.colorspace_settings.name = "Non-Color"
    return img


def _tex_node(nodes, links, pack_dir, fname, non_color, loc,
              mapping_out=None):
    node = nodes.new("ShaderNodeTexImage")
    node.image = _load_image(pack_dir, fname, non_color)
    node.location = loc
    if mapping_out is not None:
        links.new(mapping_out, node.inputs["Vector"])
    return node


def build_material(pack_path, wet=False):
    with open(pack_path, encoding="utf-8") as f:
        pack = json.load(f)
    maps = pack["maps"]
    hints = pack.get("import_hints", {})
    pack_dir = os.path.dirname(os.path.abspath(pack_path))
    asset = pack.get("asset_id", "pixelcoat")

    name = f"{asset}_wet" if wet else asset
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()

    out = nodes.new("ShaderNodeOutputMaterial")
    out.location = (900, 0)
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (600, 0)
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    albedo_key = "wet_albedo" if wet and "wet_albedo" in maps else "albedo"
    albedo = _tex_node(nodes, links, pack_dir, maps[albedo_key], False,
                       (-600, 400))
    base_color_out = albedo.outputs["Color"]

    if "surface_occlusion" in maps:
        ao = _tex_node(nodes, links, pack_dir, maps["surface_occlusion"],
                       True, (-600, 100))
        mix = nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.blend_type = "MULTIPLY"
        mix.inputs["Factor"].default_value = 1.0
        mix.location = (-300, 300)
        links.new(base_color_out, mix.inputs["A"])
        links.new(ao.outputs["Color"], mix.inputs["B"])
        base_color_out = mix.outputs["Result"]

    detail = pack.get("detail")
    if detail and "detail_albedo" in maps:
        base_color_out = _wire_detail_albedo(
            nodes, links, pack_dir, pack, maps, base_color_out)

    links.new(base_color_out, bsdf.inputs["Base Color"])

    rough_key = "wet_roughness" if wet and "wet_roughness" in maps \
        else "roughness"
    if rough_key in maps:
        rough = _tex_node(nodes, links, pack_dir, maps[rough_key], True,
                          (-600, -200))
        links.new(rough.outputs["Color"], bsdf.inputs["Roughness"])

    if "metallic" in maps:
        met = _tex_node(nodes, links, pack_dir, maps["metallic"], True,
                        (-600, -450))
        links.new(met.outputs["Color"], bsdf.inputs["Metallic"])

    _wire_normals(nodes, links, pack_dir, pack, maps, hints, bsdf, wet)
    return mat


def _detail_mapping(nodes, links, pack):
    detail = pack.get("detail", {})
    repeats = detail.get("repeats_per_meter", 8.0) \
        * float(pack.get("meters_per_tile", 1.0) or 1.0)
    uv = nodes.new("ShaderNodeUVMap")
    uv.location = (-1200, -100)
    mapping = nodes.new("ShaderNodeMapping")
    mapping.location = (-1000, -100)
    mapping.inputs["Scale"].default_value = (repeats, repeats, 1.0)
    links.new(uv.outputs["UV"], mapping.inputs["Vector"])
    return mapping.outputs["Vector"]


def _wire_detail_albedo(nodes, links, pack_dir, pack, maps, base_out):
    mapping_out = _detail_mapping(nodes, links, pack)
    tile = _tex_node(nodes, links, pack_dir, maps["detail_albedo"], False,
                     (-600, 700), mapping_out)
    mix = nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    blend = pack["detail"].get("blend_mode", "overlay")
    mix.blend_type = {"overlay": "OVERLAY", "multiply": "MULTIPLY",
                      "linear": "MIX"}.get(blend, "OVERLAY")
    mix.location = (-100, 500)
    strength = float(pack["detail"].get("strength", 0.65))
    if "detail_mask" in maps:
        mask = _tex_node(nodes, links, pack_dir, maps["detail_mask"], True,
                         (-600, 950))
        scale = nodes.new("ShaderNodeMath")
        scale.operation = "MULTIPLY"
        scale.inputs[1].default_value = strength
        scale.location = (-350, 900)
        links.new(mask.outputs["Color"], scale.inputs[0])
        links.new(scale.outputs["Value"], mix.inputs["Factor"])
    else:
        mix.inputs["Factor"].default_value = strength
    links.new(base_out, mix.inputs["A"])
    links.new(tile.outputs["Color"], mix.inputs["B"])
    return mix.outputs["Result"]


def _wire_normals(nodes, links, pack_dir, pack, maps, hints, bsdf, wet):
    if "normal" not in maps:
        return
    base_n = _tex_node(nodes, links, pack_dir, maps["normal"], True,
                       (-600, -750))
    normal_color_out = base_n.outputs["Color"]

    detail_key = "wet_detail_normal" if wet and "wet_detail_normal" in maps \
        else "detail_normal"
    if detail_key in maps:
        tiled = pack.get("detail") is not None
        mapping_out = _detail_mapping(nodes, links, pack) if tiled else None
        det_n = _tex_node(nodes, links, pack_dir, maps[detail_key], True,
                          (-600, -1050), mapping_out)
        mix = nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.blend_type = "MIX"
        mix.location = (-300, -850)
        factor = 0.5
        if wet and "wetness" in maps and \
                "wet_detail_strength_scale" in hints:
            factor *= float(hints["wet_detail_strength_scale"])
        if "detail_mask" in maps:
            mask = _tex_node(nodes, links, pack_dir, maps["detail_mask"],
                             True, (-600, -1300))
            scale = nodes.new("ShaderNodeMath")
            scale.operation = "MULTIPLY"
            scale.inputs[1].default_value = factor
            scale.location = (-450, -1250)
            links.new(mask.outputs["Color"], scale.inputs[0])
            links.new(scale.outputs["Value"], mix.inputs["Factor"])
        else:
            mix.inputs["Factor"].default_value = factor
        links.new(normal_color_out, mix.inputs["A"])
        links.new(det_n.outputs["Color"], mix.inputs["B"])
        normal_color_out = mix.outputs["Result"]

    nmap = nodes.new("ShaderNodeNormalMap")
    nmap.location = (0, -750)
    if hints.get("normal_format") == "directx":
        # flip G: separate, invert, recombine
        sep = nodes.new("ShaderNodeSeparateColor")
        sep.location = (-200, -950)
        inv = nodes.new("ShaderNodeMath")
        inv.operation = "SUBTRACT"
        inv.inputs[0].default_value = 1.0
        inv.location = (-100, -1000)
        comb = nodes.new("ShaderNodeCombineColor")
        comb.location = (0, -950)
        links.new(normal_color_out, sep.inputs["Color"])
        links.new(sep.outputs["Red"], comb.inputs["Red"])
        links.new(sep.outputs["Green"], inv.inputs[1])
        links.new(inv.outputs["Value"], comb.inputs["Green"])
        links.new(sep.outputs["Blue"], comb.inputs["Blue"])
        normal_color_out = comb.outputs["Color"]
    links.new(normal_color_out, nmap.inputs["Color"])
    links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])


class IMPORT_OT_pixelcoat_pack(bpy.types.Operator, ImportHelper):
    bl_idname = "import_scene.pixelcoat_pack"
    bl_label = "Pixelcoat Pack (.pack.json)"
    bl_options = {"REGISTER", "UNDO"}

    filename_ext = ".json"
    filter_glob: bpy.props.StringProperty(default="*.pack.json",
                                          options={"HIDDEN"})

    def execute(self, context):
        try:
            mat = build_material(self.filepath, wet=False)
            made = [mat.name]
            with open(self.filepath, encoding="utf-8") as f:
                if "wet_albedo" in json.load(f).get("maps", {}):
                    made.append(build_material(self.filepath,
                                               wet=True).name)
        except (OSError, KeyError, json.JSONDecodeError) as e:
            self.report({"ERROR"}, f"Pixelcoat: {e}")
            return {"CANCELLED"}
        self.report({"INFO"}, "Pixelcoat materials: " + ", ".join(made))
        return {"FINISHED"}


def _menu(self, _context):
    self.layout.operator(IMPORT_OT_pixelcoat_pack.bl_idname)


def register():
    bpy.utils.register_class(IMPORT_OT_pixelcoat_pack)
    bpy.types.TOPBAR_MT_file_import.append(_menu)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(_menu)
    bpy.utils.unregister_class(IMPORT_OT_pixelcoat_pack)


if __name__ == "__main__":
    register()
