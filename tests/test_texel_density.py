"""Texel density: a pack's size is derived from its tile size, not fixed.

Zoo lays down world-metre cube-projected UVs and drives a Mapping node at
1/meters_per_tile (``bpylayer/materials.py``), so a pack's ON-MESH density is
``size * texel / meters_per_tile``. One fixed ``--size`` across a library whose
meters_per_tile spans 1.0-3.0 therefore ships a 3x density spread -- measured on
the shipped library: glass at 512 px/m set into concrete at 171 px/m, on every
building. These tests pin the derivation that holds density flat instead.
"""

import glob
import json
import os

import pytest

from pixelcoat.core import material_grammar as mg

_PROFILES = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "profiles"))
_MATERIALS = os.path.join(_PROFILES, "materials")


def _tile_sizes():
    out = {}
    for path in glob.glob(os.path.join(_MATERIALS, "*.json")):
        with open(path, encoding="utf-8") as f:
            g = json.load(f)
        out[os.path.basename(path)[:-5]] = float(g.get("meters_per_tile") or 1.0)
    return out


def test_pack_size_is_a_power_of_two():
    for mpt in (0.5, 1.0, 1.2, 1.5, 2.0, 2.5, 3.0, 4.0, 7.3):
        size = mg.pack_size_for(mpt)
        assert size & (size - 1) == 0, (mpt, size)


def test_pack_size_is_bounded():
    assert mg.pack_size_for(0.001) == mg.PACK_SIZE_BOUNDS[0]
    assert mg.pack_size_for(1000.0) == mg.PACK_SIZE_BOUNDS[1]


def test_density_across_the_shipped_library_stays_within_two():
    """Two quantities, and they are not the same one.

    Power-of-two rounding caps each pack's DEVIATION from the target at
    sqrt(2). The SPREAD between two packs is therefore bounded by 2x, not
    sqrt(2), because two packs can miss in opposite directions -- which is
    exactly what happens here: flagstone (mpt 2.5) lands at 102 px/m and
    metal_painted_trafficsignal (mpt 1.5) at 171 px/m.

    An earlier draft of this test asserted sqrt(2) on the spread and failed.
    It was right to: the claim was wrong, not the code.

    Measured on the shipped library: spread 1.67x (from 3.00x fixed),
    worst deviation 1.33x.
    """
    got = [mg.pack_size_for(mpt) / mpt for mpt in _tile_sizes().values()]
    assert max(got) / min(got) <= 2.0
    assert max(got) / min(got) == pytest.approx(1.667, abs=0.01)
    for d in got:
        assert 1 / 1.415 <= d / mg.DEFAULT_DENSITY <= 1.415, d


def test_fixed_size_reproduces_the_old_four_times_spread():
    """The regression this replaces, asserted so it cannot come back unnoticed.

    THE NUMBER IS 4.0, NOT THE 3.0 THIS ASSERTED UNTIL 0.23.0, and the history
    is the point rather than the arithmetic. It went stale the day
    `concrete_panel_delco` was authored at `meters_per_tile` 4.0 against a
    library floor of 1.0 -- and that grammar sat UNTRACKED in the working tree
    from 2026-09-06, so the test was red against a file the repo did not have.
    Anyone cloning fresh saw it pass. Committing the grammar is what makes 4.0
    the library's real spread and this assertion true again.

    It is a foil, not a target: the derived-size path above holds the spread to
    1.667x, and this records what fixed 512 px tiles would do instead. A wider
    library makes the foil worse, which is the argument working -- and it did:
    `road_paint_delco` (0.31.0) is authored at 0.5 m per tile, a 0.12 m line
    needing texels, against `concrete_panel_delco`'s 4.0, so the foil is now
    8.0.
    """
    got = [512.0 / mpt for mpt in _tile_sizes().values()]
    assert max(got) / min(got) == pytest.approx(8.0, abs=0.01)


def test_theme_library_derives_per_kind_and_size_overrides(tmp_path):
    profile = os.path.join(_PROFILES, "themes", "rockay_civic.json")
    if not os.path.isfile(profile):
        pytest.skip("rockay_civic profile not present")

    derived = mg.build_theme_library(profile, _MATERIALS,
                                     str(tmp_path / "derived"), size=None)
    assert derived["density"] == mg.DEFAULT_DENSITY
    px = [s["px_per_m"] for s in derived["sizes"].values()]
    assert max(px) / min(px) <= 2.0

    # ...and an explicit size is still the escape hatch, byte-for-byte the old
    # behaviour: every pack the same size, whatever that does to density.
    fixed = mg.build_theme_library(profile, _MATERIALS,
                                   str(tmp_path / "fixed"), size=512)
    assert fixed["density"] is None
    assert {s["size"] for s in fixed["sizes"].values()} == {512}
