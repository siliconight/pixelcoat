"""Road paint: a kind whose albedo carries a cutout alpha (roadmap 153 /
152 step 2), so Lot's marking quads wear a decal worn through to the road.
"""
import os

import numpy as np

from pixelcoat.core import material_grammar as mg

_PROFILES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "profiles", "materials")


def test_a_cutout_grammar_writes_an_rgba_albedo_with_a_hard_alpha():
    g = mg.MaterialGrammar.load(os.path.join(_PROFILES, "road_paint_delco.json"))
    assert g.kind == "road_paint" and g.cutout
    out = mg.synthesize(g, size=96, seed=1999)
    a = out["albedo"]
    assert a.shape == (96, 96, 4) and a.dtype == np.uint8
    alpha = a[..., 3]
    assert set(np.unique(alpha)) <= {0, 255}, "a cutout is on or off"
    frac = float((alpha == 255).mean())
    assert 0.5 < frac < 0.98, frac                 # paint mostly there, worn in places
    # the paint itself is light
    assert a[..., :3][alpha == 255].mean() > 180


def test_a_cutout_pack_asks_for_alpha_scissor(tmp_path):
    g = mg.MaterialGrammar.load(os.path.join(_PROFILES, "road_paint_delco.json"))
    man = mg.build_material_pack(g, str(tmp_path / "paint"), size=48)
    assert man["import_hints"]["transparency"]["alpha_mode"] == "scissor"
    from PIL import Image
    im = Image.open(tmp_path / "paint" / man["maps"]["albedo"])
    assert im.mode == "RGBA"


def test_a_grammar_without_a_cutout_is_unchanged():
    g = mg.MaterialGrammar.from_dict({"id": "plain", "kind": "concrete",
                                      "base_colors": ["#808080"]})
    assert mg.synthesize(g, size=32)["albedo"].shape == (32, 32, 3)
