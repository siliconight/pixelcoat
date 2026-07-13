"""Pixel pipeline: the original fixed processing graph (TDD §10.2), pack
export (TDD §8), and build report (§19). Moved here verbatim from
pipeline.py when processing modes arrived in v0.3 — NO output change is
intended or permitted by this move; pixel packs stay byte-identical.

Load -> Transform -> Downsample -> Simplify -> Tile -> Quantize+Dither ->
Upscale -> Pad -> Export. Node caching arrives with the GUI; offline builds
just run straight through.
"""

from __future__ import annotations

import json
import os
import time

import numpy as np

from ..recipe import Recipe
from ..version import __version__
from . import (dithering, image_io, maps, quantization, simplification,
               tiling, transforms)


def build_pixel(recipe: Recipe, out_dir: str) -> dict:
    """Run a recipe. Writes the pack into ``out_dir/<asset_id>/`` and
    returns the build report dict."""
    t0 = time.perf_counter()
    src, sha = image_io.load(recipe.source_path)

    target = (recipe.pixel.working_width, recipe.pixel.working_height)
    arr = transforms.apply(src, recipe.transform.crop,
                           recipe.transform.perspective_quad,
                           recipe.transform.rotation_degrees, target)
    arr = transforms.downsample(arr, target, recipe.pixel.downsample_method)

    alpha = arr[..., 3:4]
    rgb = arr[..., :3]

    if recipe.simplification.noise_reduction > 0:
        rgb = simplification.noise_reduce(
            np.concatenate([rgb, alpha], axis=-1),
            recipe.simplification.noise_reduction)[..., :3]
    if recipe.simplification.value_bands >= 2:
        rgb = simplification.value_band(
            np.concatenate([rgb, alpha], axis=-1),
            recipe.simplification.value_bands)[..., :3]

    if recipe.tiling.enabled:
        rgb = tiling.make_tileable(rgb, recipe.tiling.axes)

    if recipe.palette.method == "fixed":
        palette = quantization.load_fixed(recipe.palette.locked_palette)
    else:
        opaque = rgb[alpha[..., 0] > 0.01] if (alpha < 1.0).any() else rgb
        palette = quantization.extract_palette(
            opaque, recipe.palette.max_colors, recipe.palette.seed)

    rgb = dithering.apply(rgb, palette, recipe.dither.method,
                          recipe.dither.strength).astype(np.float32)

    # Material maps (TDD §7.13) are derived at working resolution from the
    # post-dither albedo so they stay pixel-aligned through upscale + pad.
    wrap_x = recipe.tiling.enabled and recipe.tiling.axes in ("x", "both")
    wrap_y = recipe.tiling.enabled and recipe.tiling.axes in ("y", "both")
    extra: dict[str, np.ndarray] = {}
    m = recipe.maps
    if m.normal or m.roughness or m.height:
        h = maps.height_from_albedo(rgb, m.height_smooth, wrap_x, wrap_y)
        if m.normal:
            extra["normal"] = maps.normal_from_height(
                h, m.normal_strength, wrap_x, wrap_y, m.normal_flip_g)
        if m.roughness:
            extra["roughness"] = maps.to_rgb(maps.roughness_from_height(
                h, m.roughness_base, m.roughness_variation,
                m.roughness_levels, m.roughness_invert))
        if m.height:
            extra["height"] = maps.to_rgb(h)
    if m.emissive_mode == "indices":
        extra["emissive"] = maps.emissive_indices(rgb, palette,
                                                  m.emissive_indices)
    elif m.emissive_mode == "threshold":
        extra["emissive"] = maps.emissive_threshold(rgb, m.emissive_threshold)

    out = np.concatenate([rgb, alpha], axis=-1)

    def _finish(arr: np.ndarray) -> np.ndarray:
        if recipe.export.nearest_neighbor_upscale and recipe.pixel.display_scale > 1:
            s = recipe.pixel.display_scale
            arr = arr.repeat(s, axis=0).repeat(s, axis=1)
        if recipe.export.padding > 0:
            arr = _pad_extrude(arr, recipe.export.padding)
        return arr

    out = _finish(out)

    asset_dir = os.path.join(out_dir, recipe.asset_id)
    os.makedirs(asset_dir, exist_ok=True)
    albedo = os.path.join(asset_dir, f"{recipe.asset_id}_albedo.png")
    image_io.save_png(out, albedo)
    map_files = {"albedo": os.path.basename(albedo)}
    for name, arr in extra.items():
        p = os.path.join(asset_dir, f"{recipe.asset_id}_{name}.png")
        image_io.save_png(_finish(arr), p)
        map_files[name] = os.path.basename(p)
    recipe.save(os.path.join(asset_dir, f"{recipe.asset_id}.pixelcoat.json"))

    # Pack manifest: the cross-tool contract consumers (Zoo, Patina, the
    # Godot importer) read instead of guessing filenames.
    pack = {
        "schema": "pixelcoat-pack/1",
        "tool_version": __version__,
        "asset_id": recipe.asset_id,
        "processing_mode": "pixel",              # additive in 0.3
        "maps": map_files,
        "tileable": recipe.tiling.axes if recipe.tiling.enabled else None,
        "meters_per_tile": recipe.export.meters_per_tile,
        "source_sha256": sha,
    }
    pack_path = os.path.join(asset_dir, f"{recipe.asset_id}.pack.json")
    with open(pack_path, "w", encoding="utf-8") as f:
        json.dump(pack, f, indent=2, sort_keys=True)

    report = {
        "tool_version": __version__,
        "asset_id": recipe.asset_id,
        "processing_mode": "pixel",
        "source_sha256": sha,
        "working_resolution": list(target),
        "output_resolution": [out.shape[1], out.shape[0]],
        "final_color_count": int(len(np.unique(
            (rgb.reshape(-1, 3) * 255).astype(np.uint8), axis=0))),
        "palette_size": int(len(palette)),
        "duration_seconds": round(time.perf_counter() - t0, 4),
        "maps": sorted(map_files),
        "files": sorted(map_files.values()) + [
            f"{recipe.asset_id}.pack.json"],
    }
    with open(os.path.join(asset_dir, "build_report.json"), "w",
              encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    return report


def _pad_extrude(arr: np.ndarray, pad: int) -> np.ndarray:
    """Border extrusion padding (TDD §7.11): edge pixels repeat outward so
    mipmaps and atlas packing don't bleed."""
    return np.pad(arr, ((pad, pad), (pad, pad), (0, 0)), mode="edge")
