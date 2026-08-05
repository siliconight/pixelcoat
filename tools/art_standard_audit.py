"""Measure the shipped material library against the Controlled Contrast
Environment Art Standard.

The standard is a set of claims about the ENVIRONMENT layer specifically: it
should be low-chroma, value-compressed, matte, quiet, and almost never
emissive, so that the gameplay layer owns saturation, gloss, peak luminance and
edge density. Every one of those is a property of a synthesized albedo /
roughness map, so every one of them is measurable -- which means the standard
can be enforced instead of remembered.

What is measured, per grammar (synthesized, not read off base_colors -- the
grammar's layers move the result a long way from its stated palette):

  chroma_mean   Oklab C. 0.00 is neutral gray. A saturated sRGB primary sits
                near 0.25-0.31. Standard sect.6: tertiary surfaces are LOW chroma.
  chroma_p95    the hot 5%. A low mean with a high p95 is a quiet field with
                loud speckle -- which reads as noise at gameplay distance.
  value_range   Oklab L p95 - p5. Standard sect.5: background = COMPRESSED value
                range; sect.19: no pure black cavities, no pure white edge wear.
  crushed/blown fraction of pixels below L .06 / above L .94 -- the literal
                sect.19 prohibition.
  hf_energy     std of (L - blur(L)), a proxy for edge density (sect.11) and
                high-frequency detail (sect.10). High hf_energy behind a combat
                position is visual camouflage.
  rough_mean    standard sect.7: environmental materials favour moderate-to-high
                roughness; low roughness is a FOCAL material property.
  emissive      standard sect.8: emissive is a limited resource owned by gameplay.
                Any environmental grammar that emits is spending it.

Thresholds are stated as ENV_BUDGET below. They are read off the standard's
language and then calibrated against the shipped library's own distribution --
they are a proposal, not a measurement, and the report prints the distribution
next to them so the calibration is auditable.

Usage:
    python -m tools.art_standard_audit --materials profiles/materials \\
        --themes profiles/themes [--json out.json] [--size 256]
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import os
import sys

import numpy as np

# --------------------------------------------------------------------------- #
# The budget. Every number here traces to a clause.
# --------------------------------------------------------------------------- #

ENV_BUDGET = {
    # sect.6 "Low Chroma ... large terrain surfaces, broad walls, repeated
    # structural modules". sect.3 "70% environmental base colors" drawn from
    # "neutral gray, cool gray-blue, muted green, desaturated brown, pale
    # stone, weathered metal, dusty beige, dark charcoal".
    #
    # RECALIBRATED 2026-08-05, downward, by looking at the library instead of
    # reading the word list. 0.060 was set from the prose and it passed two
    # materials that are unmistakably COLOURED on sight:
    #   painted_metal_industrial  C 0.051  -> saturated green
    #   metal_painted_trafficsignal C 0.049 -> green
    # while metal_brass_casino at 0.109 reads as screaming yellow. A moderate
    # chroma spread over a LARGE UNIFORM FIELD reads far louder than the same
    # number speckled through a masonry pattern, and chroma_mean cannot tell
    # those apart. The library's own environment-tier distribution puts p50 at
    # 0.023 and p75 at 0.049; everything that reads neutral to the eye sits
    # below ~0.030. That is the number, and it came from the contact sheet.
    "chroma_mean": 0.030,
    # sect.6 again, but for the hot tail: a quiet mean hiding loud speckle still
    # competes. Allowed roughly 2x the mean budget.
    "chroma_p95": 0.120,
    # sect.5 "Background: compressed value range." Oklab L is 0..1, so a full
    # -range surface is 1.00. Half the available range is already generous for
    # a material that is meant to be a stage.
    "value_range": 0.500,
    # sect.19 "Do not use pure black cavities [or] pure white edge wear."
    "crushed_frac": 0.010,
    "blown_frac": 0.010,
    # sect.7 "Favor moderate-to-high roughness"; sect.7 reserves "lower roughness,
    # stronger specular highlights" for focal gameplay materials.
    "rough_mean_min": 0.45,
    # sect.8 "Treat emissive materials as a limited resource" -- the environment
    # tier's share of it is zero.
    "emissive_allowed": False,
}

# sect.18's four module tiers, as a grammar may DECLARE them. A tier is a real
# authoring decision that kind cannot express: glass_facade_mirror_blue is a
# navigation landmark (sect.2 secondary) wearing a kind that is otherwise pure
# background, and subway_tile_white is foundation wearing a kind that also holds
# hero inserts. Until a grammar says, kind is the fallback.
TIER_SCALE = {
    "foundation": 1.00,   # plain walls, floors, ceilings -- judged hardest
    "functional": 1.25,   # doors, stairs, cover, windows
    "identity":   1.75,   # landmark silhouettes, faction motifs
    "accent":     None,   # hero panels, decals, emissive trim -- exempt
}

# sect.2: which kinds are environment-tier at all, when no tier is declared.
TERTIARY_KINDS = {
    "brick", "concrete", "drywall", "plaster", "ceiling_tile",
    "tile", "carpet", "wood", "glass_facade", "metal",
}
# sect.2 secondary: "moderate saturation, controlled accent lighting, localized
# emissive strips or signage". Judged, but on a looser budget.
SECONDARY_KINDS = {"glass"}

SECONDARY_SCALE = 1.75   # secondary may run this much hotter than tertiary


# --------------------------------------------------------------------------- #
# Colour. Oklab, because sRGB HSV saturation lies about perceptual chroma:
# a saturated yellow and a saturated blue are nowhere near equally loud.
# --------------------------------------------------------------------------- #

def _srgb_to_linear(c: np.ndarray) -> np.ndarray:
    c = np.asarray(c, dtype=np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def srgb_to_oklab(rgb_u8: np.ndarray) -> np.ndarray:
    """uint8 HxWx3 sRGB -> float HxWx3 Oklab (L, a, b)."""
    lin = _srgb_to_linear(np.asarray(rgb_u8, dtype=np.float64) / 255.0)
    r, g, b = lin[..., 0], lin[..., 1], lin[..., 2]
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_, m_, s_ = np.cbrt(l), np.cbrt(m), np.cbrt(s)
    return np.stack([
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    ], axis=-1)


def _box_blur(field: np.ndarray, radius: int) -> np.ndarray:
    """Wrap-around box blur. Materials tile, so the blur must tile too --
    a clamped blur would invent an edge at the seam and inflate hf_energy."""
    out = field
    for axis in (0, 1):
        k = 2 * radius + 1
        cum = np.cumsum(np.concatenate(
            [out, out[:k]] if axis == 0 else [out, out[:, :k]], axis=axis),
            axis=axis)
        pad = np.take(cum, range(k, cum.shape[axis]), axis=axis) - \
            np.take(cum, range(0, cum.shape[axis] - k), axis=axis)
        out = np.roll(pad / k, -radius, axis=axis)
    return out


# --------------------------------------------------------------------------- #
# Measurement
# --------------------------------------------------------------------------- #

def measure(grammar, synth) -> dict:
    """Measure one synthesized grammar. `synth` is mg.synthesize's output."""
    lab = srgb_to_oklab(synth["albedo"])
    L = lab[..., 0]
    C = np.sqrt(lab[..., 1] ** 2 + lab[..., 2] ** 2)
    hf = L - _box_blur(L, max(1, L.shape[0] // 64))

    rough = synth.get("roughness")
    rough_mean = (float(np.mean(rough)) / 255.0) if rough is not None else None

    emis = synth.get("emissive")
    emis_frac = None
    if emis is not None:
        e = np.asarray(emis, dtype=np.float64)
        if e.ndim == 3:
            e = e.max(axis=-1)
        emis_frac = float(np.mean(e > 8))    # >3% of full scale counts as lit

    return {
        "id": grammar.id,
        "kind": grammar.kind,
        "tier": getattr(grammar, "tier", None),
        "chroma_mean": float(np.mean(C)),
        "chroma_p95": float(np.percentile(C, 95)),
        "value_p5": float(np.percentile(L, 5)),
        "value_p95": float(np.percentile(L, 95)),
        "value_range": float(np.percentile(L, 95) - np.percentile(L, 5)),
        "crushed_frac": float(np.mean(L < 0.06)),
        "blown_frac": float(np.mean(L > 0.94)),
        "hf_energy": float(np.std(hf)),
        "rough_mean": rough_mean,
        "emissive": emis is not None,
        "emissive_frac": emis_frac,
    }


def judge(row: dict) -> list:
    """Return the standard's complaints about one measured grammar."""
    tier = row.get("tier")
    if tier in TIER_SCALE:
        scale = TIER_SCALE[tier]
        if scale is None:
            return []                          # sect.18 tier 4 -- accents are exempt
    else:
        kind = row["kind"]
        if kind in TERTIARY_KINDS:
            scale = 1.0
        elif kind in SECONDARY_KINDS:
            scale = SECONDARY_SCALE
        else:
            return []                          # not an environment-tier surface

    b = ENV_BUDGET
    faults = []
    if row["chroma_mean"] > b["chroma_mean"] * scale:
        faults.append(f"chroma_mean {row['chroma_mean']:.3f} "
                      f"> {b['chroma_mean'] * scale:.3f} [sect.6]")
    if row["chroma_p95"] > b["chroma_p95"] * scale:
        faults.append(f"chroma_p95 {row['chroma_p95']:.3f} "
                      f"> {b['chroma_p95'] * scale:.3f} [sect.6]")
    if row["value_range"] > b["value_range"]:
        faults.append(f"value_range {row['value_range']:.3f} "
                      f"> {b['value_range']:.3f} [sect.5]")
    if row["crushed_frac"] > b["crushed_frac"]:
        faults.append(f"crushed {row['crushed_frac'] * 100:.1f}% "
                      f"of pixels below L .06 [sect.19]")
    if row["blown_frac"] > b["blown_frac"]:
        faults.append(f"blown {row['blown_frac'] * 100:.1f}% "
                      f"of pixels above L .94 [sect.19]")
    if row["rough_mean"] is not None and row["rough_mean"] < b["rough_mean_min"]:
        faults.append(f"rough_mean {row['rough_mean']:.2f} "
                      f"< {b['rough_mean_min']:.2f} [sect.7]")
    if row["emissive"] and not b["emissive_allowed"]:
        faults.append(f"emissive on an environment surface "
                      f"({(row['emissive_frac'] or 0) * 100:.0f}% lit) [sect.8]")
    return faults


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #

def audit(materials_dir, themes_dir=None, size=256, seed=1999) -> dict:
    from pixelcoat.core import material_grammar as mg

    rows = []
    for path in sorted(glob.glob(os.path.join(materials_dir, "*.json"))):
        g = mg.MaterialGrammar.load(path)
        row = measure(g, mg.synthesize(g, size=size, seed=seed))
        row["faults"] = judge(row)
        rows.append(row)

    themes = []
    if themes_dir:
        by_id = {r["id"]: r for r in rows}
        for path in sorted(glob.glob(os.path.join(themes_dir, "*.json"))):
            with open(path, encoding="utf-8") as f:
                t = json.load(f)
            used = [by_id[gid] for gid in t.get("materials", {}).values()
                    if gid in by_id]
            env = [r for r in used if r["kind"] in TERTIARY_KINDS]
            if not env:
                continue
            themes.append({
                "theme": t.get("theme"),
                "kinds": len(used),
                # sect.3: the compositional target is about the ENVIRONMENTAL
                # base, so average over the tertiary tier only.
                "chroma_mean": sum(r["chroma_mean"] for r in env) / len(env),
                "hf_energy": sum(r["hf_energy"] for r in env) / len(env),
                "faulted": sorted(r["id"] for r in used if r["faults"]),
            })

    return {"budget": ENV_BUDGET, "size": size, "seed": seed,
            "materials": rows, "themes": themes}


def _print(result) -> None:
    rows = result["materials"]
    env = [r for r in rows if r["kind"] in TERTIARY_KINDS]

    print(f"{'grammar':30s} {'kind':13s} {'Cmean':>6s} {'C95':>6s} "
          f"{'Lrange':>6s} {'crush':>6s} {'blown':>6s} {'hf':>6s} {'rgh':>5s}  n")
    print("-" * 100)
    for r in sorted(rows, key=lambda r: (-r["chroma_mean"])):
        mark = "!" * min(len(r["faults"]), 3) if r["faults"] else ""
        rg = f"{r['rough_mean']:.2f}" if r["rough_mean"] is not None else "  - "
        print(f"{r['id']:30s} {r['kind']:13s} {r['chroma_mean']:6.3f} "
              f"{r['chroma_p95']:6.3f} {r['value_range']:6.3f} "
              f"{r['crushed_frac']:6.3f} {r['blown_frac']:6.3f} "
              f"{r['hf_energy']:6.3f} {rg:>5s}  {mark}")

    if env:
        cm = sorted(r["chroma_mean"] for r in env)
        print(f"\nenvironment-tier chroma_mean distribution over {len(cm)} "
              f"grammars: min {cm[0]:.3f}  p50 {cm[len(cm)//2]:.3f}  "
              f"p90 {cm[int(len(cm)*0.9)]:.3f}  max {cm[-1]:.3f}   "
              f"(budget {ENV_BUDGET['chroma_mean']:.3f})")

    faulted = [r for r in rows if r["faults"]]
    print(f"\n{len(faulted)} of {len(rows)} grammars over budget:\n")
    for r in sorted(faulted, key=lambda r: -len(r["faults"])):
        print(f"  {r['id']} [{r['kind']}]")
        for f in r["faults"]:
            print(f"      {f}")

    if result["themes"]:
        print(f"\n{'theme':18s} {'kinds':>5s} {'envC':>6s} {'envHF':>6s}  over budget")
        print("-" * 78)
        for t in sorted(result["themes"], key=lambda t: -t["chroma_mean"]):
            print(f"{t['theme']:18s} {t['kinds']:5d} {t['chroma_mean']:6.3f} "
                  f"{t['hf_energy']:6.3f}  {', '.join(t['faulted']) or '-'}")


# --------------------------------------------------------------------------- #
# The gate. A red-on-main test of 30 pre-existing offenders gets ignored within
# a week, so the audit does not assert the budget -- it asserts NO REGRESSION
# against a committed snapshot. The budget is what you burn the baseline down
# toward; the baseline is what stops it drifting back up while you do.
# --------------------------------------------------------------------------- #

# Lower is better for all of these; rough_mean is handled separately (higher is
# better -- sect.7 wants environment surfaces matte).
_WORSE_IF_HIGHER = ("chroma_mean", "chroma_p95", "value_range",
                    "crushed_frac", "blown_frac", "hf_energy")
_TOLERANCE = 0.002      # synthesis is deterministic; this is float noise only


def snapshot(result) -> dict:
    """The committable form: metrics only, no judgements. A budget change must
    not silently rewrite the baseline."""
    keep = _WORSE_IF_HIGHER + ("rough_mean", "kind", "tier", "emissive")
    return {
        "size": result["size"], "seed": result["seed"],
        "materials": {r["id"]: {k: r[k] for k in keep if k in r}
                      for r in result["materials"]},
    }


def regressions(result, baseline: dict, tol: float = _TOLERANCE) -> list:
    """What got worse since the snapshot. New grammars are not regressions --
    they are judged by the budget, which `judge` already did."""
    if (baseline.get("size"), baseline.get("seed")) != (result["size"],
                                                        result["seed"]):
        raise ValueError(
            f"baseline was taken at size={baseline.get('size')} "
            f"seed={baseline.get('seed')}, this run is size={result['size']} "
            f"seed={result['seed']} -- the numbers are not comparable")
    out = []
    old = baseline.get("materials", {})
    for row in result["materials"]:
        was = old.get(row["id"])
        if was is None:
            continue
        for key in _WORSE_IF_HIGHER:
            if key in was and row[key] > was[key] + tol:
                out.append(f"{row['id']}: {key} {was[key]:.4f} -> "
                           f"{row[key]:.4f}")
        if was.get("rough_mean") is not None and row["rough_mean"] is not None:
            if row["rough_mean"] < was["rough_mean"] - tol:
                out.append(f"{row['id']}: rough_mean {was['rough_mean']:.4f} "
                           f"-> {row['rough_mean']:.4f} (glossier)")
        if row["emissive"] and not was.get("emissive"):
            out.append(f"{row['id']}: gained an emissive channel")
    return out


def dropped(result, baseline: dict) -> list:
    """Grammars the baseline knows about that this run did not measure."""
    seen = {r["id"] for r in result["materials"]}
    return sorted(set(baseline.get("materials", {})) - seen)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--materials", default="profiles/materials")
    ap.add_argument("--themes", default="profiles/themes")
    ap.add_argument("--size", type=int, default=256)
    ap.add_argument("--seed", type=int, default=1999)
    ap.add_argument("--json", default=None, help="also write the raw rows here")
    ap.add_argument("--baseline", default=None,
                    help="compare against this snapshot and fail on REGRESSION "
                         "only; over-budget rows already in the snapshot are "
                         "reported but do not fail")
    ap.add_argument("--write-baseline", default=None, metavar="PATH",
                    help="write today's numbers as the snapshot to beat")
    args = ap.parse_args(argv)

    result = audit(args.materials, args.themes, size=args.size, seed=args.seed)
    _print(result)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, sort_keys=True)
        print(f"\nwrote {args.json}")

    if args.write_baseline:
        with open(args.write_baseline, "w", encoding="utf-8") as f:
            json.dump(snapshot(result), f, indent=2, sort_keys=True)
        n = len(result["materials"])
        print(f"\nwrote baseline for {n} grammars to {args.write_baseline}")
        return 0

    if args.baseline:
        with open(args.baseline, encoding="utf-8") as f:
            base = json.load(f)
        regs = regressions(result, base)
        gone = dropped(result, base)
        for d in gone:
            print(f"\n  note: {d} is in the baseline but was not measured")
        if regs:
            print(f"\n{len(regs)} REGRESSION(S) against {args.baseline}:")
            for r in regs:
                print(f"  {r}")
            return 1
        print(f"\nno regressions against {args.baseline} "
              f"({len(base.get('materials', {}))} grammars)")
        return 0

    return 1 if any(r["faults"] for r in result["materials"]) else 0


if __name__ == "__main__":
    sys.exit(main())
