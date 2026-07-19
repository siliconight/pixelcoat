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

    bt = sub.add_parser("batch", help="process a folder with one style "
                                      "template (TDD 6.2)")
    bt.add_argument("input", help="folder of images")
    bt.add_argument("--recipe", default=None,
                    help="style template recipe JSON applied to every "
                         "file (asset_id/source injected per file)")
    bt.add_argument("--map", action="append", default=[],
                    metavar="PATTERN=RECIPE",
                    help="filename-pattern preset, e.g. "
                         "'poster_*=recipes/poster.json'; first match "
                         "wins, --recipe is the fallback")
    bt.add_argument("--recursive", action="store_true")
    bt.add_argument("--output", default="./build")
    bt.add_argument("--atlas", default=None,
                    help="also atlas the compatible outputs")
    bt.add_argument("--gutter", type=int, default=2)
    bt.add_argument("--pow2", action="store_true")
    bt.add_argument("--json", action="store_true", dest="json_log")

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

    pp = sub.add_parser("proc-pack",
                        help="synthesize a source-free procedural material "
                             "pack from a grammar (T03)")
    pp.add_argument("grammar", help="material grammar JSON "
                                    "(see profiles/materials/)")
    pp.add_argument("--out", default="./build",
                    help="pack directory to write into")
    pp.add_argument("--asset-id", default=None)
    pp.add_argument("--size", type=int, default=512,
                    help="square texture size in px")
    pp.add_argument("--seed", type=int, default=1999)
    pp.add_argument("--force", action="store_true",
                    help="overwrite an existing pack in --out")
    pp.add_argument("--json", action="store_true", dest="json_log")

    sl = sub.add_parser("skins-library",
                        help="build a Zoo --skins library: one "
                             "<kind>_<theme>/ pack per grammar (T03)")
    sl.add_argument("grammars", nargs="+",
                    help="grammar JSON files, or dirs to scan for *.json")
    sl.add_argument("--out", default="./skins", help="skins library root")
    sl.add_argument("--theme", default="delco")
    sl.add_argument("--size", type=int, default=512)
    sl.add_argument("--seed", type=int, default=1999)
    sl.add_argument("--force", action="store_true")
    sl.add_argument("--json", action="store_true", dest="json_log")

    tl = sub.add_parser("theme-library",
                        help="build a Zoo --skins library from a THEME PROFILE "
                             "(profiles/themes/<theme>.json): the reproducible "
                             "one-grammar-per-kind curation a building wears")
    tl.add_argument("--theme", required=True,
                    help="theme name; resolves profiles/themes/<theme>.json")
    tl.add_argument("--profile", default=None,
                    help="explicit theme profile JSON (overrides --theme lookup)")
    tl.add_argument("--grammars", default=None,
                    help="grammar dir (default: the shipped profiles/materials)")
    tl.add_argument("--out", default="./skins", help="skins library root")
    tl.add_argument("--size", type=int, default=512)
    tl.add_argument("--seed", type=int, default=1999)
    tl.add_argument("--json", action="store_true", dest="json_log")

    ln = sub.add_parser("signal-lenses",
                        help="generate the red/yellow/green traffic-signal "
                             "lens packs (lit + off) as emissive decals")
    ln.add_argument("--out", default="./build/signal_lenses")
    ln.add_argument("--size", type=int, default=128)
    ln.add_argument("--force", action="store_true")
    ln.add_argument("--json", action="store_true", dest="json_log")

    sg = sub.add_parser("sign",
                        help="generate an emissive signage/screen/label decal "
                             "(neon, panel, screen, hazard, arrow)")
    sg.add_argument("--type", required=True,
                    choices=["neon", "panel", "screen", "hazard", "arrow"])
    sg.add_argument("--text", default=None, help="sign text (neon/panel)")
    sg.add_argument("--mode", default="bars",
                    choices=["bars", "static", "terminal", "off"],
                    help="screen content")
    sg.add_argument("--direction", default="right",
                    choices=["left", "right", "up", "down"])
    sg.add_argument("--color", default=None, help="primary hex colour")
    sg.add_argument("--panel", default=None, help="panel hex (panel type)")
    sg.add_argument("--text-color", default=None, dest="text_color")
    sg.add_argument("--border", default=None)
    sg.add_argument("--unpowered", action="store_true",
                    help="author the dark, unpowered variant")
    sg.add_argument("--size", type=int, default=128)
    sg.add_argument("--seed", type=int, default=1999)
    sg.add_argument("--asset-id", default=None)
    sg.add_argument("--out", default="./build/signage")
    sg.add_argument("--force", action="store_true")
    sg.add_argument("--json", action="store_true", dest="json_log")

    args = p.parse_args(argv)
    try:
        if args.cmd == "process":
            return _process(args)
        if args.cmd == "build":
            return _build_from(args)
        if args.cmd == "preview-compression":
            return _preview_compression(args)
        if args.cmd == "proc-pack":
            return _proc_pack(args)
        if args.cmd == "skins-library":
            return _skins_library(args)
        if args.cmd == "theme-library":
            return _theme_library(args)
        if args.cmd == "signal-lenses":
            return _signal_lenses(args)
        if args.cmd == "sign":
            return _sign(args)
        if args.cmd == "atlas":
            return _atlas(args)
        if args.cmd == "batch":
            return _batch(args)
        return _validate(args)
    except (ValueError, OSError) as e:
        print(f"pixelcoat: error: {e}", file=sys.stderr)
        return 1


def _batch(args) -> int:
    import json as _json

    from ..core import batch as batch_mod

    template = None
    if args.recipe:
        with open(args.recipe, encoding="utf-8") as f:
            template = _json.load(f)
    pattern_map = []
    for spec in args.map:
        pattern, _, rpath = spec.partition("=")
        if not rpath:
            raise ValueError(f"--map '{spec}' is not PATTERN=RECIPE")
        with open(rpath, encoding="utf-8") as f:
            pattern_map.append((pattern, _json.load(f)))

    report = batch_mod.run_batch(
        os.path.abspath(args.input), os.path.abspath(args.output),
        template=template, pattern_map=pattern_map,
        recursive=args.recursive, atlas_name=args.atlas,
        gutter=args.gutter, pow2=args.pow2)
    if args.json_log:
        print(_json.dumps(report, indent=2))
    else:
        print(f"[batch] {report['processed']} processed, "
              f"{report['failed']} failed "
              f"({report['duration_seconds']}s)")
        for f_ in report["failures"]:
            print(f"  FAILED {f_['file']}: {f_['error']}",
                  file=sys.stderr)
        if "atlas" in report:
            a = report["atlas"]
            print(f"[atlas] {a['atlas']}: {a['entries']} entries -> "
                  f"{a['size'][0]}x{a['size'][1]}")
    return 1 if report["failed"] and not report["processed"] else 0


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


# Keep in sync with Zoo zoo_keeper/core/skins.py KNOWN_KINDS. A grammar whose
# kind is outside this set produces a valid pack that Zoo's find_pack (exact
# kind match) will never resolve unless a species explicitly requests it.
_ZOO_KINDS = ("laminate", "wood", "metal", "plastic", "leather", "rubber",
              "canvas", "carbon", "glass", "paper", "concrete", "plaster",
              "brick", "tile", "drywall", "ceiling_tile", "carpet", "dirt")


def _warn_unknown_kind(kind: str) -> None:
    if kind not in _ZOO_KINDS:
        print(f"pixelcoat: warning: material kind '{kind}' is not in Zoo's "
              f"known vocabulary; Zoo resolves packs by exact kind, so this "
              f"one won't be picked up unless a species requests '{kind}'.",
              file=sys.stderr)


def _proc_pack(args) -> int:
    from ..core import material_grammar as mg

    pack_dir = os.path.abspath(args.out)
    if glob.glob(os.path.join(pack_dir, "*.pack.json")) and not args.force:
        raise ValueError(f"{pack_dir} already contains a pack "
                         f"(use --force to overwrite)")
    manifest = mg.build_material_pack(
        os.path.abspath(args.grammar), pack_dir,
        asset_id=args.asset_id, size=args.size, seed=args.seed)
    if args.json_log:
        print(json.dumps(manifest, indent=2, sort_keys=True))
    else:
        print(f"pixelcoat: {manifest['asset_id']} "
              f"[procedural/{manifest['material_kind']}] -> "
              f"{sorted(manifest['maps'])}, "
              f"mpt={manifest['meters_per_tile']} -> {pack_dir}")
        _warn_unknown_kind(manifest["material_kind"])
    return 0


def _skins_library(args) -> int:
    from ..core import material_grammar as mg

    files: list[str] = []
    for g in args.grammars:
        if os.path.isdir(g):
            files.extend(sorted(glob.glob(os.path.join(g, "*.json"))))
        else:
            files.append(g)
    if not files:
        raise ValueError("no grammar JSON files found")

    root = os.path.abspath(args.out)
    resolved: dict[str, dict] = {}
    seen: dict[str, str] = {}
    created: set[str] = set()          # pack dirs written in THIS run
    for path in files:
        gram = mg.MaterialGrammar.load(path)
        pack_dir = os.path.join(root, f"{gram.kind}_{args.theme}")
        if gram.kind in seen:
            print(f"pixelcoat: warning: kind '{gram.kind}' from "
                  f"{os.path.basename(path)} overwrites {seen[gram.kind]} "
                  f"(Zoo resolves one pack per kind+theme; last wins)",
                  file=sys.stderr)
        # Refuse to clobber a pre-existing on-disk library, but a same-run
        # kind collision (warned above) is allowed to overwrite.
        pre_existing = (pack_dir not in created
                        and glob.glob(os.path.join(pack_dir, "*.pack.json")))
        if pre_existing and not args.force:
            raise ValueError(f"{pack_dir} already contains a pack "
                             f"(use --force to overwrite)")
        manifest = mg.build_material_pack(gram, pack_dir, asset_id=gram.id,
                                          size=args.size, seed=args.seed)
        created.add(pack_dir)
        seen[gram.kind] = os.path.basename(path)
        resolved[gram.kind] = {
            "pack": manifest["asset_id"], "dir": pack_dir,
            "maps": sorted(manifest["maps"]),
            "meters_per_tile": manifest["meters_per_tile"]}
        _warn_unknown_kind(gram.kind)

    report = {"skins_dir": root, "theme": args.theme, "resolved": resolved}
    if args.json_log:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"pixelcoat: skins library -> {root} "
              f"(theme={args.theme}, {len(resolved)} kinds)")
        for kind, info in sorted(resolved.items()):
            print(f"  {kind:<10} {info['pack']:<26} {info['maps']} "
                  f"mpt={info['meters_per_tile']}")
    return 0


def _sign(args) -> int:
    from ..core import signage as sgn

    powered = not args.unpowered
    t = args.type
    if t == "neon":
        text = args.text or "OPEN"
        arrays = sgn.neon_sign(text, args.size, color=args.color or "#ff2a6d",
                               powered=powered)
        aid = args.asset_id or f"sign_neon_{_slug(text)}"
    elif t == "panel":
        text = args.text or "EXIT"
        arrays = sgn.panel_sign(text, args.size, panel=args.panel or "#12351f",
                                text_color=args.text_color or "#4dff8a",
                                border=args.border, powered=powered)
        aid = args.asset_id or f"sign_panel_{_slug(text)}"
    elif t == "screen":
        arrays = sgn.screen(args.mode, args.size, seed=args.seed, powered=powered)
        aid = args.asset_id or f"screen_{args.mode}"
    elif t == "hazard":
        arrays = sgn.hazard_stripes(args.size, powered=powered)
        aid = args.asset_id or "hazard_stripes"
    else:  # arrow
        arrays = sgn.arrow(args.size, direction=args.direction,
                           color=args.color or "#f5f5f5", powered=powered)
        aid = args.asset_id or f"arrow_{args.direction}"
    if not powered:
        aid += "_off"

    pack_dir = os.path.join(os.path.abspath(args.out), aid)
    if glob.glob(os.path.join(pack_dir, "*.pack.json")) and not args.force:
        raise ValueError(f"{pack_dir} already contains a pack "
                         f"(use --force to overwrite)")
    manifest = sgn.build_sign_pack(pack_dir, arrays, aid)
    if args.json_log:
        print(json.dumps(manifest, indent=2, sort_keys=True))
    else:
        print(f"pixelcoat: {aid} [{t}] -> {sorted(manifest['maps'])} -> {pack_dir}")
    return 0


def _theme_library(args) -> int:
    """Build a Zoo --skins library from a theme profile — the reproducible
    curation the Level Factory art pass calls before running Zoo."""
    from ..core import material_grammar as mg
    pkg = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # pixelcoat/
    profiles = os.path.normpath(os.path.join(pkg, "..", "profiles"))
    profile = args.profile or os.path.join(profiles, "themes", f"{args.theme}.json")
    if not os.path.isfile(profile):
        raise ValueError(f"no theme profile for '{args.theme}' at {profile}")
    grammars = args.grammars or os.path.join(profiles, "materials")
    res = mg.build_theme_library(profile, grammars, os.path.abspath(args.out),
                                 size=args.size, seed=args.seed)
    if getattr(args, "json_log", False):
        print(json.dumps(res, indent=2))
    else:
        print(f"pixelcoat: theme '{res['theme']}' -> {res['kind_count']} packs "
              f"in {res['out_dir']}")
        for kind, name in sorted(res["packs"].items()):
            print(f"  {kind:14s} -> {name}/")
    return 0


def _slug(s: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in s.lower()).strip("_") or "sign"


def _signal_lenses(args) -> int:
    from ..core import decals

    root = os.path.abspath(args.out)
    built: list[dict] = []
    for color in ("red", "yellow", "green"):
        for state in ("lit", "off"):
            pack_dir = os.path.join(root, f"lens_{color}_{state}")
            if glob.glob(os.path.join(pack_dir, "*.pack.json")) and not args.force:
                raise ValueError(f"{pack_dir} already contains a pack "
                                 f"(use --force to overwrite)")
            built.append(decals.build_lens_pack(pack_dir, color=color,
                                                state=state, size=args.size))
    if args.json_log:
        print(json.dumps({"out": root, "packs": [m["asset_id"] for m in built]},
                         indent=2))
    else:
        print(f"pixelcoat: {len(built)} lens packs -> {root}")
        for m in built:
            print(f"  {m['asset_id']:<24} {sorted(m['maps'])}")
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
