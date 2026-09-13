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


# Lot's crosswalk, as Lot 0.69.3's `site_streets` draws it (BAR_WIDTH 0.5,
# BAR_GAP 0.5, EDGE_INSET 0.30): bars 0.5 m wide on a 1.0 m pitch, 9.4 m long
# across Level Factory's 10 m road. Copied as numbers rather than
# imported -- Pixelcoat does not depend on Lot -- so if Lot's bars change
# these go stale, and the test below says what they stood for.
_BAR_W, _BAR_PITCH, _BAR_LEN, _BARS = 0.5, 1.0, 9.4, 6


def _world_alpha(alpha, mpt, x0, y0, w, h, step):
    """The alpha a quad at plan (x0, y0) of size (w, h) m shows under Lot's
    material: `uv1_world_triplanar` at `uv1_scale = 1 / meters_per_tile`, a
    nearest filter, so the tile is looked up at world metres / mpt, wrapped."""
    n = alpha.shape[0]
    xs = x0 + (np.arange(int(round(w / step))) + 0.5) * step
    ys = y0 + (np.arange(int(round(h / step))) + 0.5) * step
    X, Y = np.meshgrid(xs, ys)
    u = np.floor(X / mpt * n).astype(np.int64) % n
    v = np.floor(Y / mpt * n).astype(np.int64) % n
    return alpha[v, u]


def test_no_two_bars_of_a_crosswalk_wear_alike():
    """The walker, on a generated street: 'why the paint on the pavement has
    the look of identical blotches missing?'. Lot projects the pack in WORLD
    space, and at the 0.5 m tile this grammar shipped with a 1.0 m bar pitch is
    two whole tiles -- so every bar sampled the same phase and wore the same
    holes, repeated every 0.5 m down its length. Measured on cold run 9044's
    themed build: 36 of 36 bar pairs within a crosswalk pixel-identical."""
    g = mg.MaterialGrammar.load(os.path.join(_PROFILES, "road_paint_delco.json"))
    size = 256
    alpha = mg.synthesize(g, size=size, seed=1999)["albedo"][..., 3]
    step = g.meters_per_tile / size
    bars = [_world_alpha(alpha, g.meters_per_tile, 3.25 + k * _BAR_PITCH, 1.3,
                         _BAR_W, _BAR_LEN, step) for k in range(_BARS)]
    worn = [float((b == 0).mean()) for b in bars]
    for i in range(_BARS):
        for j in range(i + 1, _BARS):
            assert not np.array_equal(bars[i], bars[j]), (i, j)
    # and the wear itself varies bar to bar, not merely its position
    assert max(worn) - min(worn) > 0.05, worn
    # why it holds: a tile that fits a whole crosswalk's bars at distinct
    # phases, and half a bar's length without wrapping onto itself
    assert g.meters_per_tile >= _BARS * _BAR_PITCH
    assert g.meters_per_tile > _BAR_LEN / 2.0


def test_the_paint_wear_does_not_repeat_down_a_bar():
    g = mg.MaterialGrammar.load(os.path.join(_PROFILES, "road_paint_delco.json"))
    size = 256
    alpha = mg.synthesize(g, size=size, seed=1999)["albedo"][..., 3]
    step = g.meters_per_tile / size
    # the worst bar for this question is one that is worn at all
    for k in range(_BARS):
        bar = _world_alpha(alpha, g.meters_per_tile, 3.25 + k * _BAR_PITCH, 1.3,
                           _BAR_W, _BAR_LEN, step)
        if (bar == 0).any():
            break
    else:
        raise AssertionError("no bar of the crosswalk carries any wear")
    rows = bar.shape[0]
    for lag in range(1, rows // 2):
        assert not np.array_equal(bar[lag:], bar[:-lag]), \
            f"the wear repeats every {lag * step:.2f} m down a {_BAR_LEN} m bar"


def test_a_cutout_coverage_is_the_fraction_kept_whatever_the_field():
    """A fixed `threshold` is not a fraction: the same 0.40 kept 90% of the
    tile at fbm 3 cells x 4 octaves and 23% at 2 x 7 (1024 px, seed 1999).
    `coverage` cuts at the field's own quantile, so a retune of the wear's
    scale does not silently strip or restore the paint."""
    for gen in ({"generator": "fbm", "cells": 3, "octaves": 4},
                {"generator": "fbm", "cells": 2, "octaves": 7},
                {"generator": "worley_f1", "cells": 7}):
        for invert in (False, True):
            g = mg.MaterialGrammar.from_dict({
                "id": "cov", "kind": "road_paint", "base_colors": ["#e6e3dc"],
                "cutout": {"generator": gen, "coverage": 0.85, "invert": invert}})
            a = mg.synthesize(g, size=128, seed=1999)["albedo"][..., 3]
            assert abs(float((a == 255).mean()) - 0.85) < 0.01, (gen, invert)


def test_a_threshold_cutout_is_unchanged():
    """`coverage` is opt-in: a cutout that names only `threshold` keeps the
    exact alpha it had, so foliage and any grammar authored before it are
    byte-identical."""
    spec = {"generator": "worley_f1", "cells": 7}
    g = mg.MaterialGrammar.from_dict({
        "id": "thr", "kind": "foliage", "base_colors": ["#406030"],
        "cutout": {"generator": spec, "threshold": 0.3, "invert": True}})
    a = mg.synthesize(g, size=64, seed=1999)["albedo"][..., 3]
    from pixelcoat.core import procedural_surface as ps
    fld = mg._generator(spec, (64, 64), ps.stream_seed(1999, "cutout"), "cutout")
    assert np.array_equal(a == 255, ~(fld >= 0.3))
