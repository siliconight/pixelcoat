"""Tests for pixelcoat.core.uv_dilation (roadmap Technique T06).

Correctness of the exact EDT is proven against an O(N^2) brute-force nearest
-seed reference. The dilation behaviour is checked against the roadmap's own
proof test: a red island two gutters from a green island must never produce a
red-green averaged texel across the ownership boundary.
"""

import numpy as np
import pytest

from pixelcoat.core import uv_dilation as uvd


# ---------------------------------------------------------------------------
# Brute-force reference
# ---------------------------------------------------------------------------

def _brute_nearest(mask, wrap_x=False, wrap_y=False):
    h, w = mask.shape
    seeds = np.argwhere(mask)
    dist2 = np.full((h, w), np.inf)
    for y in range(h):
        for x in range(w):
            best = np.inf
            for (sy, sx) in seeds:
                dy = abs(y - sy)
                dx = abs(x - sx)
                if wrap_y:
                    dy = min(dy, h - dy)
                if wrap_x:
                    dx = min(dx, w - dx)
                dd = dy * dy + dx * dx
                if dd < best:
                    best = dd
            dist2[y, x] = best
    return dist2


# ---------------------------------------------------------------------------
# EDT correctness
# ---------------------------------------------------------------------------

def test_edt_matches_bruteforce_planar():
    rng = np.random.default_rng(1999)
    mask = rng.random((17, 23)) < 0.12
    mask[0, 0] = True  # guarantee at least one seed
    dist2, ny, nx = uvd.edt_nearest_indices(mask)
    ref = _brute_nearest(mask)
    assert np.allclose(dist2, ref)
    # Every returned source index must itself be a seed at the reported distance.
    for y in range(mask.shape[0]):
        for x in range(mask.shape[1]):
            sy, sx = ny[y, x], nx[y, x]
            assert mask[sy, sx]
            d = (y - sy) ** 2 + (x - sx) ** 2
            # planar (non-wrapped) source distance equals the transform distance
            assert d == pytest.approx(dist2[y, x])


def test_edt_matches_bruteforce_wrapped():
    rng = np.random.default_rng(7)
    mask = rng.random((16, 16)) < 0.10
    mask[5, 5] = True
    dist2, ny, nx = uvd.edt_nearest_indices(mask, wrap_x=True, wrap_y=True)
    ref = _brute_nearest(mask, wrap_x=True, wrap_y=True)
    assert np.allclose(dist2, ref)


def test_edt_seed_texels_have_zero_distance():
    mask = np.zeros((8, 8), dtype=bool)
    mask[2, 3] = True
    mask[6, 1] = True
    dist2, ny, nx = uvd.edt_nearest_indices(mask)
    assert dist2[2, 3] == 0.0
    assert dist2[6, 1] == 0.0
    assert (ny[2, 3], nx[2, 3]) == (2, 3)


def test_edt_empty_mask_is_infinite():
    mask = np.zeros((5, 5), dtype=bool)
    dist2, ny, nx = uvd.edt_nearest_indices(mask)
    assert np.isinf(dist2).all()


# ---------------------------------------------------------------------------
# Island-aware dilation — the roadmap proof test
# ---------------------------------------------------------------------------

def _two_island_fixture():
    """A 1x2-texel red island and green island separated by empty gutter."""
    h, w = 5, 12
    img = np.zeros((h, w, 3), dtype=np.uint8)
    cov = np.zeros((h, w), dtype=bool)
    ids = np.zeros((h, w), dtype=np.int64)

    red = (220, 30, 30)
    green = (30, 210, 40)
    # Red island: columns 1-2. Green island: columns 9-10. Gutter between.
    img[2, 1:3] = red
    cov[2, 1:3] = True
    ids[2, 1:3] = 1
    img[2, 9:11] = green
    cov[2, 9:11] = True
    ids[2, 9:11] = 2
    return img, cov, ids, red, green


def test_no_cross_island_averaging():
    img, cov, ids, red, green = _two_island_fixture()
    out, owner = uvd.dilate_islands(img, cov, ids, radius=8)

    # Every filled texel must be exactly red or green — never a blend of both.
    filled = (~cov) & (owner >= 0)
    ys, xs = np.nonzero(filled)
    for y, x in zip(ys, xs):
        px = tuple(int(c) for c in out[y, x])
        assert px in (red, green), f"blended texel {px} at ({y},{x})"
        # Colour and recorded owner agree.
        assert owner[y, x] == (1 if px == red else 2)


def test_ownership_follows_nearest_island():
    img, cov, ids, red, green = _two_island_fixture()
    out, owner = uvd.dilate_islands(img, cov, ids, radius=8)
    # A texel just right of the red island (col 4) is nearer red than green.
    assert owner[2, 4] == 1
    # A texel just left of the green island (col 7) is nearer green.
    assert owner[2, 7] == 2


def test_radius_is_respected():
    img, cov, ids, _, _ = _two_island_fixture()
    out, owner = uvd.dilate_islands(img, cov, ids, radius=1)
    # Column 5 is >1 texel from either island: must stay untouched (owner -1).
    assert owner[2, 5] == -1
    assert tuple(out[2, 5]) == (0, 0, 0)


def test_determinism_byte_identical():
    img, cov, ids, _, _ = _two_island_fixture()
    a_img, a_own = uvd.dilate_islands(img, cov, ids, radius=6)
    b_img, b_own = uvd.dilate_islands(img, cov, ids, radius=6)
    assert np.array_equal(a_img, b_img)
    assert np.array_equal(a_own, b_own)


def test_covered_texels_are_never_modified():
    img, cov, ids, red, green = _two_island_fixture()
    out, owner = uvd.dilate_islands(img, cov, ids, radius=8)
    assert np.array_equal(out[cov], img[cov])
    assert np.array_equal(owner[cov], ids[cov])


def test_alpha_gutter_default_keeps_transparent():
    h, w = 3, 8
    img = np.zeros((h, w, 4), dtype=np.uint8)
    cov = np.zeros((h, w), dtype=bool)
    ids = np.zeros((h, w), dtype=np.int64)
    img[1, 1] = (200, 100, 50, 255)
    cov[1, 1] = True
    ids[1, 1] = 1

    out, _ = uvd.dilate_islands(img, cov, ids, radius=3)
    # A filled neighbour extrudes RGB but keeps alpha 0 by default.
    assert tuple(out[1, 2][:3]) == (200, 100, 50)
    assert out[1, 2][3] == 0

    out_a, _ = uvd.dilate_islands(img, cov, ids, radius=3, alpha_gutter=True)
    assert out_a[1, 2][3] == 255


def test_wrap_fills_across_seam():
    h, w = 4, 10
    img = np.zeros((h, w, 3), dtype=np.uint8)
    cov = np.zeros((h, w), dtype=bool)
    ids = np.zeros((h, w), dtype=np.int64)
    # Island at the far-right column; with wrap_x its colour should reach col 0.
    img[1, 9] = (10, 20, 250)
    cov[1, 9] = True
    ids[1, 9] = 5

    out, owner = uvd.dilate_islands(img, cov, ids, radius=2, wrap_x=True)
    assert owner[1, 0] == 5
    assert tuple(out[1, 0]) == (10, 20, 250)
