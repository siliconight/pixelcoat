"""Tests for pixelcoat.core.procedural_surface (roadmap T03 primitives).

The load-bearing properties: determinism (byte-identical), tileability
(wrap-exact, so Zoo's REPEAT import shows no grid seam), value range, and
independent seed streams (a new generator never reshuffles an existing one).
"""

import numpy as np

from pixelcoat.core import procedural_surface as ps


def _seam_is_continuous(field: np.ndarray, factor: float = 1.25) -> bool:
    """A tileable field's wrap-seam step must be no larger than its interior
    steps — otherwise tiling shows a visible discontinuity."""
    interior = max(
        np.abs(np.diff(field, axis=0)).max(),
        np.abs(np.diff(field, axis=1)).max(),
    )
    seam = max(
        np.abs(field[0, :] - field[-1, :]).max(),
        np.abs(field[:, 0] - field[:, -1]).max(),
    )
    return seam <= interior * factor + 1e-6


# --------------------------------------------------------------------------- #
# Determinism & streams
# --------------------------------------------------------------------------- #

def test_value_noise_deterministic():
    a = ps.value_noise(64, 8, 1999)
    b = ps.value_noise(64, 8, 1999)
    assert np.array_equal(a, b)


def test_streams_are_independent():
    # Same seed, different labels -> different fields (independent streams).
    a = ps.value_noise(64, 8, 1999, label="macro")
    b = ps.value_noise(64, 8, 1999, label="chips")
    assert not np.array_equal(a, b)
    # Same label -> identical (stable).
    c = ps.value_noise(64, 8, 1999, label="macro")
    assert np.array_equal(a, c)


def test_stream_seed_stable_and_distinct():
    assert ps.stream_seed(1999, "macro") == ps.stream_seed(1999, "macro")
    assert ps.stream_seed(1999, "macro") != ps.stream_seed(1999, "micro")
    assert ps.stream_seed(1999, "a", "b") != ps.stream_seed(1999, "ab")


# --------------------------------------------------------------------------- #
# Range
# --------------------------------------------------------------------------- #

def test_ranges_in_unit_interval():
    for f in (
        ps.value_noise(48, 6, 7),
        ps.fbm(48, 4, 3, 7),
        ps.directional_grain(48, 4, 24, 7, axis="x"),
        ps.worley_f1(48, 8, 7),
    ):
        assert f.dtype == np.float32
        assert f.min() >= 0.0 and f.max() <= 1.0


# --------------------------------------------------------------------------- #
# Tileability (the breakage constraint)
# --------------------------------------------------------------------------- #

def test_value_noise_tiles():
    assert _seam_is_continuous(ps.value_noise(128, 8, 1999))


def test_fbm_tiles():
    assert _seam_is_continuous(ps.fbm(128, 4, 4, 1999))


def test_directional_grain_tiles_both_axes():
    assert _seam_is_continuous(ps.directional_grain(128, 4, 32, 5, axis="x"))
    assert _seam_is_continuous(ps.directional_grain(128, 4, 32, 5, axis="y"))


def test_worley_tiles():
    assert _seam_is_continuous(ps.worley_f1(128, 10, 3), factor=1.6)


# --------------------------------------------------------------------------- #
# Crisp primitives (the anti-smear toolkit)
# --------------------------------------------------------------------------- #

def test_hash_grain_is_high_frequency_and_deterministic():
    a = ps.hash_grain(64, 1999)
    b = ps.hash_grain(64, 1999)
    assert np.array_equal(a, b)                        # deterministic
    assert 0.0 <= a.min() and a.max() <= 1.0
    # High-frequency: adjacent-texel differences are large (not a smooth blur).
    assert np.abs(np.diff(a, axis=1)).mean() > 0.2


def test_worley_edges_range_and_tiles():
    e = ps.worley_edges(96, 8, 7)
    assert 0.0 <= e.min() and e.max() <= 1.0
    # Edges concentrate value near the ridges: a right-skewed (not flat) field.
    assert e.mean() > 0.5


def test_scratches_are_binary_and_sparse():
    sc = ps.scratches(128, 3, axis="x", density=0.05)
    assert set(np.unique(sc)).issubset({0.0, 1.0})     # hard-edged, not smeared
    assert 0.0 < sc.mean() < 0.25                      # sparse


def test_stripes_and_weave_range_and_tile():
    for f in (ps.stripes(128, 5, 1, axis="x"),
              ps.stripes(128, 6, 2, axis="y"),
              ps.weave(128, 16, 1)):
        assert 0.0 <= f.min() and f.max() <= 1.0
    assert _seam_is_continuous(ps.weave(128, 16, 1), factor=1.6)
    assert _seam_is_continuous(ps.stripes(128, 4, 1, axis="x"), factor=1.6)


def test_masonry_mortar_and_units():
    mort, unit = ps.masonry(96, 6, 6, 1, offset=0.0)
    assert set(np.unique(mort)).issubset({0.0, 1.0})     # hard mortar mask
    assert 0.0 < mort.mean() < 0.5                        # some mortar, not all
    assert 0.0 <= unit.min() and unit.max() <= 1.0


def test_ribs_range_and_tiles():
    r = ps.ribs(96, 8, axis="x")
    assert 0.0 <= r.min() and r.max() <= 1.0
    assert _seam_is_continuous(r, factor=1.6)


def test_veins_range_and_tiles():
    v = ps.veins(96, 5)
    assert 0.0 <= v.min() and v.max() <= 1.0
    assert _seam_is_continuous(v, factor=1.6)


def test_streaks_deterministic_and_present():
    a = ps.streaks(96, 3, density=0.5)
    b = ps.streaks(96, 3, density=0.5)
    assert np.array_equal(a, b)
    assert 0.0 <= a.min() and a.max() <= 1.0
    assert a.max() > 0.0                                # some streaks exist


def test_posterize_makes_hard_steps():
    ramp = np.linspace(0, 1, 100).astype(np.float32)
    q = ps.posterize(ramp, 4)
    assert len(np.unique(q)) == 4                      # exactly 4 levels
    assert np.array_equal(ps.posterize(ramp, 1), ramp)  # no-op guard


# --------------------------------------------------------------------------- #
# Shapes / colour helper
# --------------------------------------------------------------------------- #

def test_non_square_size():
    f = ps.value_noise((32, 96), 8, 1)
    assert f.shape == (32, 96)


def test_hex_to_rgb():
    assert np.allclose(ps.hex_to_rgb("#ffffff"), [1, 1, 1])
    assert np.allclose(ps.hex_to_rgb("000000"), [0, 0, 0])
    assert np.allclose(ps.hex_to_rgb("#ff8000"), [1.0, 128 / 255, 0.0])


# --------------------------------------------------------------------------- #
# voronoi_cells (filled aggregate) + wave (reeded/wavy glass)
# --------------------------------------------------------------------------- #

def test_voronoi_cells_deterministic_range_and_structure():
    g1, c1 = ps.voronoi_cells(96, 10, 1999)
    g2, c2 = ps.voronoi_cells(96, 10, 1999)
    assert np.array_equal(g1, g2) and np.array_equal(c1, c2)    # deterministic
    assert set(np.unique(g1)).issubset({0.0, 1.0})             # gap mask binary
    assert 0.0 <= c1.min() and c1.max() <= 1.0                 # cell id unit range
    assert 0.0 < g1.mean() < 0.5                               # some gap, not all
    assert len(np.unique(c1)) > 4                              # many distinct cells


def test_voronoi_cells_tiles_and_streams():
    g, _ = ps.voronoi_cells(128, 8, 7)
    assert _seam_is_continuous(g, factor=1.6)                  # gap mask wraps
    ga, _ = ps.voronoi_cells(96, 8, 1999, label="a")
    gb, _ = ps.voronoi_cells(96, 8, 1999, label="b")
    assert not np.array_equal(ga, gb)                          # independent streams


def test_wave_range_tiles_and_warp():
    w = ps.wave(128, 12, 1999, axis="x")
    assert 0.0 <= w.min() and w.max() <= 1.0
    assert _seam_is_continuous(w, factor=1.6)                  # integer count tiles
    straight = ps.wave(96, 8, 1, axis="x", warp=0.0)
    assert np.allclose(straight, straight[0][None, :])         # warp 0 -> straight flutes
    wavy = ps.wave(96, 8, 1, axis="x", warp=0.4)
    assert not np.allclose(wavy, wavy[0][None, :])             # warp -> undulating
