"""Pixelcoat CLI (TDD §14): process, build, validate.

argparse for v0.1 — Click/Typer is a dependency the scaffold doesn't need
yet. Non-zero exit on failure, ``--json`` machine-readable logs,
overwrite protection, deterministic by construction.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys

from ..recipe import Recipe
from ..core import pipeline
from ..version import __version__


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="pixelcoat",
                                description="Controlled pixel-art surface "
                                            "treatments for 3D worlds.")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("process", help="process a source image directly")
    pr.add_argument("input")
    pr.add_argument("--asset-id", default=None)
    pr.add_argument("--mode", default="pixel",
                    choices=["pixel", "generation_7"])
    pr.add_argument("--profile", default=None,
                    help="generation_7 profile JSON (a generation_7 "
                         "recipe-section fragment, e.g. "
                         "profiles/generation_7/concrete.json)")
    pr.add_argument("--meters-per-tile", type=float, default=None)
    pr.add_argument("--width", type=int, default=None,
                    help="working width (default: 128 pixel / 1024 gen7)")
    pr.add_argument("--height", type=int, default=None,
                    help="working height (default: 128 pixel / 1024 gen7)")
    pr.add_argument("--colors", type=int, default=24)
    pr.add_argument("--dither", default="none",
                    choices=["none", "bayer", "floyd_steinberg"])
    pr.add_argument("--dither-strength", type=float, default=0.5)
    pr.add_argument("--palette", default=None,
                    help="fixed palette JSON (hex list)")
    pr.add_argument("--value-bands", type=int, default=0)
    pr.add_argument("--downsample", default="box",
                    choices=["box", "nearest", "edge_aware"])
    pr.add_argument("--edge-preserve", type=float, default=0.5)
    pr.add_argument("--island-removal", type=int, default=0,
                    help="dissolve palette islands of <= N pixels")
    pr.add_argument("--protected-mask", default=None,
                    help="grayscale mask; >50%% keeps source detail")
    pr.add_argument("--alpha", default="none",
                    choices=["none", "source", "color_key", "luminance",
                             "mask", "flood"],
                    help="alpha extraction source (TDD 7.11)")
    pr.add_argument("--alpha-key", default="#ff00ff",
                    help="color_key hex, e.g. '#00ff00'")
    pr.add_argument("--alpha-tolerance", type=float, default=None,
                    help="color_key / flood tolerance 0..1")
    pr.add_argument("--alpha-threshold", type=float, default=0.5,
                    help="luminance threshold 0..1")
    pr.add_argument("--alpha-invert", action="store_true")
    pr.add_argument("--alpha-mask", default=None,
                    help="grayscale alpha mask path")
    pr.add_argument("--alpha-feather", type=float, default=0.0,
                    help="source-space feather radius, px")
    pr.add_argument("--alpha-dilate", type=int, default=0)
    pr.add_argument("--decal", action="store_true",
                    help="decal export: <asset>_decal.png, transparent "
                         "padding")
    pr.add_argument("--tile", default=None, choices=["x", "y", "both"])
    pr.add_argument("--scale", type=int, default=1,
                    help="nearest-neighbor display scale")
    pr.add_argument("--seed", type=int, default=1999)
    pr.add_argument("--output", default="./build")
    pr.add_argument("--force", action="store_true",
                    help="overwrite an existing asset directory")
    pr.add_argument("--json", action="store_true", dest="json_log")

    bd = sub.add_parser("build", help="build from a saved recipe")
    bd.add_argument("recipe")
    bd.add_argument("--output", default="./build")
    bd.add_argument("--force", action="store_true")
    bd.add_argument("--json", action="store_true", dest="json_log")

    va = sub.add_parser("validate", help="validate recipe file(s) or a dir")
    va.add_argument("paths", nargs="+")

    at = sub.add_parser("atlas", help="pack pixelcoat packs into one "
                                      "atlas + UV manifest (TDD 7.15)")
    at.add_argument("packs", nargs="+",
                    help=".pack.json files, or directories to scan")
    at.add_argument("--name", required=True, help="atlas name")
    at.add_argument("--output", default="./build")
    at.add_argument("--gutter", type=int, default=2)
    at.add_argument("--pow2", action="store_true",
                    help="round atlas dimensions up to powers of two")
    at.add_argument("--no-rotate", action="store_true",
                    help="disable 90-degree rotation")
    at.add_argument("--json", action="store_true", dest="json_log")

    pc = sub.add_parser("preview-compression",
                        help="write legacy block-compression previews for "
                             "an existing pack (never alters the pack)")
    pc.add_argument("pack", help="path to a <asset>.pack.json")
    pc.add_argument("--profile", default="legacy_bc",
                    choices=["legacy_bc"])
    pc.add_argument("--output", default=None,
                    help="preview dir (default: <pack dir>/previews/"
                         "compression)")

    args = p.parse_args(argv)
    try:
        if args.cmd == "process":
            return _process(args)
        if args.cmd == "build":
            return _build_from(args)
        if args.cmd == "preview-compression":
            return _preview_compression(args)
        if args.cmd == "atlas":
            return _atlas(args)
        return _validate(args)
    except (ValueError, OSError) as e:
        print(f"pixelcoat: error: {e}", file=sys.stderr)
        return 1


def _atlas(args) -> int:
    import glob as _glob
    import json as _json

    from ..core import atlas as atlas_mod

    packs: list[str] = []
    for p in args.packs:
        if os.path.isdir(p):
            packs.extend(_glob.glob(os.path.join(p, "**", "*.pack.json"),
                                    recursive=True))
        else:
            packs.append(p)
    if not packs:
        raise ValueError("no .pack.json files found")
    report = atlas_mod.build_atlas(
        [os.path.abspath(p) for p in sorted(set(packs))],
        args.name, os.path.abspath(args.output),
        gutter=args.gutter, pow2=args.pow2,
        allow_rotate=not args.no_rotate)
    if args.json_log:
        print(_json.dumps(report, indent=2))
    else:
        print(f"[atlas] {report['atlas']}: {report['entries']} entries "
              f"-> {report['size'][0]}x{report['size'][1]} "
              f"({report['occupancy']:.0%} occupancy, "
              f"{len(report['maps'])} maps)")
    return 0


def _preview_compression(args) -> int:
    """Roadmap §19 CLI: previews from an existing pack's canonical PNGs.
    Reads only; writes only under the preview directory."""
    import json as _json

    import numpy as np
    from PIL import Image

    from ..core import preview as pv

    pack_path = os.path.abspath(args.pack)
    with open(pack_path, encoding="utf-8") as f:
        pack = _json.load(f)
    pack_dir = os.path.dirname(pack_path)
    out_dir = os.path.abspath(args.output) if args.output else \
        os.path.join(pack_dir, "previews", "compression")
    os.makedirs(out_dir, exist_ok=True)

    for name, fname in sorted(pack.get("maps", {}).items()):
        arr = np.asarray(Image.open(os.path.join(pack_dir, fname))
                         .convert("RGBA"), np.float32) / 255.0
        fam = pv.suggest_family(
            name, has_varying_alpha=float(arr[..., 3].std()) > 1e-4)
        bc = pv.preview_block_compression(arr, fam)
        stem = os.path.splitext(fname)[0]
        out = os.path.join(out_dir, f"{stem}_bc.png")
        Image.fromarray(
            (np.clip(bc, 0, 1) * 255).astype(np.uint8)).save(out)
        err = float(np.abs(bc[..., :3] - arr[..., :3]).mean())
        print(f"  {name:<20} {fam:<15} mean_abs_error {err:.5f}")
    print(f"previews -> {out_dir}")
    return 0


def _process(args) -> int:
    asset_id = args.asset_id or \
        os.path.splitext(os.path.basename(args.input))[0]
    r = Recipe(asset_id=asset_id, source_path=os.path.abspath(args.input))
    r.processing_mode = args.mode
    if args.mode == "generation_7":
        return _process_generation_7(r, args)
    if args.profile:
        raise ValueError("--profile is a generation_7 option "
                         "(use --mode generation_7)")
    r.pixel.working_width = args.width if args.width else 128
    r.pixel.working_height = args.height if args.height else 128
    r.pixel.display_scale = args.scale
    r.palette.max_colors = args.colors
    r.palette.seed = args.seed
    if args.palette:
        r.palette.method = "fixed"
        r.palette.locked_palette = os.path.abspath(args.palette)
    r.dither.method = args.dither
    r.dither.strength = args.dither_strength
    r.dither.seed = args.seed
    r.simplification.value_bands = args.value_bands
    r.pixel.downsample_method = args.downsample
    r.pixel.edge_preserve = args.edge_preserve
    r.simplification.island_removal = args.island_removal
    if args.protected_mask:
        r.simplification.protected_mask = os.path.abspath(
            args.protected_mask)
    r.alpha.source = args.alpha
    r.alpha.color_key = args.alpha_key
    if args.alpha_tolerance is not None:
        r.alpha.tolerance = args.alpha_tolerance
        r.alpha.flood_tolerance = args.alpha_tolerance
    r.alpha.luminance_threshold = args.alpha_threshold
    r.alpha.invert = args.alpha_invert
    if args.alpha_mask:
        r.alpha.mask_path = os.path.abspath(args.alpha_mask)
    r.alpha.feather = args.alpha_feather
    r.alpha.dilate = args.alpha_dilate
    if args.decal:
        r.export.type = "decal"
    if args.tile:
        r.tiling.enabled = True
        r.tiling.axes = args.tile
    r.validate()
    return _run(r, args)


def _process_generation_7(r: Recipe, args) -> int:
    g = r.generation_7
    if args.profile:
        with open(args.profile, encoding="utf-8") as f:
            g.fill(json.load(f))
    if args.width:
        g.resolution.working_width = args.width
    if args.height:
        g.resolution.working_height = args.height
    if args.tile:
        r.tiling.enabled = True
        r.tiling.axes = args.tile
    if args.meters_per_tile:
        r.export.meters_per_tile = args.meters_per_tile
    g.weathering.seed = args.seed
    r.validate()
    return _run(r, args)


def _build_from(args) -> int:
    return _run(Recipe.load(args.recipe), args)


def _run(recipe: Recipe, args) -> int:
    asset_dir = os.path.join(args.output, recipe.asset_id)
    if os.path.exists(asset_dir) and not args.force:
        raise ValueError(f"{asset_dir} exists (use --force to overwrite)")
    report = pipeline.build(recipe, args.output)
    if args.json_log:
        print(json.dumps(report))
    elif report["processing_mode"] == "generation_7":
        print(f"pixelcoat: {report['asset_id']} [generation_7/"
              f"{report['material_profile']}] -> "
              f"{report['output_resolution'][0]}x"
              f"{report['output_resolution'][1]}, "
              f"{len(report['maps'])} maps, "
              f"{report['duration_seconds']}s")
        for w in report.get("warnings", []):
            print(f"pixelcoat: warning: {w}", file=sys.stderr)
    else:
        print(f"pixelcoat: {report['asset_id']} -> "
              f"{report['output_resolution'][0]}x"
              f"{report['output_resolution'][1]}, "
              f"{report['final_color_count']} colors, "
              f"{report['duration_seconds']}s")
    return 0


def _validate(args) -> int:
    paths: list[str] = []
    for raw in args.paths:
        if os.path.isdir(raw):
            paths += sorted(glob.glob(os.path.join(raw, "*.json")))
        else:
            paths.append(raw)
    failures = 0
    for path in paths:
        try:
            Recipe.load(path)
            print(f"ok      {path}")
        except (ValueError, OSError, json.JSONDecodeError) as e:
            failures += 1
            print(f"INVALID {path}: {e}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
