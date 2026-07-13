"""Generation 7 surface-skin pipeline (roadmap Slices 2–3).

Load -> Transform -> Working Resolution -> Linear -> Lighting Flatten ->
Edge-Preserving Cleanup -> Frequency Separation -> Base-Color Stylization
-> Macro/Micro Height -> Base/Detail Normal -> Cavity/Surface Occlusion ->
Material Response -> Weathering -> Tile Validation -> Export.

A separate deterministic graph from pixel mode — NOT a higher-resolution
pixel treatment. It bypasses low-color palettes, value banding, pixel-grid
dithering, nearest-neighbor scaling, and stepped PS1 roughness. Optional
moderate OKLab color clustering (32..256) is the only quantization, and
dithering does not exist here.

Everything math happens on linear working data; display albedo is encoded
back to sRGB at export; data maps stay linear. Same source bytes + recipe
+ seed + version = byte-identical canonical outputs.
"""

from __future__ import annotations

import json
import os
import time

import numpy as np
from PIL import Image

from ..recipe import Recipe
from ..version import __version__
from . import (color_space as cs, detail_texture as dtex, frequency,
               image_io, lighting_flatten, maps, material_response as mr,
               preview as pv, quantization, tiling, transforms, weathering)

_RESAMPLE = {"lanczos": Image.LANCZOS, "bicubic": Image.BICUBIC,
             "box": Image.BOX}
_SEAM_TOLERANCE = 2.5 / 255.0
_CHUNK = 1 << 18  # pixels per nearest-palette mapping block


def build_generation_7(recipe: Recipe, out_dir: str) -> dict:
    t0 = time.perf_counter()
    g = recipe.generation_7
    warnings: list[str] = []

    # ---------------------------------------------------- load + resolve
    src, sha = image_io.load(recipe.source_path)
    w, h = g.resolution.working_width, g.resolution.working_height
    _resolution_warnings(src, w, h, warnings)

    arr = transforms.apply(src, recipe.transform.crop,
                           recipe.transform.perspective_quad,
                           recipe.transform.rotation_degrees, (w, h))
    im = Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8), "RGBA")
    im = im.resize((w, h), _RESAMPLE[g.resolution.resample_method])
    arr = np.asarray(im, np.float32) / 255.0
    alpha = arr[..., 3:4]

    wrap_x = recipe.tiling.enabled and recipe.tiling.axes in ("x", "both")
    wrap_y = recipe.tiling.enabled and recipe.tiling.axes in ("y", "both")

    # ------------------------------------------------- linear + flatten
    lin = cs.srgb_to_linear(arr[..., :3])
    if recipe.tiling.enabled:
        lin = np.clip(tiling.make_tileable_wrap(lin, recipe.tiling.axes),
                      0, 1)

    lin = lighting_flatten.flatten(
        lin, g.color.lighting_flatten_strength, g.color.illumination_radius,
        g.color.shadow_recovery, g.color.highlight_compression,
        wrap_x, wrap_y)
    lin = frequency.edge_preserving_smooth(
        lin, g.cleanup.strength, g.cleanup.chroma_strength, wrap_x, wrap_y)

    # ------------------------------------------- frequency (pre-stylize)
    # Bands come from the cleaned, pre-cluster luminance so optional color
    # clustering can never band the height fields.
    luma = cs.luminance(lin)
    macro_band, micro_detail = frequency.separate(
        luma, g.frequency.macro_radius, g.frequency.micro_radius,
        g.frequency.noise_threshold, g.frequency.detail_gain,
        wrap_x, wrap_y)

    # ------------------------------------------------------- stylize
    preset = mr.PRESETS[g.material.preset]
    albedo = _stylize(lin, g, preset, wrap_x, wrap_y)

    # ------------------------------------------------------- heights
    macro_h, micro_h, combined_h = _heights(
        recipe, g, preset, macro_band, micro_detail, warnings,
        wrap_x, wrap_y)

    # ------------------------------------------------------- normals
    # With a repeating detail tile enabled the Gen7-authentic split
    # applies: the BASE normal absorbs unique micro features (combined
    # height) and the detail slot carries the small repeating tile.
    # Without it, v0.3 behavior byte-for-byte: base=macro, detail=micro.
    detail_on = g.detail_texture.enabled
    tile_albedo = tile_normal = detail_mask = None
    if detail_on:
        tile_albedo, tile_normal, detail_mask = dtex.build(
            g, lin, micro_detail, preset, warnings, wrap_x, wrap_y)
    base_h_src = combined_h if detail_on else macro_h
    base_normal = maps.normal_from_height(
        base_h_src, g.normal.base_strength * preset.base_normal * 4.0,
        wrap_x, wrap_y, g.normal.flip_green)
    detail_normal = tile_normal if detail_on else maps.normal_from_height(
        micro_h, g.normal.detail_strength * preset.detail_normal * 4.0,
        wrap_x, wrap_y, g.normal.flip_green)

    # ------------------------------------------- cavity + occlusion
    cavity_recess = _recess(combined_h, radius=2, wrap_x=wrap_x,
                            wrap_y=wrap_y)
    occlusion_recess = _recess(combined_h,
                               radius=max(4, g.frequency.macro_radius * 2),
                               wrap_x=wrap_x, wrap_y=wrap_y)
    cavity_map = np.clip(1.0 - cavity_recess, 0.0, 1.0)
    surface_occlusion = np.clip(1.0 - 0.85 * occlusion_recess, 0.0, 1.0)

    # ------------------------------------------------ material response
    spec_level = (g.material.specular_level
                  if g.material.specular_level is not None
                  else preset.specular_level)
    base_gloss = (g.material.gloss if g.material.gloss is not None
                  else preset.gloss)
    variation = (g.material.roughness_variation
                 if g.material.roughness_variation is not None
                 else preset.roughness_variation)
    gloss = mr.gloss_map(preset, micro_detail, cavity_recess,
                         base_gloss, variation)
    specular = mr.specular_map(preset, spec_level, cavity_recess)

    # ------------------------------------------------------ weathering
    wthr = g.weathering
    wear = weathering.edge_wear_mask(macro_h, wthr.edge_wear, wthr.seed,
                                     wrap_x, wrap_y)
    grime = weathering.grime_mask(cavity_recess, wthr.cavity_grime,
                                  wthr.seed, wrap_x, wrap_y)
    vertical = wthr.streak_direction in ("down", "up")
    streak_wrap = wrap_y if vertical else wrap_x
    streak_cross = wrap_x if vertical else wrap_y
    streak_src = np.clip(grime + wear * 0.5, 0.0, 1.0)
    streak = weathering.streaks(streak_src, wthr.streaks, wthr.streak_decay,
                                wthr.streak_direction, wthr.seed,
                                streak_wrap, streak_cross)
    rust = weathering.streaks(
        np.clip(wear + cavity_recess * 0.4, 0.0, 1.0),
        wthr.rust_bleed, min(0.97, wthr.streak_decay + 0.03),
        wthr.streak_direction, wthr.seed + 7, streak_wrap, streak_cross) \
        if wthr.rust_bleed > 0 else np.zeros_like(wear)

    albedo, gloss = _apply_weathering(albedo, gloss, preset,
                                      wear, grime, streak, rust)
    roughness = mr.roughness_from_gloss(gloss)
    metallic = mr.metallic_map(preset, wear) \
        if g.material.emit_metallic else None

    # -------------------------------------------------------- wetness
    wet: dict[str, np.ndarray] = {}
    if g.wetness.enabled and g.wetness.amount > 0.0:
        wmask = weathering.wetness_mask(
            cavity_recess, g.wetness.amount, g.wetness.cavity_bias,
            g.wetness.bottom_bias, wthr.seed, wrap_x, wrap_y)
        wet["wetness"] = wmask
        wet["wet_albedo"] = np.clip(
            albedo * (1.0 - preset.wet_darken * wmask[..., None]), 0, 1)
        wet_gloss = np.clip(
            gloss + preset.wet_gloss_boost * wmask, 0.0, 1.0)
        wet["wet_roughness"] = mr.roughness_from_gloss(wet_gloss)
        if not detail_on:
            # Micro-normal response softens only inside the wetness mask.
            # With a repeating detail tile the importer applies the same
            # softening by scaling detail strength with wetness x mask
            # (wet_detail_strength_scale in import_hints).
            wet["wet_detail_normal"] = maps.normal_from_height(
                np.clip(0.5 + (micro_h - 0.5) * (1.0 - 0.7 * wmask), 0, 1),
                g.normal.detail_strength * preset.detail_normal * 4.0,
                wrap_x, wrap_y, g.normal.flip_green)

    # ------------------------------------------------------ variations
    # One-recipe variants (§17): same UV boundaries, driven by the same
    # masks the pack already exports. Albedo always; roughness only where
    # the variant shifts gloss.
    variants: dict[str, tuple[np.ndarray, bool]] = {}
    for v in g.variations:
        if v == "darker":
            variants["albedo_darker"] = (np.clip(albedo * 0.72, 0, 1), True)
        elif v == "lighter":
            variants["albedo_lighter"] = (
                np.clip(1.0 - (1.0 - albedo) * 0.75, 0, 1), True)
        elif v == "dirtier":
            a2, gl2 = _apply_weathering(
                albedo, gloss, preset,
                wear * 0.0, np.clip(grime * 1.6, 0, 1),
                np.clip(streak * 1.6, 0, 1), rust * 0.0)
            variants["albedo_dirtier"] = (a2, True)
            variants["roughness_dirtier"] = (
                mr.roughness_from_gloss(gl2), False)
        elif v == "damaged":
            a2, gl2 = _apply_weathering(
                albedo, gloss, preset,
                np.clip(wear * 2.2 + cavity_recess * 0.3, 0, 1),
                grime * 0.0, streak * 0.0, rust * 0.0)
            variants["albedo_damaged"] = (a2, True)
            variants["roughness_damaged"] = (
                mr.roughness_from_gloss(gl2), False)

    # -------------------------------------------------------- assemble
    out_maps: dict[str, tuple[np.ndarray, bool]] = {  # name -> (arr, srgb)
        "albedo": (np.concatenate(
            [cs.linear_to_srgb(albedo), alpha], axis=-1), True),
        "normal": (base_normal, False),
        "detail_normal": (detail_normal, False),
        "specular": (maps.to_rgb(specular), False),
        "gloss": (maps.to_rgb(gloss), False),
        "height": (maps.to_rgb(combined_h), False),
        "cavity": (maps.to_rgb(cavity_map), False),
        "surface_occlusion": (maps.to_rgb(surface_occlusion), False),
    }
    if g.material.emit_roughness:
        out_maps["roughness"] = (maps.to_rgb(roughness), False)
    if metallic is not None:
        out_maps["metallic"] = (maps.to_rgb(metallic), False)
    if wthr.edge_wear > 0:
        out_maps["wear"] = (maps.to_rgb(wear), False)
    if wthr.cavity_grime > 0:
        out_maps["grime"] = (maps.to_rgb(grime), False)
    if wthr.streaks > 0:
        out_maps["streaks"] = (maps.to_rgb(streak), False)
    if wthr.rust_bleed > 0:
        out_maps["rust"] = (maps.to_rgb(rust), False)
    for name, arr_ in wet.items():
        if name == "wet_albedo":
            out_maps[name] = (np.concatenate(
                [cs.linear_to_srgb(arr_), alpha], axis=-1), True)
        elif name.endswith("normal"):
            out_maps[name] = (arr_, False)
        else:
            out_maps[name] = (maps.to_rgb(arr_), False)

    for name, (arr_, is_color) in variants.items():
        if is_color:
            out_maps[name] = (np.concatenate(
                [cs.linear_to_srgb(arr_), alpha], axis=-1), True)
        else:
            out_maps[name] = (maps.to_rgb(arr_), False)

    # Detail tiles are their own repeat unit: exported unpadded, always
    # wrap-continuous on both axes, and validated as such.
    tile_maps: dict[str, tuple[np.ndarray, bool]] = {}
    if detail_on:
        out_maps.pop("detail_normal")            # moves to the tile set
        tile_maps["detail_albedo"] = (cs.linear_to_srgb(tile_albedo), True)
        tile_maps["detail_normal"] = (tile_normal, False)
        out_maps["detail_mask"] = (maps.to_rgb(detail_mask), False)

    _validate_seams(out_maps, wrap_x, wrap_y, warnings)
    if tile_maps:
        _validate_seams(tile_maps, True, True, warnings)
    if recipe.tiling.enabled:
        pv.landmark_warnings(cs.luminance(albedo), warnings)

    # ---------------------------------------------------------- export
    pad = recipe.export.padding
    asset_dir = os.path.join(out_dir, recipe.asset_id)
    os.makedirs(asset_dir, exist_ok=True)
    map_files: dict[str, str] = {}
    for name, (arr_, _srgb) in out_maps.items():
        if pad > 0:
            arr_ = np.pad(arr_, ((pad, pad), (pad, pad), (0, 0)),
                          mode="edge")
        p = os.path.join(asset_dir, f"{recipe.asset_id}_{name}.png")
        image_io.save_png(arr_, p)
        map_files[name] = os.path.basename(p)
    for name, (arr_, _srgb) in tile_maps.items():   # repeat units: no pad
        p = os.path.join(asset_dir, f"{recipe.asset_id}_{name}.png")
        image_io.save_png(arr_, p)
        map_files[name] = os.path.basename(p)
    recipe.save(os.path.join(asset_dir, f"{recipe.asset_id}.pixelcoat.json"))

    preview_report = _previews(recipe, g, out_maps, tile_maps, asset_dir,
                               warnings)

    pack = _pack_manifest(recipe, g, preset, map_files, sha)
    with open(os.path.join(asset_dir, f"{recipe.asset_id}.pack.json"),
              "w", encoding="utf-8") as f:
        json.dump(pack, f, indent=2, sort_keys=True)

    report = {
        "tool_version": __version__,
        "asset_id": recipe.asset_id,
        "processing_mode": "generation_7",
        "material_profile": preset.name,
        "source_sha256": sha,
        "working_resolution": [w, h],
        "output_resolution": [w + 2 * pad, h + 2 * pad],
        "weathering_seed": wthr.seed,
        "maps": sorted(map_files),
        "files": sorted(map_files.values()) + [
            f"{recipe.asset_id}.pack.json"],
        "warnings": warnings,
        "duration_seconds": round(time.perf_counter() - t0, 4),
    }
    if preview_report:
        report["preview"] = preview_report
    with open(os.path.join(asset_dir, "build_report.json"), "w",
              encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    return report


# ---------------------------------------------------------------- stages

def _previews(recipe: Recipe, g, out_maps: dict, tile_maps: dict,
              asset_dir: str, warnings: list[str]) -> dict | None:
    """Roadmap §18–19: preview-only outputs under <asset>/previews/.
    Never touches a canonical export."""
    want_mips = g.preview.generate_mipmaps
    want_bc = g.preview.compression_preview == "legacy_bc"
    if not (want_mips or want_bc):
        return None

    pdir = os.path.join(asset_dir, "previews")
    os.makedirs(pdir, exist_ok=True)
    all_maps = {**out_maps, **tile_maps}
    rep: dict = {"directory": "previews"}

    if want_mips:
        rep["mip_strips"] = {}
        for name in ("albedo", "normal", "detail_normal", "roughness"):
            if name not in all_maps:
                continue
            arr, _srgb = all_maps[name]
            levels, lengths = pv.mip_chain(arr, name.endswith("normal"))
            strip = pv.mip_strip(levels)
            fname = f"{recipe.asset_id}_{name}_mipstrip.png"
            image_io.save_png(strip, os.path.join(pdir, fname))
            rep["mip_strips"][name] = fname
            if name.endswith("normal") and len(lengths) > 3                     and lengths[3] < 0.82:
                warnings.append(
                    f"{name}: high-frequency detail averages to short "
                    f"normals at distance (mip3 mean length "
                    f"{lengths[3]:.2f}) and will shimmer; use roughness "
                    "filtering with the source normal in Godot")
        n_levels = max(2, int(np.log2(
            max(8, min(a.shape[0] for a, _ in out_maps.values()) // 8)))
        )
        rep["recommended_mip_at_preview_distance"] = pv.recommended_mip(
            g.preview.preview_distance_meters,
            recipe.export.meters_per_tile or 1.0,
            next(iter(out_maps.values()))[0].shape[1], n_levels)

    if want_bc:
        rep["compression"] = {}
        for name, (arr, _srgb) in all_maps.items():
            fam = pv.suggest_family(
                name, has_varying_alpha=(
                    arr.shape[-1] > 3 and float(arr[..., 3].std()) > 1e-4))
            bc = pv.preview_block_compression(arr, fam)
            fname = f"{recipe.asset_id}_{name}_bc.png"
            image_io.save_png(bc, os.path.join(pdir, fname))
            rep["compression"][name] = {
                "family": fam, "file": fname,
                "mean_abs_error": round(
                    float(np.abs(bc[..., :3] - arr[..., :3]).mean()), 5)}

    if recipe.tiling.enabled and "albedo" in out_maps:
        grid = pv.tile_grid(out_maps["albedo"][0])
        fname = f"{recipe.asset_id}_tile3x3.png"
        image_io.save_png(grid, os.path.join(pdir, fname))
        rep["tile_grid"] = fname
    return rep



def _stylize(lin: np.ndarray, g, preset, wrap_x: bool,
             wrap_y: bool) -> np.ndarray:
    """Base-color stylization (§7): art-directed, not an unchanged photo.
    Saturation scaling, local contrast, and optional MODERATE perceptual
    clustering — never the pixel path's low-color/dither treatment."""
    sat = g.color.saturation_scale * preset.saturation_scale
    luma = cs.luminance(lin)
    out = luma[..., None] + (lin - luma[..., None]) * sat

    lc = g.color.local_contrast
    if lc > 0.0:
        base = frequency.smooth_blur(luma, 6, wrap_x, wrap_y)
        boosted = np.clip(luma + (luma - base) * lc * 2.0, 0.0, 1.0)
        out = cs.scale_to_luminance(out, boosted)
    out = np.clip(out, 0.0, 1.0)

    k = g.color.maximum_colors
    if k >= 8:
        srgb = cs.linear_to_srgb(out)
        flat = srgb.reshape(-1, 3)
        palette = quantization.extract_palette_large(flat, k,
                                                     g.weathering.seed)
        pal_lab = quantization.srgb_to_oklab(palette).astype(np.float32)
        pal_sq = (pal_lab ** 2).sum(axis=1)
        idx = np.empty(len(flat), np.int64)
        for s in range(0, len(flat), _CHUNK):
            lab = quantization.srgb_to_oklab(
                flat[s:s + _CHUNK]).astype(np.float32)
            # argmin over ||a-b||^2 = ||b||^2 - 2 a.b (||a||^2 constant/row)
            d = pal_sq[None, :] - 2.0 * (lab @ pal_lab.T)
            idx[s:s + _CHUNK] = d.argmin(axis=1)
        srgb = palette[idx].reshape(srgb.shape)
        out = cs.srgb_to_linear(srgb)
    return out.astype(np.float32)


def _heights(recipe: Recipe, g, preset, macro_band: np.ndarray,
             micro_detail: np.ndarray, warnings: list[str],
             wrap_x: bool, wrap_y: bool
             ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Macro + micro + combined height fields, 0.5-centered (§8).
    Material-aware: presets weight the bands; concrete suppresses broad
    luminance gradients so lighting drift never reads as slope; imported
    height replaces or blends with the inferred macro field."""
    macro = macro_band
    if preset.suppress_macro_gradients:
        broad = frequency.smooth_blur(macro, g.frequency.macro_radius * 3,
                                      wrap_x, wrap_y)
        macro = macro - broad + float(broad.mean())
    macro = cs.normalize01(macro)

    if g.height.source in ("imported", "combined"):
        imp = _load_height(recipe, g.height.import_path,
                           macro.shape, warnings)
        macro = imp if g.height.source == "imported" \
            else 0.5 * macro + 0.5 * imp

    if g.height.invert:
        macro = 1.0 - macro

    macro_h = np.clip(
        0.5 + (macro - 0.5) * g.height.macro_strength * preset.macro_weight,
        0.0, 1.0).astype(np.float32)
    micro_h = np.clip(
        0.5 + micro_detail * 2.0 * g.height.micro_strength
        * preset.micro_weight, 0.0, 1.0).astype(np.float32)
    combined = np.clip(macro_h + (micro_h - 0.5), 0.0, 1.0)
    return macro_h, micro_h, combined.astype(np.float32)


def _load_height(recipe: Recipe, path: str, shape, warnings) -> np.ndarray:
    if not os.path.isabs(path):
        path = os.path.join(os.path.dirname(
            os.path.abspath(recipe.source_path)), path)
    arr, _ = image_io.load(path)
    im = Image.fromarray((arr * 255).astype(np.uint8), "RGBA")
    if (im.height, im.width) != shape:
        warnings.append(
            f"imported height resized {im.width}x{im.height} -> "
            f"{shape[1]}x{shape[0]}")
        im = im.resize((shape[1], shape[0]), Image.LANCZOS)
    a = np.asarray(im, np.float32) / 255.0
    return cs.luminance(cs.srgb_to_linear(a[..., :3]))


def _recess(height: np.ndarray, radius: int, wrap_x: bool,
            wrap_y: bool) -> np.ndarray:
    """Normalized recess field: blur(height) - height, positive where the
    surface dips below its neighborhood (§10)."""
    r = np.maximum(
        frequency.box_blur(height, radius, wrap_x, wrap_y) - height, 0.0)
    m = float(r.max())
    return (r / m if m > 1e-5 else r).astype(np.float32)


def _apply_weathering(albedo, gloss, preset, wear, grime, streak, rust):
    """Every effect is driven by the exported masks (§12–§14): wear
    reveals undercoat on raised edges and shifts gloss; grime darkens and
    roughens cavities; streaks carry grime downstream; rust bleeds warm
    and rough."""
    under = np.array(preset.undercoat, np.float32)
    wearc = np.clip(wear, 0, 1)[..., None]
    luma = cs.luminance(albedo)[..., None]
    desat = luma + (albedo - luma) * (1.0 - preset.wear_desaturate)
    worn = desat * 0.35 + under * 0.65
    albedo = albedo * (1 - wearc) + worn * wearc
    gloss = np.clip(gloss + preset.wear_gloss_shift * wear, 0, 1)

    dirt = np.clip(grime + streak * 0.8, 0.0, 1.0)[..., None]
    grime_c = np.array(preset.grime_color, np.float32)
    albedo = albedo * (1 - dirt * 0.85) + grime_c * dirt * 0.85
    gloss = np.clip(gloss - preset.grime_roughen * dirt[..., 0], 0, 1)

    if rust.max() > 0:
        rust_c = np.array((0.28, 0.10, 0.04), np.float32)
        rc = np.clip(rust, 0, 1)[..., None]
        albedo = albedo * (1 - rc * 0.7) + rust_c * rc * 0.7
        gloss = np.clip(gloss - 0.25 * rust, 0, 1)
    return np.clip(albedo, 0, 1).astype(np.float32), \
        gloss.astype(np.float32)


def _resolution_warnings(src: np.ndarray, w: int, h: int,
                         warnings: list[str]) -> None:
    for name, v in (("width", w), ("height", h)):
        if v & (v - 1):
            warnings.append(f"{name} {v} is not a power of two")
        if v % 4:
            warnings.append(f"{name} {v} is not a multiple of four "
                            f"(block compression needs 4x4 blocks)")
    if w > src.shape[1] * 2 or h > src.shape[0] * 2:
        warnings.append(
            f"requested {w}x{h} exceeds useful detail of the "
            f"{src.shape[1]}x{src.shape[0]} source")


def _validate_seams(out_maps: dict, wrap_x: bool, wrap_y: bool,
                    warnings: list[str]) -> None:
    """Tile validation (§17): the step across the seam must be
    statistically indistinguishable from an ordinary interior pixel step.
    Exact edge equality is the wrong test — a tileable brick wall still
    has mortar-to-brick transitions AT the boundary. Instead, every
    adjacent row/column pair gets a mean-difference score and the seam
    pair must sit inside the distribution of interior pairs."""
    for name, (arr, _srgb) in out_maps.items():
        if wrap_x:
            _seam_axis(name, "x", arr, axis=1, warnings=warnings)
        if wrap_y:
            _seam_axis(name, "y", arr, axis=0, warnings=warnings)


def _seam_axis(name: str, label: str, arr: np.ndarray, axis: int,
               warnings: list[str]) -> None:
    other = tuple(i for i in range(arr.ndim) if i != axis)
    interior = np.abs(np.diff(arr, axis=axis)).mean(axis=other)
    first = np.take(arr, 0, axis=axis)
    last = np.take(arr, -1, axis=axis)
    seam = float(np.abs(first - last).mean())
    ceiling = max(1.5 * float(np.percentile(interior, 99)),
                  _SEAM_TOLERANCE)
    if seam > ceiling:
        warnings.append(f"{name}: {label} seam discontinuity {seam:.4f} "
                        f"exceeds interior p99 ceiling {ceiling:.4f}")


def _pack_manifest(recipe: Recipe, g, preset, map_files: dict,
                   sha: str) -> dict:
    """pixelcoat-pack/2: additive over pack/1 — downstream tools that only
    know pack/1 keep reading maps/tileable/meters_per_tile the same way."""
    color_space_hints = {
        name: ("srgb" if name in ("albedo", "wet_albedo") else "linear")
        for name in map_files}
    pack = {
        "schema": "pixelcoat-pack/2",
        "tool_version": __version__,
        "asset_id": recipe.asset_id,
        "processing_mode": "generation_7",
        "material_profile": preset.name,
        "material_workflow": g.material.workflow,
        "maps": map_files,
        "tileable": recipe.tiling.axes if recipe.tiling.enabled else None,
        "meters_per_tile": recipe.export.meters_per_tile,
        "source_sha256": sha,
        "import_hints": {
            "color_space": color_space_hints,
            "normal_format": "directx" if g.normal.flip_green else "opengl",
            "generate_mipmaps": True,
            "roughness_source_normal": map_files.get("normal"),
            "albedo_compression": "color_block",
            "normal_compression": "two_channel",
            "mask_compression": "single_channel",
        },
    }
    if g.variations:
        pack["variants"] = sorted(g.variations)
    if g.detail_texture.enabled:
        dt = g.detail_texture
        pack["detail"] = {
            "repeats_per_meter": dt.repeats_per_meter,
            "blend_mode": dt.blend_mode,
            "strength": dt.strength,
            "tile_size": dt.size,
            "uv": "uv1_scaled_or_triplanar",
            "distance_fade_meters": [4.0, 12.0],
        }
        pack["import_hints"]["wet_detail_strength_scale"] = 0.3
    return pack
