r"""Mint a material profile, or list the kinds a theme cannot dress (roadmap 150).

    python tools/new_material.py report [--theme delco_1997]
    python tools/new_material.py new <profile_id> --kind <kind>
        [--like metal_rusted_street] [--colors "#6b4a35,#7a5539,#875f3c"]
        [--meters-per-tile 2.0] [--theme delco_1997] [--replace]
        [--profiles-dir DIR --themes-dir DIR]

WHY THIS EXISTS. A minted prop (zoo/tools/new_species.py) wears a material
KIND, and a kind the theme has no profile for renders flat -- Zoo's
`find_pack` says so with `flat_fallback`, and cold run 9003 died on a theme
that named no profile at all. The walker's goal is that a new person can
"mint the necessary props, textures, styles to fulfil the request", and
the texture half of that is this file: `report` says which kinds a theme
cannot dress, `new` writes a grammar from a template, PROVES it renders
(a 64 px synth, with the two numbers item 140 measures a skin by -- the
albedo's luminance spread and its neighbour correlation, so a minted
static is caught before anyone walks it), maps the kind into the theme so
`theme-library` builds it, and refuses to overwrite.

WHAT IT DOES NOT DO. It does not draw the surface: a grammar copied from a
template with new colours is the template's surface in new colours, which
is the honest state of a material nobody has authored. The grammar file is
where the authoring goes (`profiles/materials/*.json`, every knob named in
`core/material_grammar.MaterialGrammar`). And a kind Zoo does not know
(`zoo_keeper/core/skins.KNOWN_KINDS`, `bpylayer/materials.ROUGHNESS` /
`METALLIC`) needs those three tables before any species can wear it; the
tool says so rather than editing another repo.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)

from pixelcoat.core import material_grammar as mg  # noqa: E402

PROFILES = os.path.join(REPO, "profiles", "materials")
THEMES = os.path.join(REPO, "profiles", "themes")
ZOO_SKINS = os.path.join(os.path.dirname(REPO), "zoo", "zoo_keeper", "core", "skins.py")

#: The floor a skin must clear to read as a surface rather than static
#: (roadmap 140): neighbour correlation of the albedo's luminance.
AC1_FLOOR = 0.3


def zoo_kinds() -> list[str]:
    """Zoo's kind vocabulary, read off its source when the sibling repo is
    there; else the kinds the shipped grammars declare."""
    if os.path.isfile(ZOO_SKINS):
        src = open(ZOO_SKINS, encoding="utf-8").read()
        start = src.find("KNOWN_KINDS = (")
        end = src.find(")", start)
        if start >= 0 and end > start:
            import re
            return sorted(set(re.findall(r'"([a-z_]+)"', src[start:end])))
    kinds = set()
    for p in glob.glob(os.path.join(PROFILES, "*.json")):
        with open(p, encoding="utf-8") as f:
            kinds.add(json.load(f).get("kind"))
    return sorted(k for k in kinds if k)


def albedo_numbers(g: mg.MaterialGrammar, size: int = 64) -> tuple[float, float]:
    """(std, ac1) of a small synth of the grammar -- item 140's instrument."""
    import numpy as np
    a = mg.synthesize(g, size=size)["albedo"].astype(np.float64)
    lum = 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]
    d = lum - lum.mean()
    var = (d * d).mean()
    if var <= 0:
        return 0.0, 1.0
    ax = (d[:, :-1] * d[:, 1:]).mean() / var
    ay = (d[:-1, :] * d[1:, :]).mean() / var
    return float(lum.std()), float((ax + ay) / 2.0)


def cmd_report(args) -> int:
    themes_dir = os.path.abspath(args.themes_dir)
    kinds = zoo_kinds()
    paths = sorted(glob.glob(os.path.join(themes_dir, "*.json")))
    if args.theme:
        paths = [p for p in paths if os.path.basename(p)[:-5] == args.theme]
    if not paths:
        print(f"no theme profile under {themes_dir}", file=sys.stderr)
        return 2
    print(f"{len(kinds)} kinds Zoo's species can wear")
    for p in paths:
        with open(p, encoding="utf-8") as f:
            t = json.load(f)
        have = set(t.get("materials", {}))
        missing = [k for k in kinds if k not in have]
        name = t.get("theme", os.path.basename(p)[:-5])
        if missing:
            print(f"{name}: {len(missing)} kind(s) with no profile -- a species wearing "
                  f"one renders flat: {', '.join(missing)}")
        else:
            print(f"{name}: every kind has a profile")
    return 0


def cmd_new(args) -> int:
    pid = args.profile_id.strip().lower()
    profiles_dir = os.path.abspath(args.profiles_dir)
    themes_dir = os.path.abspath(args.themes_dir)
    out = os.path.join(profiles_dir, f"{pid}.json")
    if os.path.exists(out):
        print(f"refusing: {out} exists", file=sys.stderr)
        return 2
    like = os.path.join(profiles_dir, f"{args.like}.json")
    if not os.path.isfile(like):
        print(f"no template profile '{args.like}' under {profiles_dir}", file=sys.stderr)
        return 2
    with open(like, encoding="utf-8") as f:
        raw = json.load(f)
    raw["id"] = pid
    raw["kind"] = args.kind
    if args.colors:
        cols = [c.strip() for c in args.colors.split(",") if c.strip()]
        if not all(c.startswith("#") and len(c) == 7 for c in cols):
            print("--colors wants #rrggbb values, comma-separated", file=sys.stderr)
            return 2
        raw["base_colors"] = cols
    if args.meters_per_tile:
        raw["meters_per_tile"] = float(args.meters_per_tile)
    try:
        g = mg.MaterialGrammar.from_dict(raw)
        std, ac1 = albedo_numbers(g)
    except Exception as exc:  # a grammar that does not synthesize is not a material
        print(f"grammar does not synthesize: {exc}", file=sys.stderr)
        return 2
    kinds = zoo_kinds()
    with open(out, "w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2)
        f.write("\n")
    print(f"minted '{pid}' (kind {args.kind}, from {args.like}): {out}")
    print(f"  renders: albedo std {std:.1f}, ac1 {ac1:.2f}"
          + ("" if ac1 >= AC1_FLOOR else
             f"   <- BELOW {AC1_FLOOR}: reads as static (roadmap 140); lower detail_strength"))
    if args.theme:
        tpath = os.path.join(themes_dir, f"{args.theme}.json")
        if not os.path.isfile(tpath):
            print(f"no theme '{args.theme}' under {themes_dir}; not mapped", file=sys.stderr)
            return 2
        with open(tpath, encoding="utf-8") as f:
            t = json.load(f)
        mats = t.setdefault("materials", {})
        if args.kind in mats and not args.replace:
            print(f"  theme {args.theme} already maps '{args.kind}' -> '{mats[args.kind]}'; "
                  f"pass --replace to take the slot")
        else:
            prev = mats.get(args.kind)
            mats[args.kind] = pid
            t["materials"] = dict(sorted(mats.items()))
            with open(tpath, "w", encoding="utf-8") as f:
                json.dump(t, f, indent=1)
                f.write("\n")
            print(f"  theme {args.theme}: '{args.kind}' -> '{pid}'"
                  + (f" (was '{prev}')" if prev else "")
                  + f"; `theme-library --theme {args.theme}` builds {args.kind}_{args.theme}/")
    else:
        print(f"  not mapped into a theme; pass --theme <name> so `theme-library` builds it")
    if args.kind not in kinds:
        print(f"  '{args.kind}' is NOT a kind Zoo knows. Before a species can wear it, add it to "
              f"zoo_keeper/core/skins.KNOWN_KINDS and bpylayer/materials.ROUGHNESS / METALLIC "
              f"(tests/test_kind_vocabulary.py holds the three in step).")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("report", help="kinds a theme has no profile for")
    r.add_argument("--theme", default=None)
    r.add_argument("--themes-dir", default=THEMES)
    r.set_defaults(func=cmd_report)
    n = sub.add_parser("new", help="mint a material profile from a template")
    n.add_argument("profile_id")
    n.add_argument("--kind", required=True)
    n.add_argument("--like", default="metal_rusted_street")
    n.add_argument("--colors", default=None)
    n.add_argument("--meters-per-tile", type=float, default=None)
    n.add_argument("--theme", default=None)
    n.add_argument("--replace", action="store_true")
    n.add_argument("--profiles-dir", default=PROFILES)
    n.add_argument("--themes-dir", default=THEMES)
    n.set_defaults(func=cmd_new)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
