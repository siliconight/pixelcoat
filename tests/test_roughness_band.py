"""Stepped roughness keeps the band a grammar declares, and bare metal draws no
bars in its reflection.

Measured by Zoo on 0.85.0's vault door, delco_1997 packs, Godot 4.7 GL
Compatibility, 2026-09-14: long black horizontal streaks across every bare
face wider than about half a metre. Replacing only the roughness map with its
flat mean removed them (upper surround vertical luma gradient 22.30 -> 6.80).
The 0.40.0 map held two values, 0.165 and 0.333, 27.2% of the tile at the
glossy one in runs averaging 64.6 px along x and 1.9 px across (128 px tile,
1 m): at metallic 0.9 the glossy rows mirror a dark room.

The cause was the quantiser, not the metal. `synthesize` posterized roughness
on a `1 / (levels - 1)` grid over [0, 1]; every shipped grammar declares a
variation narrower than two of those steps, so the band collapsed to one or
two grid points wherever it happened to fall. These tests hold the band over
every shipped grammar, and hold the bar measure over every grammar a theme
resolves for `metal_bare`. Against 0.40.0 the band test fails 47 of its 53
grammars and both bare-metal tests fail (49 failures); the six that passed
happened to straddle a grid point.
"""

import glob
import json
import os

import numpy as np
import pytest

from pixelcoat.core import material_grammar as mg

_PROFILES = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "profiles"))
_MATERIALS = os.path.join(_PROFILES, "materials")
_THEMES = os.path.join(_PROFILES, "themes")
_SEED = 1999


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _declares_a_response_offset(raw):
    """A motif's ink or a wear pass that names `roughness` offsets part of
    the tile after quantising -- the flock is matte, the crushed pile is
    glossy -- which moves the mean by design, exactly as a chip does.
    `tests/test_club_surfaces.py` checks those offsets land."""
    wear = raw.get("wear") or []
    wear = wear if isinstance(wear, list) else [wear]
    return bool((raw.get("motif") or {}).get("roughness")
                or any(w.get("roughness") for w in wear))


def _stepped_paths():
    """Grammars whose roughness is posterized, varies, and has no chips (a
    chip adds +0.2 over part of the tile, which moves the mean by design)
    and no motif or wear response offset (same reason)."""
    out = []
    for path in sorted(glob.glob(os.path.join(_MATERIALS, "*.json"))):
        raw = _load(path)
        if (raw.get("posterize") and raw.get("emit", {}).get("roughness", True)
                and not raw.get("chips")
                and not _declares_a_response_offset(raw)
                and float((raw.get("roughness") or {}).get("variation", 0.2)) > 0):
            out.append(path)
    return out


def _ids(p):
    return os.path.basename(p)[:-5]


def _rough(g):
    """The roughness map at the size `build_theme_library` writes, in [0, 1]."""
    px = mg.pack_size_for(g.meters_per_tile)
    u8 = mg.synthesize(g, size=px, seed=_SEED)["roughness"]
    return u8, u8.astype(np.float64) / 255.0


def test_there_are_stepped_grammars_to_check():
    """A glob that matches nothing passes every parametrised test below."""
    assert len(_stepped_paths()) >= 50


@pytest.mark.parametrize("path", _stepped_paths(), ids=_ids)
def test_stepped_roughness_keeps_its_band(path):
    """At least three steps, centred on the declared base.

    0.40.0: `metal_painted_neutral` (0.42 +- 0.07) shipped one value, 0.400;
    `rubber_delco` (0.85) shipped 0.749; `asphalt_delco` (0.95) shipped 1.000.
    """
    g = mg.MaterialGrammar.from_dict(_load(path))
    u8, r = _rough(g)
    base = float(g.roughness["base"])
    levels = len(np.unique(u8))
    assert levels >= 3, f"{g.id}: {levels} roughness value(s) {np.unique(u8)}"
    assert abs(r.mean() - base) <= 0.025, \
        f"{g.id}: mean {r.mean():.3f}, declared base {base}"


def _bar_std(r, ky, kx):
    """Std across windows ky px tall x kx px long -- a streak, if ky << kx."""
    h, w = r.shape
    r = r[: h // ky * ky, : w // kx * kx]
    return float(r.reshape(h // ky, ky, w // kx, kx).mean(axis=(1, 3)).std())


def _metal_bare_grammars():
    ids = sorted({_load(p)["materials"]["metal_bare"]
                  for p in glob.glob(os.path.join(_THEMES, "*.json"))
                  if "metal_bare" in _load(p).get("materials", {})})
    assert ids, "no theme resolves metal_bare"
    return ids


@pytest.mark.parametrize("gid", _metal_bare_grammars())
def test_bare_metal_draws_no_bars(gid):
    """No streak half a tile long and 4 px tall stands out of the response.

    Measured at 128 px, seed 1999: 0.40.0 gave 0.0324 across the rows and
    0.0135 down the columns; the band fix alone 0.0207; the shipped grammar
    0.0041. The glossiest 4 px patch (1st percentile) was 0.165 and is now
    0.258 around a 0.28 base.
    """
    g = mg.MaterialGrammar.load(os.path.join(_MATERIALS, gid + ".json"))
    _, r = _rough(g)
    h, w = r.shape
    along = _bar_std(r, 4, w // 2)
    assert along <= 0.008, f"{gid}: bar std {along:.4f} along x"
    box = r[: h // 4 * 4, : w // 4 * 4].reshape(h // 4, 4, w // 4, 4).mean(axis=(1, 3))
    p1 = float(np.percentile(box, 1))
    base = float(g.roughness["base"])
    assert p1 >= base - 0.04, f"{gid}: glossiest 4 px patch {p1:.3f}, base {base}"


@pytest.mark.parametrize("gid", _metal_bare_grammars())
def test_bare_metal_is_not_flat_plastic(gid):
    """The fix for a streak is not a constant. Per-texel variation stays, in
    several steps."""
    g = mg.MaterialGrammar.load(os.path.join(_MATERIALS, gid + ".json"))
    u8, r = _rough(g)
    assert len(np.unique(u8)) >= 5, f"{gid}: {len(np.unique(u8))} values"
    assert r.std() >= 0.015, f"{gid}: std {r.std():.4f}"


def test_grain_zero_is_the_meso_alone():
    """`roughness.grain` is opt-in: a grammar that does not name it gets the
    same map as one that names 0."""
    raw = _load(os.path.join(_MATERIALS, "metal_painted_neutral.json"))
    a = mg.synthesize(mg.MaterialGrammar.from_dict(raw), size=64, seed=_SEED)
    raw["roughness"] = {**raw["roughness"], "grain": 0.0}
    b = mg.synthesize(mg.MaterialGrammar.from_dict(raw), size=64, seed=_SEED)
    assert np.array_equal(a["roughness"], b["roughness"])
    assert np.array_equal(a["albedo"], b["albedo"])


def test_chips_still_add_their_wear_after_quantising():
    """Chips still reach above the stepped band, and nothing falls below it."""
    raw = {"id": "t", "kind": "metal", "posterize": 12,
           "meso": {"generator": "fbm", "cells": 4, "octaves": 2},
           "roughness": {"base": 0.5, "variation": 0.1},
           "chips": {"cells": 6, "amount": 0.3}}
    r = mg.synthesize(mg.MaterialGrammar.from_dict(raw), size=64,
                      seed=_SEED)["roughness"].astype(int)
    vals = np.unique(r)
    assert vals.max() / 255.0 > 0.6 + 0.1 - 0.01   # band top + chip
    assert vals.min() / 255.0 >= 0.4 - 0.005       # band bottom, never below
