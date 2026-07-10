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
    pr.add_argument("--width", type=int, default=128)
    pr.add_argument("--height", type=int, default=128)
    pr.add_argument("--colors", type=int, default=24)
    pr.add_argument("--dither", default="none",
                    choices=["none", "bayer", "floyd_steinberg"])
    pr.add_argument("--dither-strength", type=float, default=0.5)
    pr.add_argument("--palette", default=None,
                    help="fixed palette JSON (hex list)")
    pr.add_argument("--value-bands", type=int, default=0)
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

    args = p.parse_args(argv)
    try:
        if args.cmd == "process":
            return _process(args)
        if args.cmd == "build":
            return _build_from(args)
        return _validate(args)
    except (ValueError, OSError) as e:
        print(f"pixelcoat: error: {e}", file=sys.stderr)
        return 1


def _process(args) -> int:
    asset_id = args.asset_id or \
        os.path.splitext(os.path.basename(args.input))[0]
    r = Recipe(asset_id=asset_id, source_path=os.path.abspath(args.input))
    r.pixel.working_width = args.width
    r.pixel.working_height = args.height
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
    if args.tile:
        r.tiling.enabled = True
        r.tiling.axes = args.tile
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
