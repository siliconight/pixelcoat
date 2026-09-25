"""Source-free material synthesis from a grammar (roadmap Technique T03).

A *material grammar* is structured data (JSON) describing how to build a
complete tiling material — base colour family, a macro/meso/micro frequency
budget, named procedural generators, and a response (roughness) rule — with no
reference photograph. :func:`synthesize` composes the primitives in
``procedural_surface`` into aligned map arrays; :func:`build_material_pack`
writes them to disk as a Pixelcoat pack that Zoo's ``core.skins.load_pack``
resolves directly.

Scope decisions (grounded in the factory's verified runtime, not guessed):

- **Albedo-first.** Zoo applies packs to per-vertex-lit StandardMaterial3D and
  the Lux stylized shader samples only albedo/emissive, so albedo carries the
  look. Roughness is emitted as a light response; a normal map is emitted only
  when the grammar asks (it pays off on Lux's pc2000 lightmapped path, and is
  inert on the default per-vertex path — emitting it is optional, never load-
  bearing).
- **Tiling by contract.** Every map is wrap-exact (the primitives guarantee it);
  the normal map is derived with wrapped derivatives so it tiles too.
- **Deterministic.** Same grammar + seed + size ⇒ byte-identical PNGs.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from PIL import Image

from . import maps, pack as pack_meta, procedural_surface as ps
from . import material_response as mr
from . import weathering
from ..version import __version__, DEFAULT_SEED

__all__ = ["MaterialGrammar", "synthesize", "build_material_pack",
           "build_theme_library"]

_DEFAULT_BANDS = {"macro": 0.4, "meso": 0.4, "micro": 0.2}

#: What a fully wet surface's roughness converges to. CHOSEN, not derived: the
#: middle of the 0.05-0.10 band usually quoted for outdoor standing water in a
#: microfacet model, and nobody here has measured a puddle. Named, and
#: overridable per grammar through `wet.water_roughness`, because it is a guess
#: that should be cheap to move after the first look at a lit street.
WATER_ROUGHNESS = 0.08


@dataclass
class MaterialGrammar:
    id: str
    kind: str = "concrete"                      # Zoo material-kind for resolution
    base_colors: list = field(default_factory=lambda: ["#808080"])
    undercoat: str | None = None                # exposed by chips (painted kinds)
    cavity: str | None = None                   # darkest recess colour
    meters_per_tile: float = 1.0
    bands: dict = field(default_factory=lambda: dict(_DEFAULT_BANDS))
    macro: dict = field(default_factory=dict)   # low-freq colour/condition drift
    meso: dict = field(default_factory=dict)    # material identity / structure
    micro: dict = field(default_factory=dict)   # close-range surface response
    chips: dict = field(default_factory=dict)   # optional damage (expose under/cavity)
    #: Crisp cracks / seams, from the F2-F1 ridge field.
    #: `{cells, thr, strength, sparsity}`.
    #:
    #: `cells` is PER AXIS: a cell is `meters_per_tile / cells` across and a
    #: tile holds `cells**2` of them. Two grammars were authored against the
    #: other reading and came out an order of magnitude off.
    #:
    #: F2-F1 IS A COMPLETE TESSELLATION. Every cell is closed by its own
    #: walls at every threshold, so `thr` controls how THIN a crack is and
    #: never how MANY -- which is why asphalt, concrete and sidewalk all
    #: shipped crazy paving while their notes claimed "a few cracks"
    #: (cold run 9041's frames). `sparsity` is the fraction of the net that
    #: draws: a second low-frequency field is thresholded at its own
    #: quantile so whole runs go uncracked and the survivors begin and end.
    #: 1.0 is the tessellation, unchanged, and is the default -- grout and
    #: panel seams want the whole net.
    edges: dict = field(default_factory=dict)
    scratches: dict = field(default_factory=dict)  # crisp directional wear lines
    streaks: dict = field(default_factory=dict)  # vertical gravity grime/water stains
    form_lines: dict = field(default_factory=dict)  # formwork seams;
    #   {count, seam, jitter, strength, axis='y', cross={...}} -- `cross`
    #   adds the perpendicular pass that makes a panel GRID
    veins: dict = field(default_factory=dict)   # flowing veins (marble/stone)
    masonry: dict = field(default_factory=dict)  # brick/tile bond + mortar/grout
    aggregate: dict = field(default_factory=dict)  # filled Voronoi stones/chips
    #: A PRINTED REPEAT poured in colour: carpet medallions, flocked damask.
    #: `{count, petals, radius, arms, swirl, scroll, corner, aspect, line,
    #: ogee, wobble}` go to `procedural_surface.medallion`; `colors` is
    #: [primary ink, secondary ink] (secondary defaults to primary);
    #: `strength` how far the ink replaces the ground (1.0 = fully);
    #: `relief` how much the ink raises the height field; `roughness` a
    #: response offset on the ink (flock is matte against a satin ground),
    #: added after quantising, like chips' wear. The ink keeps the ground's
    #: meso/micro/grain modulation, so a printed figure is still carpet pile.
    motif: dict = field(default_factory=dict)
    #: WORN AND STAINED AREAS, a spec or a list of them, each
    #: `{generator, coverage, color, strength, feather, roughness}`. The
    #: generator (default fbm 3 cells x 3 octaves) is cut at its own quantile
    #: so `coverage` is the fraction of the tile touched -- the reason
    #: `cutout.coverage` and `edges.sparsity` are quantiles. `feather` (0..1)
    #: ramps the edge over that share of the field above the cut, so a
    #: traffic lane fades out and a stain can be hard. Pulls albedo toward
    #: `color`; `roughness` offsets the response in the same mask (crushed
    #: pile is glossier). Irregular by construction: a thresholded fbm is not
    #: a round cell, which is the walker's standing complaint about Worley
    #: blotches on walls.
    wear: Any = field(default_factory=dict)
    detail_strength: float = 0.15               # crisp per-texel grain (anti-smear)
    albedo_pattern: float = 1.0                 # how much meso/micro/grain tint albedo
    posterize: int = 0                          # albedo value steps (Q2 crispness); 0 = off
    roughness: dict = field(default_factory=lambda: {"base": 0.7, "variation": 0.2})
    height_strength: float = 0.6
    emissive: dict = field(default_factory=dict)  # backlit glow (stained glass, screens)
    transparency: dict = field(default_factory=dict)  # see-through glass: {opacity, ior}
    # CUTOUT: an alpha channel on the albedo, 1 where a generator field is at
    # or above `threshold` and 0 where it is not -- paint worn through to the
    # road, a grate's holes. `{generator: {...}, threshold: 0..1, invert}`.
    # Pair it with `transparency: {alpha_mode: "scissor"}` so the consumer
    # tests the alpha rather than blending it; a marking is crisp or gone.
    #
    # `coverage` (0..1), when given, replaces `threshold`: the fraction of
    # the tile the alpha keeps, cut at the field's own quantile. A fixed
    # threshold is not a fraction -- an fbm's spread narrows as octaves are
    # added, so the same 0.40 kept 90% of `road_paint_delco` at 3 cells x 4
    # octaves and 23% at 2 cells x 7 (measured at 1024 px, seed 1999). The
    # same reason `edges.sparsity` is a quantile.
    cutout: dict = field(default_factory=dict)
    #: DIRECTIONAL WARP: displace the whole composed surface along one
    #: direction by an amount a noise field decides -- the Substance node
    #: of the same name. `{generator, intensity, angle}`: `intensity` is
    #: the largest displacement as a FRACTION OF THE TILE (0.04 is four
    #: percent of its width), `angle` degrees clockwise from +x. Wrapped,
    #: so a tiling texture stays tiling.
    #:
    #: WHY IT MATTERS MORE THAN ANOTHER NOISE LAYER. Blending a noise over
    #: a grid changes its colour and leaves the grid; warping MOVES the
    #: grid, so a mortar line bends, a paving joint wanders and a kerb
    #: edge stops being a ruler. Everything this pipeline shipped before
    #: it was laid by a machine, which is what the walker kept seeing.
    warp: dict = field(default_factory=dict)
    #: WET VARIANT: a second albedo and roughness for the same surface with
    #: water on it, written into the same pack as `wet_albedo`,
    #: `wet_roughness` and `wetness`.
    #:
    #: `{"responds_like": <material_response preset>, "amount": 0..1,
    #:   "floor": 0..1, "cavity_bias": 0..1, "saturation": 0..1,
    #:   "water_roughness": 0..1}`.
    #:
    #: `saturation` is how far toward WATER a fully wet texel's roughness
    #: travels, and 1 means it arrives. Omitted, it falls back to the preset's
    #: `wet_gloss_boost`. The response used to subtract that boost instead,
    #: which could not reach water at all -- at 1 it clipped to roughness 0, a
    #: mirror -- so the roughness now lerps toward `water_roughness`
    #: (`WATER_ROUGHNESS` by default) and lands on it by construction.
    #:
    #: `amount` is the saturation ceiling and `floor` is the fraction of it the
    #: DRIEST texel gets, with the pooling spending what is left. A ground
    #: plane under rain needs a floor and a wall does not: measured on the
    #: first build, `asphalt_delco` at `amount 0.9` and no floor came out 17%
    #: darker on average, mask mean 0.36 -- damp, not raining. That is
    #: `weathering.wetness_mask` working correctly for what it was written
    #: for, water that has run down a surface and collected; it normalises to
    #: its own maximum, so its mass sits near 0.4 whatever `amount` says, and
    #: raising `amount` scales that distribution rather than moving it.
    #: `floor: 0.0` reproduces the old behaviour to the float.
    #:
    #: A SECOND MATERIAL, NOT A SECOND PASS, and that is the whole reason it
    #: exists. LF 0.110.0 priced a wet `next_pass` on a real package at
    #: 2.27-4.29 us per ADDED DRAW CALL -- flat per submission, not per pixel
    #: -- which is +8.05 ms at the worst station of `crossroads_9600`. A
    #: variant material draws the same triangles once.
    #:
    #: `responds_like` names a `material_response.PRESETS` family and the
    #: response is read from it: this repo's wetness model lives there and the
    #: gen7 pipeline already uses it. Deriving the response from the grammar's
    #: own dry roughness was tried and refused: `wet_darken / dry_roughness` is
    #: 0.50 concrete, 0.44 brick, 0.83 wood, 0.71 painted metal, because
    #: darkening tracks porosity and wood is smoother than brick and darkens
    #: more. A grammar declares no porosity, so it declares the family.
    #:
    #: Refuses a grammar that emits no roughness -- there would be nothing for
    #: the water to smooth, and a wet material with a dry response is a
    #: material that looks wet and lights dry.
    wet: dict = field(default_factory=dict)
    emit: dict = field(default_factory=lambda: {"roughness": True, "normal": False})
    # ACHROMATIC-BY-INTENT. True means "my albedo is a surface, not a paint
    # job -- the consumer supplies the hue". Zoo multiplies the mesh's own
    # base colour into a tintable pack and skips it for every other pack, so
    # a rusted-metal facade keeps its rust while a plastic shroud takes the
    # genome's red. Keyed here and not on `kind` because one kind (metal)
    # legitimately serves both cases.
    tintable: bool = False

    @classmethod
    def from_dict(cls, raw: dict) -> "MaterialGrammar":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in raw.items() if k in known})

    @classmethod
    def load(cls, path: str) -> "MaterialGrammar":
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))


# --------------------------------------------------------------------------- #
# Generator dispatch
# --------------------------------------------------------------------------- #

def _generator(spec: dict, size, seed: int, label: str) -> np.ndarray:
    """Evaluate a named generator spec → field in [0, 1]. Empty spec → flat 0.5."""
    if not spec:
        return np.full(_hw(size), 0.5, np.float32)
    gen = spec.get("generator", "fbm")
    if gen == "fbm":
        return ps.fbm(size, spec.get("cells", 32), spec.get("octaves", 3), seed,
                      label=label)
    if gen == "value_noise":
        return ps.value_noise(size, spec.get("cells", 16), seed, label=label)
    if gen == "directional_grain":
        return ps.directional_grain(
            size, spec.get("cells_along", 4), spec.get("cells_across", 48),
            seed, axis=spec.get("axis", "x"), label=label)
    if gen == "worley_f1":
        return ps.worley_f1(size, spec.get("cells", 12), seed, label=label)
    if gen == "worley_edges":
        return ps.worley_edges(size, spec.get("cells", 12), seed, label=label)
    if gen in ("hash_grain", "grain"):
        return ps.hash_grain(size, seed, label=label)
    if gen == "stripes":
        return ps.stripes(size, spec.get("count", 5), seed,
                          axis=spec.get("axis", "x"),
                          seam=spec.get("seam", 0.35),
                          jitter=spec.get("jitter", 0.12), label=label)
    if gen == "weave":
        return ps.weave(size, spec.get("count", 40), seed, label=label)
    if gen == "veins":
        return ps.veins(size, seed, base_cells=spec.get("cells", 4),
                        octaves=spec.get("octaves", 4),
                        sharpness=spec.get("sharpness", 3.0), label=label)
    if gen == "ribs":
        return ps.ribs(size, spec.get("count", 12), seed,
                       axis=spec.get("axis", "x"), label=label)
    if gen == "wave":
        return ps.wave(size, spec.get("count", 12), seed,
                       axis=spec.get("axis", "x"),
                       warp=spec.get("warp", 0.15),
                       warp_cells=spec.get("warp_cells", 4), label=label)
    raise ValueError(f"unknown generator {gen!r}")


def _centered(field01: np.ndarray) -> np.ndarray:
    """Map [0,1] → [-1,1] around the field's own mean (structure, not bias)."""
    return np.clip((field01 - float(field01.mean())) * 2.0, -1.0, 1.0)


def _hw(size):
    return ps._as_hw(size)


# --------------------------------------------------------------------------- #
# Synthesis
# --------------------------------------------------------------------------- #

def _apply_form_lines(albedo, height, size, cfg, axis, seed):
    """One pass of formwork seams along `axis`, darkening albedo and height.

    Split out so the primary and the `cross` pass are literally the same code:
    two spellings of a seam is how one direction ends up with a jitter the
    other does not.
    """
    fl = ps.stripes(size, cfg.get("count") or 6, seed, axis=axis,
                    seam=cfg.get("seam", 0.5) if cfg.get("seam") is not None else 0.5,
                    jitter=cfg.get("jitter", 0.05) if cfg.get("jitter") is not None else 0.05)
    # stripes() is bright bands with dark seams; pull out the seam darkening.
    dark = np.clip(0.5 - fl, 0.0, 0.5) * 2.0
    st = cfg.get("strength", 0.25) if cfg.get("strength") is not None else 0.25
    return albedo * (1.0 - st * dark)[..., None], height - dark * 0.3


def roughness_levels(grammar) -> int:
    """How many steps a posterized grammar's roughness is quantised to."""
    return max(4, int(grammar.posterize) // 2) if grammar.posterize else 0


def _roughness(grammar, meso_s, chip_mask, grain_s=None, extra=None):
    """The response rule: ``base + variation * meso``, stepped when the
    grammar posterizes, plus the chips' wear.

    THE STEPS SPAN THE DECLARED BAND, NOT [0, 1]. Up to 0.40.0 the stepped
    roughness was `posterize(base + variation * meso, levels)` -- a grid of
    `1 / (levels - 1)` laid over the whole unit range. Every shipped grammar
    declares a variation of 0.04-0.18, and the grid's step is 0.14-0.33, so
    the band a grammar asked for held one or two grid points and nothing
    between them. `metal_bare_neutral` (0.28 +- 0.11, 7 levels, step 1/6)
    shipped exactly 0.165 and 0.333 at 128 px, 27.2% of the tile at the
    glossy one, in runs averaging 64.6 px along x and 1.9 px across it:
    horizontal bars half a metre long. At Zoo's metallic 0.9 the glossy bars
    mirrored a dark room as black streaks across every bare face (Zoo's vault
    door, 2026-09-14). `metal_painted_neutral` collapsed to one value, 0.400,
    and `metal_chrome_casino` put 3% of its tile at 0.000.

    So the level count is unchanged and the steps are laid across
    `base +- variation`: the grammar gets the stepped response it asked for
    AND the variation it declared. Chips add after quantising, so worn
    patches keep their exact +0.2.
    """
    r = grammar.roughness or {}
    base, var = float(r.get("base", 0.7)), float(r.get("variation", 0.2))
    v = meso_s
    # GRAIN (0..1): how much of the variation comes from per-texel grain
    # instead of the meso. The meso is the material's STRUCTURE, and for a
    # brushed metal that structure is rows half a metre long -- a response
    # driven by it alone draws those rows in the reflection. Grain varies
    # the response at the scale of one texel, which reads up close and
    # averages away in the mips before it can form a line. 0 (the default)
    # is the meso alone and draws no stream.
    g = min(max(float(r.get("grain", 0.0)), 0.0), 1.0)
    if g > 0.0 and grain_s is not None:
        v = (1.0 - g) * meso_s + g * grain_s
    if grammar.posterize:
        v = ps.posterize((v + 1.0) * 0.5, roughness_levels(grammar)) * 2.0 - 1.0
    rough = base + var * v
    if chip_mask is not None:
        rough = rough + chip_mask * 0.2                      # bare/worn is rougher
    if extra is not None:
        rough = rough + extra             # motif ink / wear offsets, unstepped
    return np.clip(rough, 0.0, 1.0)


def _warp_offsets(spec, size, seed):
    """(dy, dx) integer pixel offsets for a directional warp, wrapped."""
    h, w = _hw(size)
    field = _generator(spec.get("generator") or {"generator": "fbm", "cells": 4,
                                                 "octaves": 3},
                       (h, w), ps.stream_seed(seed, "warp"), "warp")
    amp = float(spec.get("intensity", 0.04)) * max(h, w)
    ang = math.radians(float(spec.get("angle", 0.0)))
    push = _centered(field) * amp
    dy = np.rint(push * math.sin(ang)).astype(np.int64)
    dx = np.rint(push * math.cos(ang)).astype(np.int64)
    return dy, dx


def _warp_apply(arr, dy, dx):
    """Sample ``arr`` at each pixel displaced by (dy, dx), wrapped. Nearest,
    not bilinear: every pack here is read under a nearest filter, and a
    resampled edge would be the soft fringe the whole pipeline avoids."""
    h, w = arr.shape[:2]
    ys, xs = np.mgrid[0:h, 0:w]
    sy = (ys + dy) % h
    sx = (xs + dx) % w
    return arr[sy, sx]


def synthesize(grammar: MaterialGrammar, size=512, seed: int = DEFAULT_SEED) -> dict:
    """Compose a grammar into aligned map arrays.

    Returns a dict with ``albedo`` (H,W,3 uint8) and, per the grammar's ``emit``,
    ``roughness`` (H,W uint8) and ``normal`` (H,W,3 uint8). All tileable.
    """
    h, w = _hw(size)
    bands = {**_DEFAULT_BANDS, **(grammar.bands or {})}
    base_cols = [ps.hex_to_rgb(c) for c in grammar.base_colors] or [ps.hex_to_rgb("#808080")]

    # Macro: which base colour, plus a gentle value drift across the tile.
    macro = _generator(grammar.macro or {"generator": "fbm", "cells": 3, "octaves": 2},
                       (h, w), ps.stream_seed(seed, "macro"), "macro")
    if len(base_cols) > 1:
        sel = np.clip(macro * (len(base_cols) - 1), 0, len(base_cols) - 1 - 1e-6)
        lo = np.floor(sel).astype(int)
        fr = (sel - lo)[..., None]
        palette = np.stack(base_cols, 0)
        base = palette[lo] * (1 - fr) + palette[np.minimum(lo + 1, len(base_cols) - 1)] * fr
    else:
        base = np.broadcast_to(base_cols[0], (h, w, 3)).copy()
    base = base * (1.0 + bands["macro"] * 0.25 * _centered(macro)[..., None])

    # Meso: material identity / structure.
    meso = _generator(grammar.meso, (h, w), ps.stream_seed(seed, "meso"), "meso")
    meso_s = _centered(meso)

    # Micro: close-range breakup.
    micro = _generator(grammar.micro or {"generator": "fbm", "cells": 96, "octaves": 3},
                       (h, w), ps.stream_seed(seed, "micro"), "micro")
    micro_s = _centered(micro)

    # Crisp per-texel grain — the anti-smear layer. Full-res white-ish noise
    # (no lattice smoothing), so it survives Zoo's nearest-filter import as
    # sharp stipple rather than a soft blur.
    grain_s = _centered(ps.hash_grain((h, w), ps.stream_seed(seed, "grain"),
                                      label="grain"))

    # ``albedo_pattern`` scales how much the meso/micro/grain pattern tints the
    # albedo, independent of the height field (which keeps the full pattern for
    # the normal map). Glass wants a near-clear albedo (~0.1) with a strong
    # normal — set it low without flattening the bump.
    ap = grammar.albedo_pattern
    value_mod = (1.0
                 + ap * bands["meso"] * 0.30 * meso_s
                 + ap * bands["micro"] * 0.12 * micro_s
                 + ap * grammar.detail_strength * grain_s)
    albedo = base * value_mod[..., None]
    height = (bands["meso"] * meso_s + bands["micro"] * 0.4 * micro_s
              + grammar.detail_strength * 0.3 * grain_s)

    # Crisp cracks / panel seams (hard-thresholded F2-F1 ridges).
    if grammar.edges:
        e = ps.worley_edges((h, w), grammar.edges.get("cells", 16),
                            ps.stream_seed(seed, "edges"), label="edges")
        crack = (e >= grammar.edges.get("thr", 0.72)).astype(np.float32)
        # SPARSITY: keep only the fraction of the net that falls under a
        # low-frequency mask. Thresholded at the field's own quantile so the
        # fraction is the fraction asked for rather than whatever a fixed
        # cut happens to pass on this seed.
        sp = float(grammar.edges.get("sparsity", 1.0))
        if sp < 1.0:
            keep = _generator(grammar.edges.get("mask") or
                              {"generator": "fbm", "cells": 2, "octaves": 2},
                              (h, w), ps.stream_seed(seed, "edge_mask"),
                              "edge_mask")
            crack = crack * (keep >= np.quantile(keep, 1.0 - max(sp, 0.0))
                             ).astype(np.float32)
        st = grammar.edges.get("strength", 0.5)
        albedo = albedo * (1.0 - st * crack)[..., None]
        height = height - crack * 0.6

    # Crisp directional scratches (metal/plastic edge wear).
    if grammar.scratches:
        sc = ps.scratches((h, w), ps.stream_seed(seed, "scratch"),
                          axis=grammar.scratches.get("axis", "x"),
                          density=grammar.scratches.get("density", 0.05),
                          length_cells=grammar.scratches.get("length_cells", 3))
        st = grammar.scratches.get("strength", 0.4)
        col = ps.hex_to_rgb(grammar.scratches.get("color",
                                                  grammar.undercoat or "#c8c8c8"))
        m = (st * sc)[..., None]
        albedo = albedo * (1.0 - m) + col * m
        height = height + sc * 0.15

    # Flowing veins (marble / figured stone) — one or more coloured vein
    # networks. ``veins`` may be a single spec (one network) or a list of specs
    # (multi-scale: broad structural veins + fine hairline threading). Pass 0
    # keeps the "veins" stream label so single-network grammars stay
    # byte-identical; later passes draw independent streams.
    if grammar.veins:
        passes = grammar.veins if isinstance(grammar.veins, list) else [grammar.veins]
        for i, vp in enumerate(passes):
            label = "veins" if i == 0 else f"veins:{i}"
            vn = ps.veins((h, w), ps.stream_seed(seed, label),
                          base_cells=vp.get("cells", 4),
                          octaves=vp.get("octaves", 4),
                          sharpness=vp.get("sharpness", 3.0))
            st = vp.get("strength", 0.5)
            col = ps.hex_to_rgb(vp.get("color", "#6a635a"))
            m = (st * vn)[..., None]
            albedo = albedo * (1.0 - m) + col * m
            height = height - vn * 0.1

    # Masonry bond — per-unit tone variation + mortar/grout lines (brick/tile).
    if grammar.masonry:
        mm = grammar.masonry
        mort, unit = ps.masonry((h, w), mm.get("rows", 8), mm.get("cols", 4),
                                ps.stream_seed(seed, "masonry"),
                                offset=mm.get("offset", 0.5),
                                mortar=mm.get("mortar", 0.05))
        var = mm.get("brick_variation", 0.18)
        albedo = albedo * (1.0 + var * (unit - 0.5))[..., None]
        mcol = ps.hex_to_rgb(mm.get("mortar_color", "#9a958c"))
        m = (mort * mm.get("mortar_strength", 1.0))[..., None]
        albedo = albedo * (1.0 - m) + mcol * m
        height = height - mort * 0.5

    # Aggregate — filled irregular Voronoi cells, each poured a palette colour,
    # with a mortar/matrix line between (cobblestone, flagstone, terrazzo chips,
    # pebble/gravel, crazy-paving). ``colors`` is the per-cell palette (defaults
    # to base_colors); ``fill`` how strongly the chip colour replaces the base;
    # ``variation`` a per-cell tone jitter; ``gap``/``gap_color``/``gap_strength``
    # the matrix line.
    if grammar.aggregate:
        ag = grammar.aggregate
        gapm, cid = ps.voronoi_cells((h, w), ag.get("cells", 10),
                                     ps.stream_seed(seed, "aggregate"),
                                     gap=ag.get("gap", 0.04))
        chip_cols = [ps.hex_to_rgb(c) for c in (ag.get("colors") or grammar.base_colors)]
        if chip_cols:
            sel = np.clip(cid * len(chip_cols), 0, len(chip_cols) - 1e-6).astype(int)
            chip = np.stack(chip_cols, 0)[sel]
            fill = ag.get("fill", 1.0)
            albedo = albedo * (1.0 - fill) + chip * fill
        var = ag.get("variation", 0.0)
        if var:
            albedo = albedo * (1.0 + var * (cid - 0.5))[..., None]
        mcol = ps.hex_to_rgb(ag.get("gap_color", "#3a3a3a"))
        gm = (gapm * ag.get("gap_strength", 1.0))[..., None]
        albedo = albedo * (1.0 - gm) + mcol * gm
        height = height - gapm * 0.5

    # A printed repeat. The ink is poured over the ground but keeps the
    # ground's `value_mod`, so the figure is pile or flock with the same
    # grain as what it is printed on, not a decal lying across it.
    rough_extra = None
    if grammar.motif:
        mo = grammar.motif
        keys = ("count", "petals", "radius", "arms", "swirl", "scroll",
                "corner", "aspect", "line", "ogee", "wobble")
        ink = ps.medallion((h, w), mo.get("count", 2),
                           ps.stream_seed(seed, "motif"), label="motif",
                           **{k: mo[k] for k in keys[1:] if k in mo})
        cols = [ps.hex_to_rgb(c) for c in (mo.get("colors") or ["#808080"])]
        primary = cols[0]
        secondary = cols[1] if len(cols) > 1 else cols[0]
        st = float(mo.get("strength", 1.0))
        p_m = (ink == 1.0).astype(np.float32)
        s_m = (ink == 0.5).astype(np.float32)
        tinted = value_mod[..., None]
        albedo = (albedo * (1.0 - st * (p_m + s_m))[..., None]
                  + primary * tinted * (st * p_m)[..., None]
                  + secondary * tinted * (st * s_m)[..., None])
        inked = np.clip(p_m + s_m, 0.0, 1.0)
        height = height + inked * float(mo.get("relief", 0.3))
        if mo.get("roughness"):
            rough_extra = inked * float(mo["roughness"])

    # Form-board seams (concrete formwork lines) — subtle dark bands.
    #
    # `axis` DEFAULTS TO "y", which is where this started and what every
    # grammar written before it existed still gets: horizontal board courses.
    # `cross` adds a second pass on the perpendicular axis, which is what
    # turns bands into a GRID -- and a grid is the difference between
    # board-formed concrete and precast panels. `concrete_panel_delco` could
    # not read as panels at any `count` while this only drew one direction;
    # the operator's verdict on it, "reads as stripes, not intentional
    # architecture", was a capability report and not a taste note.
    #
    # `cross` inherits the primary's seam/jitter/strength unless it overrides
    # them, because a panel wall's two joint directions are usually the same
    # joint seen twice.
    if grammar.form_lines:
        fl_cfg = grammar.form_lines
        axis = str(fl_cfg.get("axis", "y")).lower()
        albedo, height = _apply_form_lines(
            albedo, height, (h, w), fl_cfg, axis,
            ps.stream_seed(seed, "form"))
        cross = fl_cfg.get("cross")
        if cross:
            other = "x" if axis == "y" else "y"
            merged = {k: cross.get(k, fl_cfg.get(k))
                      for k in ("count", "seam", "jitter", "strength")}
            albedo, height = _apply_form_lines(
                albedo, height, (h, w), merged,
                str(cross.get("axis", other)).lower(),
                ps.stream_seed(seed, "form_cross"))

    # Vertical grime/water streaks (interior-concrete stain character).
    if grammar.streaks:
        sv = ps.streaks((h, w), ps.stream_seed(seed, "streaks"),
                        density=grammar.streaks.get("density", 0.25),
                        decay=grammar.streaks.get("decay", 0.95))
        st = grammar.streaks.get("strength", 0.35)
        albedo = albedo * (1.0 - st * sv)[..., None]
        height = height - sv * 0.15

    # Worn and stained areas. Pass 0 keeps the plain "wear" label, later
    # passes draw "wear:i", the convention `veins` set so adding a pass never
    # moves the ones before it.
    if grammar.wear:
        passes = grammar.wear if isinstance(grammar.wear, list) else [grammar.wear]
        for i, wp in enumerate(passes):
            label = "wear" if i == 0 else f"wear:{i}"
            fld = _generator(wp.get("generator") or
                             {"generator": "fbm", "cells": 3, "octaves": 3},
                             (h, w), ps.stream_seed(seed, label), label)
            cov = min(max(float(wp.get("coverage", 0.3)), 0.0), 1.0)
            cut = float(np.quantile(fld, 1.0 - cov))
            top = float(fld.max())
            feather = min(max(float(wp.get("feather", 0.5)), 0.0), 1.0)
            if feather > 0.0 and top > cut:
                m = np.clip((fld - cut) / ((top - cut) * feather), 0.0, 1.0)
            else:
                m = (fld >= cut).astype(np.float32)
            m = (m * float(wp.get("strength", 0.5))).astype(np.float32)
            col = ps.hex_to_rgb(wp.get("color", "#808080"))
            albedo = albedo * (1.0 - m)[..., None] + col * m[..., None]
            height = height - m * 0.1
            if wp.get("roughness"):
                off = m * float(wp["roughness"])
                rough_extra = off if rough_extra is None else rough_extra + off

    # Crisp chips: hard-edged clustered damage exposing undercoat then cavity.
    if grammar.chips:
        damage = ps.worley_f1((h, w), grammar.chips.get("cells", 10),
                              ps.stream_seed(seed, "chips"), label="chips")
        thr = grammar.chips.get("amount", 0.2)
        chip_mask = (damage < thr).astype(np.float32)            # hard edge
        if grammar.undercoat:
            under = ps.hex_to_rgb(grammar.undercoat)
            albedo = albedo * (1 - chip_mask[..., None]) + under * chip_mask[..., None]
        if grammar.cavity:
            deep = (damage < thr * 0.4).astype(np.float32)
            cav = ps.hex_to_rgb(grammar.cavity)
            albedo = albedo * (1 - deep[..., None]) + cav * deep[..., None]
        height = height - chip_mask * 0.5
    else:
        chip_mask = None

    # THE WARP, applied to the composed surface and everything derived from
    # it, so the albedo, the height and the roughness all bend together --
    # a warped colour over an unwarped normal reads as a decal sliding on
    # the surface.
    if grammar.warp:
        _dy, _dx = _warp_offsets(grammar.warp, (h, w), seed)
        albedo = _warp_apply(albedo, _dy, _dx)
        height = _warp_apply(height, _dy, _dx)
        meso_s = _warp_apply(meso_s, _dy, _dx)
        micro_s = _warp_apply(micro_s, _dy, _dx)
        grain_s = _warp_apply(grain_s, _dy, _dx)
        if chip_mask is not None:
            chip_mask = _warp_apply(chip_mask, _dy, _dx)
        if rough_extra is not None:
            rough_extra = _warp_apply(rough_extra, _dy, _dx)

    albedo = np.clip(albedo, 0.0, 1.0)
    if grammar.posterize:
        albedo = ps.posterize(albedo, grammar.posterize)   # hard value steps (Q2)

    out: dict[str, Any] = {"albedo": _to_u8(albedo)}
    rough_f = None

    if grammar.cutout:
        co = grammar.cutout
        fld = _generator(co.get("generator") or {"generator": "worley_f1", "cells": 8},
                         (h, w), ps.stream_seed(seed, "cutout"), "cutout")
        if co.get("coverage") is not None:
            cov = min(max(float(co["coverage"]), 0.0), 1.0)
            if co.get("invert"):
                keep = fld < np.quantile(fld, cov)
            else:
                keep = fld >= np.quantile(fld, 1.0 - cov)
        else:
            keep = fld >= float(co.get("threshold", 0.25))
            if co.get("invert"):
                keep = ~keep
        # ELLIPSE: nothing outside an ellipse centred on the tile's corner
        # (wrapped, so it sits at the centre of a card whose UVs run -0.5
        # to 0.5 across it). For a tile that IS one card -- a tree's crown
        # card at `meters_per_tile` = the card's width -- the card's edge
        # becomes the canopy's, ragged by the clusters, and not a hard
        # line. `{"rx": 0.46, "ry": 0.44}` in tile units.
        ell = co.get("ellipse")
        if ell:
            rx, ry = float(ell.get("rx", 0.46)), float(ell.get("ry", 0.46))
            fy, fx = np.meshgrid((np.arange(h) + 0.5) / h, (np.arange(w) + 0.5) / w,
                                 indexing="ij")
            dx, dy = np.minimum(fx, 1.0 - fx), np.minimum(fy, 1.0 - fy)
            keep = keep & ((dx / rx) ** 2 + (dy / ry) ** 2 <= 1.0)
        alpha = keep.astype(np.float32)
        out["albedo"] = _to_u8(np.concatenate([albedo, alpha[..., None]], axis=-1))

    if grammar.emit.get("roughness", True):
        rough_f = _roughness(grammar, meso_s, chip_mask, grain_s, rough_extra)
        out["roughness"] = _to_u8(rough_f)

    if grammar.emit.get("normal", False):
        hf = height - height.min()
        hf = hf / max(hf.max(), 1e-6)
        nrm = maps.normal_from_height(hf.astype(np.float32),
                                      strength=grammar.height_strength * 3.0,
                                      wrap_x=True, wrap_y=True)   # tileable normals
        out["normal"] = _to_u8(np.clip(nrm, 0.0, 1.0))

    # Emissive (backlit glow): stained-glass cells and lit panels. By default
    # the coloured albedo itself glows (so dark lead cames / grout stay dark);
    # ``from: "tint"`` glows a flat colour instead. ``gamma`` punches the
    # saturated cells; ``strength`` scales the whole map.
    if grammar.emissive:
        em = grammar.emissive
        if em.get("from") == "tint":
            glow = np.broadcast_to(ps.hex_to_rgb(em.get("color", "#ffffff")),
                                   (h, w, 3)).astype(np.float32).copy()
        else:
            glow = np.clip(albedo, 0.0, 1.0).astype(np.float32)
        g = em.get("gamma")
        if g:
            glow = np.clip(glow, 0.0, 1.0) ** float(g)
        out["emissive"] = _to_u8(np.clip(glow * em.get("strength", 1.0), 0.0, 1.0))

    if grammar.wet:
        out.update(_wet_maps(grammar, albedo, rough_f, height, seed,
                             out.get("albedo")))

    return out


def _wet_maps(grammar, albedo, rough_f, height, seed, albedo_u8):
    """`wetness`, `wet_albedo` and `wet_roughness` for a grammar's wet block.

    WATER POOLS IN THE LOW PLACES, so the mask comes from the height field the
    rest of the pack was built from, inverted: `weathering.wetness_mask` is the
    same function the gen7 path uses, called with the same meaning of its first
    argument (1 where the surface is recessed). Reusing it keeps one wetness in
    Pixelcoat instead of two that drift.

    `bottom_bias` IS ZERO HERE AND THAT IS NOT A CHOICE. Every grammar pack
    tiles on both axes (`build_material_pack` writes `tileable: ["x", "y"]`), and
    the mask function's own comment says a y-tiling surface has no bottom and a
    linear ramp would cut a seam by construction; it folds the bias into the
    cavity term itself when `wrap_y`. Passing a nonzero value would be asking
    for a term the function is about to discard.

    A CUTOUT GRAMMAR KEEPS ITS ALPHA. `road_paint_delco` is worn through to the
    road by an alpha channel, and a wet albedo without it would hand the
    importer an opaque road marking -- wet paint covering the whole tile.
    """
    w = grammar.wet
    family = str(w.get("responds_like", ""))
    if family not in mr.PRESETS:
        raise ValueError(
            f"grammar '{grammar.id}': wet.responds_like is {family!r}, which "
            f"names no material_response preset; have "
            f"{', '.join(mr.PRESET_NAMES)}")
    if rough_f is None:
        raise ValueError(
            f"grammar '{grammar.id}' declares wetness but emits no roughness. "
            f"Water smooths a surface's response; a wet albedo over a dry "
            f"roughness is a material that looks wet and lights dry.")
    preset = mr.PRESETS[family]
    amount = float(w.get("amount", 0.0))
    if not 0.0 < amount <= 1.0:
        raise ValueError(
            f"grammar '{grammar.id}': wet.amount is {amount}, which is outside "
            f"(0, 1]. A wet block that wets nothing is a pack carrying three "
            f"maps nobody can use.")

    floor = float(w.get("floor", 0.0))
    if not 0.0 <= floor < 1.0:
        raise ValueError(
            f"grammar '{grammar.id}': wet.floor is {floor}, which is outside "
            f"[0, 1). A floor of 1 is a flat mask and the pooling would have "
            f"nothing to spend.")

    recess = height.max() - height
    recess = recess / max(float(recess.max()), 1e-6)
    # THE POOLING IS ASKED FOR AT FULL STRENGTH AND SPENT AFTERWARDS. Passing
    # `amount` into the mask would scale the distribution before the floor is
    # applied, and the floor would then be a fraction of a fraction.
    pooling = weathering.wetness_mask(
        recess.astype(np.float32), 1.0,
        float(w.get("cavity_bias", 0.65)), 0.0,
        ps.stream_seed(seed, "wet"), True, True)
    wmask = (amount * (floor + (1.0 - floor) * pooling)).astype(np.float32)

    wet_albedo = np.clip(
        albedo * (1.0 - preset.wet_darken * wmask[..., None]), 0.0, 1.0)
    if albedo_u8 is not None and albedo_u8.ndim == 3 \
            and albedo_u8.shape[-1] == 4:
        alpha = albedo_u8[..., 3:].astype(np.float32) / 255.0
        wet_albedo = np.concatenate([wet_albedo, alpha], axis=-1)

    # TOWARD WATER, NOT AWAY FROM DRY. This was `dry - boost * mask`, which is
    # gen7's `wet_gloss = gloss + wet_gloss_boost * mask` rearranged. That form
    # cannot reach water: at `boost` 1 asphalt goes 0.95 - 1.0 = -0.05 and
    # clips to roughness 0, a perfect mirror, when standing water sits around
    # 0.05-0.10. A lerp lands on the target by construction, with no clip and
    # no overshoot, and narrows the spread on the way instead of widening it
    # (measured, RAIN_WETNESS.md: the shift raised roughness sd by 5-66%).
    #
    # `reach` is how far a fully wet texel goes. Absent, it is the preset's
    # `wet_gloss_boost`, so PRESETS stays the authority for any grammar that
    # does not declare one.
    reach = float(w.get("saturation", preset.wet_gloss_boost))
    if not 0.0 <= reach <= 1.0:
        raise ValueError(
            f"grammar '{grammar.id}': wet.saturation is {reach}, outside "
            f"[0, 1]. It is the fraction of the way to water a fully wet "
            f"texel travels; past 1 there is nowhere further to go.")
    water = float(w.get("water_roughness", WATER_ROUGHNESS))
    if not 0.0 <= water <= 1.0:
        raise ValueError(
            f"grammar '{grammar.id}': wet.water_roughness is {water}, "
            f"outside [0, 1]")
    lerped = rough_f + (water - rough_f) * reach * wmask
    # NEVER ROUGHER THAN DRY. A material already glossier than water would be
    # lerped UP toward it, which is wetness making a surface less smooth.
    wet_rough = np.clip(np.minimum(rough_f, lerped), 0.0, 1.0)

    return {"wetness": _to_u8(wmask),
            "wet_albedo": _to_u8(wet_albedo),
            "wet_roughness": _to_u8(wet_rough)}


# --------------------------------------------------------------------------- #
# Pack writer — the Zoo-consumable contract
# --------------------------------------------------------------------------- #

def build_material_pack(grammar, pack_dir: str, *, asset_id: str | None = None,
                        size=512, seed: int = DEFAULT_SEED) -> dict:
    """Synthesize + write a Pixelcoat pack into ``pack_dir``. Returns the manifest.

    Writes ``<pack_dir>/{<asset_id>_albedo.png, ..., <asset_id>.pack.json}``.
    The caller owns the directory name — for Zoo's tiling library, name it
    ``<kind>_<theme>`` (e.g. ``metal_delco``) so ``skins.find_pack`` resolves it;
    the map filenames inside are independent of that name.
    """
    if isinstance(grammar, str):
        grammar = MaterialGrammar.load(grammar)
    elif isinstance(grammar, dict):
        grammar = MaterialGrammar.from_dict(grammar)
    asset_id = asset_id or grammar.id

    arrays = synthesize(grammar, size=size, seed=seed)
    os.makedirs(pack_dir, exist_ok=True)

    map_files: dict[str, str] = {}
    for key, arr in arrays.items():
        fname = f"{asset_id}_{key}.png"
        _write_png(arr, os.path.join(pack_dir, fname))
        map_files[key] = fname

    manifest = {
        "schema": "pixelcoat-pack/2",
        "tool_version": __version__,
        "asset_id": asset_id,
        "processing_mode": "procedural",
        "source_kind": "procedural",
        "material_kind": grammar.kind,
        "material_profile": grammar.id,
        "maps": map_files,
        # WHAT IS IN THE FILES, not just their names. A manifest that named
        # filenames alone stayed byte-identical through a grammar retune, so a
        # consumer hashing it -- the obvious cheap thing, and what LF's Zoo
        # adapter did -- could not tell a re-themed material from the old one
        # and shipped the previously baked GLB. See `core/pack.py`.
        "map_sha256": pack_meta.map_sha256(pack_dir, map_files),
        "tileable": ["x", "y"],
        "meters_per_tile": float(grammar.meters_per_tile),
        "seed": int(seed),
        "tintable": bool(grammar.tintable),
        "import_hints": {
            # `wet_albedo` IS A COLOUR MAP AND MUST SAY SO. The gen7 pack
            # writer has always listed it here
            # (`pipeline_generation_7.py:545`); this comprehension predates
            # wetness on the grammar path and would have hinted a colour map
            # as linear data, which an importer obeys silently -- a wet road
            # that is a different colour from the dry one for no reason a
            # frame could explain.
            "color_space": {k: ("srgb" if k in ("albedo", "wet_albedo",
                                                "emissive") else "linear")
                            for k in map_files},
            "normal_format": "opengl",
            "generate_mipmaps": True,
            "interpolation": "nearest",
        },
    }
    # See-through glass: the pack asks the consumer (Zoo -> Godot) for a
    # transparent material. opacity 1.0 = opaque (facade glass you can't see
    # into); < 1.0 = see-through window glass. ior is advisory for refraction.
    if grammar.transparency:
        t = grammar.transparency
        manifest["import_hints"]["transparency"] = {
            "opacity": float(t.get("opacity", 0.6)),
            "ior": float(t.get("ior", 1.45)),
            "alpha_mode": t.get("alpha_mode", "blend"),
        }
    with open(os.path.join(pack_dir, f"{asset_id}.pack.json"), "w",
              encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    return manifest


# Texel density. Zoo lays down world-metre cube-projected UVs and drives a
# Mapping node at 1/meters_per_tile, so a pack's ON-MESH density is
# ``size * texel / meters_per_tile``. A fixed size across a library whose
# meters_per_tile spans 1.0-3.0 therefore ships a 3x density spread -- a window
# at 512 px/m set into a concrete wall at 171 px/m, on every building.
DEFAULT_DENSITY = 128.0          # pixels per world metre
PACK_SIZE_BOUNDS = (64, 1024)


def pack_size_for(meters_per_tile, density: float = DEFAULT_DENSITY,
                  bounds=PACK_SIZE_BOUNDS) -> int:
    """Texture size that puts ``density`` pixels on every world metre.

    Rounded to a power of two: that caps the residual density error at sqrt(2)
    (measured worst case across the shipped library: 1.33x, against 3.0x for a
    fixed size) and keeps every map POT for the GPU.
    """
    mpt = float(meters_per_tile or 1.0)
    size = 2 ** int(round(math.log2(max(float(density) * mpt, 1.0))))
    return int(min(max(size, bounds[0]), bounds[1]))


# WHAT A KIND PROMISES ABOUT LIGHT. The consumer's contract, not a style:
# Zoo glazes every enterable window, teller screen and shelter pane in `glass`
# and every hollow-facade window in `glass_facade` (zoo `recipes/_arch.py`),
# and blends a material only when its pack carries
# `import_hints.transparency` with opacity below 1. So the kind is the
# question "can you see through this" and this field is the answer, and the
# two must agree or the answer is silently wrong.
#
# It was, for a whole theme. `glass_delco` was written with no `transparency`
# block and sat orphaned (0.17.0 noted it); 0.27.0 put it in delco_1997's
# `glass` slot, and every window, teller line, bus shelter and car of that
# theme exported alphaMode OPAQUE -- a dark teal-grey slab across every
# opening. Measured on walk 9050: `M_Skin_glass_delco_1997` OPAQUE on 12
# GLBs, 7 of them window modules. Nothing refused it, because the grammar
# was a legal grammar and the theme a legal theme.
SEE_THROUGH_KINDS = ("glass",)
OPAQUE_GLAZING_KINDS = ("glass_facade",)


def see_through_fault(grammar: "MaterialGrammar") -> str | None:
    """Why ``grammar`` breaks its kind's see-through contract, or None.

    A ``glass`` grammar must blend (``transparency.opacity`` below 1, not a
    ``scissor`` cutout); a ``glass_facade`` grammar must not declare
    transparency at all. Every other kind is unconstrained.
    """
    t = grammar.transparency or {}
    if grammar.kind in SEE_THROUGH_KINDS:
        if not t:
            return (f"grammar '{grammar.id}' is kind '{grammar.kind}', which "
                    f"consumers glaze see-through, and declares no "
                    f"transparency -- it would ship opaque")
        if t.get("alpha_mode", "blend") != "blend":
            return (f"grammar '{grammar.id}' is kind '{grammar.kind}' and asks "
                    f"for alpha_mode '{t.get('alpha_mode')}'; glass blends")
        if not 0.0 < float(t.get("opacity", 0.6)) < 1.0:
            return (f"grammar '{grammar.id}' is kind '{grammar.kind}' with "
                    f"opacity {t.get('opacity')}; see-through glass needs "
                    f"0 < opacity < 1")
    if grammar.kind in OPAQUE_GLAZING_KINDS and t:
        return (f"grammar '{grammar.id}' is kind '{grammar.kind}', the opaque "
                f"glazing of a hollow facade, and declares transparency")
    return None


def build_theme_library(profile, grammars_dir: str, out_dir: str, *,
                        size=None, density: float = DEFAULT_DENSITY,
                        seed: int = DEFAULT_SEED) -> dict:
    """Build a Zoo ``--skins`` library from a *theme profile* — the reproducible
    curation the Level Factory orchestrator needs.

    A theme is a declarative map of one grammar per material kind
    (``profiles/themes/<theme>.json``: ``{"theme": ..., "materials": {kind:
    grammar_id}}``). This writes one ``<kind>_<theme>/`` pack per curated
    material into ``out_dir`` — exactly the layout ``core.skins.find_pack``
    resolves for ``(kind, theme)``. So a building's art pass just needs
    ``build_theme_library(<its theme>)`` then Zoo ``--skins out_dir --theme
    <theme>``; the vocabulary a building wears is entirely the theme profile.

    Raises if a curated grammar's ``kind`` doesn't match the slot it's mapped to
    (a theme can't put a brick grammar in the ``glass`` slot), and if the
    grammar disagrees with what its kind promises about light (see
    ``see_through_fault``).
    """
    if isinstance(profile, str):
        with open(profile, encoding="utf-8") as f:
            profile = json.load(f)
    theme = profile["theme"]
    packs: dict[str, str] = {}
    sizes: dict[str, dict] = {}
    for kind, gram_id in profile.get("materials", {}).items():
        g = MaterialGrammar.load(os.path.join(grammars_dir, f"{gram_id}.json"))
        if g.kind != kind:
            raise ValueError(
                f"theme '{theme}': grammar '{gram_id}' is kind '{g.kind}', "
                f"but the profile maps it to the '{kind}' slot")
        fault = see_through_fault(g)
        if fault:
            raise ValueError(f"theme '{theme}': {fault}")
        pack_dir = os.path.join(out_dir, f"{kind}_{theme}")
        # size=None means "hold texel density flat"; an explicit size is the
        # escape hatch and reproduces the old fixed-size behaviour exactly.
        px = int(size) if size else pack_size_for(g.meters_per_tile, density)
        build_material_pack(g, pack_dir, size=px, seed=seed)
        packs[kind] = f"{kind}_{theme}"
        sizes[kind] = {"size": px, "meters_per_tile": float(g.meters_per_tile),
                       "px_per_m": round(px / float(g.meters_per_tile or 1.0), 1)}
    return {"theme": theme, "out_dir": os.path.abspath(out_dir),
            "packs": packs, "kind_count": len(packs), "sizes": sizes,
            "density": None if size else float(density)}


def _to_u8(arr: np.ndarray) -> np.ndarray:
    return np.rint(np.clip(arr, 0.0, 1.0) * 255.0).astype(np.uint8)


def _write_png(u8: np.ndarray, path: str) -> None:
    """Deterministic PNG write for uint8 L / RGB / RGBA arrays."""
    if u8.ndim == 2:
        mode = "L"
    elif u8.shape[-1] == 3:
        mode = "RGB"
    elif u8.shape[-1] == 4:
        mode = "RGBA"
    else:
        raise ValueError(f"cannot write array of shape {u8.shape}")
    Image.fromarray(u8, mode).save(path, optimize=False)
