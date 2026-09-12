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


def test_the_foliage_grammar_is_a_leaf_cluster_cutout():
    g = mg.MaterialGrammar.load(os.path.join(_PROFILES, "foliage_delco.json"))
    assert g.kind == "foliage" and g.cutout.get("invert")
    a = mg.synthesize(g, size=96, seed=1999)["albedo"]
    assert a.shape[2] == 4
    frac = float((a[..., 3] == 255).mean())
    assert 0.35 < frac < 0.75, frac                 # clusters with sky between
    assert g.transparency.get("alpha_mode") == "scissor"
    # one tile is one card: nothing survives outside the ellipse, whose
    # centre wraps to the tile's corner (a card's UVs run -0.5..0.5)
    assert g.meters_per_tile == 4.0 and g.cutout["ellipse"]
    n = a.shape[0]
    mid = n // 2
    assert (a[mid - 4:mid + 4, mid - 4:mid + 4, 3] == 0).all()      # the tile's centre is outside
    assert (a[:6, :6, 3] == 255).any() or (a[-6:, -6:, 3] == 255).any()   # the corner is inside


def test_the_paint_wears_in_patches_not_speckle():
    """Cold run 9029's frames: 7-cell worley holes read as speckle. The wear
    is now a low-frequency field, so the paint goes in patches."""
    g = mg.MaterialGrammar.load(os.path.join(_PROFILES, "road_paint_delco.json"))
    assert g.cutout["generator"]["generator"] == "fbm"
    a = mg.synthesize(g, size=64, seed=1999)["albedo"]
    holes = (a[..., 3] == 0)
    assert 0.03 < holes.mean() < 0.3
    # a patch is bigger than a speck: the largest 4-connected hole spans
    # more than a tenth of the tile
    import numpy as np
    seen = np.zeros_like(holes, bool)
    best = 0
    for y in range(holes.shape[0]):
        for x in range(holes.shape[1]):
            if holes[y, x] and not seen[y, x]:
                stack, n = [(y, x)], 0
                seen[y, x] = True
                while stack:
                    cy, cx = stack.pop(); n += 1
                    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        ny, nx = (cy + dy) % 64, (cx + dx) % 64
                        if holes[ny, nx] and not seen[ny, nx]:
                            seen[ny, nx] = True; stack.append((ny, nx))
                best = max(best, n)
    assert best > 64 * 64 * 0.01, best
