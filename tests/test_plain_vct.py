"""A store's vinyl tile floor is one pale colour, polished (0.63.0).

The walker, 2026-10-26, on seed 9205's supermarket under Deli Counter 0.274.0's lamps: "better, it wouldn't be this
tile pattern though...", and of the same floor at roughness 0.12, "but the finish/shine looks right". The comps (the
factory's docs/reference/GROCERY_STORE_COMPS.md) show pale VCT polished until it mirrors the fluorescent runs, one
colour with faint joints. `vct_floor_beige` drew 25 cm tiles in a strong four-shade checker (per-tile tone
variation 0.14, mortar 2 %, roughness 0.35), read in the game as a dark tan checkerboard (the factory's
docs/findings/shiny_floor/).

FAILS ON 0.62.0: the rendered albedo's mean is 204.7 and its spread 14.1 (0.63.0: 216.0 and 5.8), the tiles are
25 cm, and the roughness base is 0.35.

Run:  python -m pytest tests/test_plain_vct.py
"""
import os

import numpy as np

from pixelcoat.core import material_grammar as mg

_PROFILE = os.path.join(os.path.dirname(__file__), "..", "profiles", "materials", "vct_floor_beige.json")
#: 12 inches: a VCT tile's size, the module the 1990s commercial floor was laid in.
VCT_TILE_M = 0.3048


def _albedo():
    g = mg.MaterialGrammar.load(_PROFILE)
    return g, mg.synthesize(g, size=256)["albedo"].astype(np.float64).mean(axis=2)


def test_it_is_pale_and_one_colour():
    _g, a = _albedo()
    assert a.mean() >= 210.0, a.mean()
    assert a.std() <= 10.0, a.std()


def test_its_tiles_are_twelve_inches_and_barely_differ():
    g, a = _albedo()
    m = g.masonry
    assert abs(g.meters_per_tile / m["cols"] - VCT_TILE_M) < 0.002
    assert abs(g.meters_per_tile / m["rows"] - VCT_TILE_M) < 0.002
    # the tile-to-tile tone, measured: each tile's mean, inside its joints
    n = m["rows"]
    s = a.shape[0] // n
    means = [a[i * s + 4:(i + 1) * s - 4, j * s + 4:(j + 1) * s - 4].mean() for i in range(n) for j in range(n)]
    assert max(means) - min(means) <= 8.0, (min(means), max(means))


def test_it_is_polished():
    g, _a = _albedo()
    assert g.roughness["base"] <= 0.15, g.roughness
