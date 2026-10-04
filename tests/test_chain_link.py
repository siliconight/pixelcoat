"""Chain link (Pixelcoat 0.56.0): a woven diamond fabric, alpha-cut."""
import json
import os

import numpy as np

from pixelcoat.core import material_grammar as mg
from pixelcoat.core import procedural_surface as ps

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROFILE = os.path.join(_ROOT, "profiles", "materials", "chain_link_galvanized.json")


def test_the_diamond_mesh_is_two_crossed_wire_families_and_tiles():
    f = ps.diamond_mesh(128, 8, 1999, wire=0.14)
    assert f.shape == (128, 128) and f.dtype == np.float32
    on = f >= 0.5
    # a 16 px diamond period: the wire crosses every diagonal 16 px apart
    assert on[0, 0] and on[16, 16] and on[16, 0] and on[0, 16]
    assert not on[8, 0] and not on[0, 8]                    # the middle of a diamond is open
    # it tiles: the last column and row meet the first
    assert (on[:, 0] == np.roll(on[:, -1], 1)).mean() > 0.9 or (on[:, 0] == on[:, -1]).mean() > 0.6
    frac = float(on.mean())
    assert 0.15 < frac < 0.35, frac


def test_the_fabric_is_a_scissor_cutout_mostly_open():
    g = mg.MaterialGrammar.load(_PROFILE)
    assert g.kind == "chain_link" and g.transparency["alpha_mode"] == "scissor"
    a = mg.synthesize(g, size=256, seed=1999)["albedo"]
    assert a.shape == (256, 256, 4)
    alpha = a[..., 3]
    assert set(np.unique(alpha)) <= {0, 255}
    frac = float((alpha == 255).mean())
    assert 0.15 < frac < 0.35, frac                          # wire, not a sheet
    assert a[..., :3][alpha == 255].mean() > 110              # galvanised, not black


def test_every_level_theme_maps_chain_link_to_it():
    for name in ("delco", "delco_1997"):
        with open(os.path.join(_ROOT, "profiles", "themes", name + ".json"), encoding="utf-8") as fh:
            assert json.load(fh)["materials"]["chain_link"] == "chain_link_galvanized"
