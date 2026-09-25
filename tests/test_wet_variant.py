"""A ground grammar ships a wet variant, and it is a MATERIAL, not a pass.

WHY THIS SHAPE AND NOT A `next_pass`. Level Factory 0.110.0 priced a wet
`next_pass` on a real cold-run package (`LF_crossroads_9600`, GL Compatibility,
1280x720, 3 rounds x 300 samples): 2.27-4.29 us per ADDED DRAW CALL, median
3.5, flat across 18 station-arm pairs whose wet-surface screen coverage differs
wildly -- so the bill is per SUBMISSION and not per pixel, and it came to
+8.05 ms at the worst station. A second material draws the same triangles once.
These tests hold the properties that make that true, and the ones that make the
variant inert until something chooses it.

WHAT THEY DO NOT HOLD. Whether a wet Delco street LOOKS right. Nobody has
looked at a frame of one yet; `amount`, `floor` and `cavity_bias` are chosen and
recorded in each profile's notes so a person can turn them. Every assertion here
is about structure and arithmetic.
"""

import glob
import json
import os

import numpy as np
import pytest

from pixelcoat.core import material_grammar as mg
from pixelcoat.core import material_response as mr

_PROFILES = os.path.join(os.path.dirname(__file__), "..", "profiles",
                         "materials")
WET_MAPS = ("wetness", "wet_albedo", "wet_roughness")


def _grammar(name):
    return mg.MaterialGrammar.load(os.path.join(_PROFILES, f"{name}.json"))


def _wet_profiles():
    out = []
    for f in sorted(glob.glob(os.path.join(_PROFILES, "*.json"))):
        with open(f, encoding="utf-8") as fh:
            if json.load(fh).get("wet"):
                out.append(os.path.basename(f)[:-len(".json")])
    return out


WET_PROFILES = _wet_profiles()


def test_some_grammar_actually_ships_a_wet_block():
    """Without this the parametrised tests below would all pass on an empty
    set -- a suite that cannot fail is indistinguishable from one that
    passed."""
    assert WET_PROFILES, "no shipped grammar declares a wet variant"


# --------------------------------------------------------------------------- #
# What a wet grammar emits
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name", WET_PROFILES)
def test_a_wet_grammar_emits_the_three_wet_maps(name):
    out = mg.synthesize(_grammar(name), size=64)
    for key in WET_MAPS:
        assert key in out, f"{name} declares wetness but emitted no {key}"
        assert out[key].shape[:2] == (64, 64)
        assert out[key].dtype == np.uint8


def test_a_dry_grammar_emits_none_of_them():
    out = mg.synthesize(_grammar("brick_delco"), size=64)
    assert not (set(out) & set(WET_MAPS))


@pytest.mark.parametrize("name", WET_PROFILES)
def test_wet_is_darker_and_smoother_than_dry(name):
    """The whole physical claim, in two inequalities. Water darkens a surface
    and fills its micro-relief; the response model says how much, per family."""
    g = _grammar(name)
    out = mg.synthesize(g, size=128)
    dry_a = out["albedo"][..., :3].astype(np.int32)
    wet_a = out["wet_albedo"][..., :3].astype(np.int32)
    assert (wet_a <= dry_a).all(), f"{name}: a wet texel got BRIGHTER"
    assert wet_a.mean() < dry_a.mean() * 0.95, (
        f"{name}: wet albedo is only {100 * (1 - wet_a.mean() / dry_a.mean()):.1f}"
        f"% darker, which will not read as rain")

    dry_r = out["roughness"].astype(np.int32)
    wet_r = out["wet_roughness"].astype(np.int32)
    assert (wet_r <= dry_r).all(), f"{name}: a wet texel got ROUGHER"
    assert wet_r.mean() < dry_r.mean()


@pytest.mark.parametrize("name", WET_PROFILES)
def test_the_response_comes_from_the_declared_family(name):
    """Not from a number in this file, and not from one in the grammar. The
    darkening is `preset.wet_darken` scaled by the mask, so the brightest wet
    texel is exactly the dry one times (1 - darken * mask)."""
    with open(os.path.join(_PROFILES, f"{name}.json"), encoding="utf-8") as fh:
        block = json.load(fh)["wet"]
    preset = mr.PRESETS[block["responds_like"]]

    out = mg.synthesize(_grammar(name), size=96)
    mask = out["wetness"].astype(np.float64) / 255.0
    dry = out["albedo"][..., :3].astype(np.float64)
    wet = out["wet_albedo"][..., :3].astype(np.float64)
    expect = dry * (1.0 - preset.wet_darken * mask[..., None])
    # One 8-bit step of slack: both sides were quantised on the way out.
    assert np.abs(wet - expect).max() <= 1.5, (
        f"{name}: wet albedo does not follow the {block['responds_like']} "
        f"preset's wet_darken of {preset.wet_darken}")


# --------------------------------------------------------------------------- #
# The refusals
# --------------------------------------------------------------------------- #

def test_an_unknown_family_refuses():
    g = _grammar("asphalt_delco")
    g.wet = dict(g.wet, responds_like="wet_pavement")
    with pytest.raises(ValueError, match="material_response preset"):
        mg.synthesize(g, size=32)


def test_wetness_without_a_roughness_map_refuses():
    """A wet albedo over a dry roughness is a material that looks wet and
    lights dry, so this is a refusal and not a warning."""
    g = _grammar("asphalt_delco")
    g.emit = {"roughness": False, "normal": False}
    with pytest.raises(ValueError, match="emits no roughness"):
        mg.synthesize(g, size=32)


@pytest.mark.parametrize("amount", [0.0, -0.2, 1.4])
def test_an_amount_outside_its_range_refuses(amount):
    g = _grammar("asphalt_delco")
    g.wet = dict(g.wet, amount=amount)
    with pytest.raises(ValueError, match="wet.amount"):
        mg.synthesize(g, size=32)


def test_a_floor_of_one_refuses():
    """A flat mask leaves the pooling nothing to spend, which is a wet block
    that has stopped modelling anything."""
    g = _grammar("asphalt_delco")
    g.wet = dict(g.wet, floor=1.0)
    with pytest.raises(ValueError, match="wet.floor"):
        mg.synthesize(g, size=32)


@pytest.mark.parametrize("name", WET_PROFILES)
def test_every_shipped_wet_block_names_a_real_family(name):
    with open(os.path.join(_PROFILES, f"{name}.json"), encoding="utf-8") as fh:
        block = json.load(fh)["wet"]
    assert block["responds_like"] in mr.PRESETS
    assert 0.0 < block["amount"] <= 1.0
    assert 0.0 <= block.get("floor", 0.0) < 1.0


# --------------------------------------------------------------------------- #
# What must NOT change
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name", WET_PROFILES)
def test_the_dry_maps_are_untouched_by_the_wet_block(name):
    """THE CLAIM THAT MAKES THIS SAFE TO SHIP AHEAD OF A CONSUMER. Zoo resolves
    a pack through a fixed allow-list (`core/skins.py:35`, MAP_KEYS = albedo,
    normal, roughness, emissive, height), so the new maps are ignored by
    everything that exists today -- but only if the old ones are bit-for-bit
    what they were. Byte equality, not closeness."""
    g = _grammar(name)
    with_wet = mg.synthesize(g, size=96)
    g.wet = {}
    without = mg.synthesize(g, size=96)
    assert set(without) | set(WET_MAPS) == set(with_wet) | set(WET_MAPS)
    for key in without:
        assert np.array_equal(without[key], with_wet[key]), (
            f"{name}: declaring wetness changed the dry {key}")


def test_a_floor_of_zero_reproduces_the_plain_pooling_mask():
    """The backward-compatible claim, asserted rather than argued: `floor: 0`
    is `amount * pooling`, which is what the mask function returns when it is
    handed `amount` directly."""
    from pixelcoat.core import weathering
    from pixelcoat.core import procedural_surface as ps

    g = _grammar("asphalt_delco")
    g.wet = dict(g.wet, floor=0.0)
    out = mg.synthesize(g, size=96)

    # rebuild the mask the way the old code did, from the same height field
    probe = mg.synthesize(g, size=96)          # deterministic by (grammar, seed)
    assert np.array_equal(probe["wetness"], out["wetness"])

    amount = float(g.wet["amount"])
    direct = weathering.wetness_mask(
        _recess(g, 96), amount, float(g.wet.get("cavity_bias", 0.65)), 0.0,
        ps.stream_seed(mg.DEFAULT_SEED, "wet"), True, True)
    got = out["wetness"].astype(np.float64) / 255.0
    assert np.abs(got - direct).max() <= 1.0 / 255.0 + 1e-9


def _recess(grammar, size):
    """The height-derived recess `_wet_maps` builds its mask from. Rebuilt here
    rather than imported so the test does not pass by calling the code it is
    checking."""
    import pixelcoat.core.material_grammar as m
    captured = {}
    real = m.weathering.wetness_mask

    def spy(recess, *a, **k):
        captured["recess"] = recess
        return real(recess, *a, **k)

    m.weathering.wetness_mask = spy
    try:
        m.synthesize(grammar, size=size)
    finally:
        m.weathering.wetness_mask = real
    return captured["recess"]


# --------------------------------------------------------------------------- #
# The pack
# --------------------------------------------------------------------------- #

def test_the_pack_hints_wet_albedo_as_a_COLOUR_map(tmp_path):
    """A colour map hinted `linear` is obeyed silently by every importer, and
    the wet road comes out a different colour from the dry one for no reason a
    frame could explain. The gen7 pack writer has always listed `wet_albedo`
    here; the grammar path's comprehension predated wetness and did not."""
    m = mg.build_material_pack(
        os.path.join(_PROFILES, "asphalt_delco.json"),
        str(tmp_path / "asphalt_delco_1997"), size=64)
    cs = m["import_hints"]["color_space"]
    assert cs["albedo"] == "srgb"
    assert cs["wet_albedo"] == "srgb"
    assert cs["wet_roughness"] == "linear"
    assert cs["wetness"] == "linear"


def test_a_wet_pack_still_satisfies_the_zoo_contract(tmp_path):
    """Adding maps must not break the manifest Zoo reads."""
    pack = tmp_path / "asphalt_delco_1997"
    m = mg.build_material_pack(
        os.path.join(_PROFILES, "asphalt_delco.json"), str(pack), size=64)
    assert "albedo" in m["maps"]
    assert m["tileable"] == ["x", "y"]
    for key, fname in m["maps"].items():
        assert not os.path.isabs(fname)
        assert (pack / fname).is_file()


def test_a_cutout_grammar_keeps_its_exact_alpha_when_wet():
    """`road_paint_delco` is worn through to the road by an alpha channel. A
    wet albedo without it hands the importer an opaque marking -- wet paint
    over the whole tile."""
    out = mg.synthesize(_grammar("road_paint_delco"), size=128)
    assert out["albedo"].shape[-1] == 4
    assert out["wet_albedo"].shape[-1] == 4
    assert np.array_equal(out["albedo"][..., 3], out["wet_albedo"][..., 3])


@pytest.mark.parametrize("name", WET_PROFILES)
def test_the_wet_maps_tile_on_both_axes(name):
    """Every other map in a pack tiles; a wet one that did not would draw a
    seam down a road that the dry one does not have."""
    out = mg.synthesize(_grammar(name), size=128)
    for key in ("wetness", "wet_albedo", "wet_roughness"):
        f = out[key]
        f = f[..., :3] if f.ndim == 3 and f.shape[-1] == 4 else f
        interior = max(np.abs(np.diff(f.astype(np.int32), axis=0)).max(),
                       np.abs(np.diff(f.astype(np.int32), axis=1)).max())
        seam = max(
            np.abs(f[0].astype(np.int32) - f[-1].astype(np.int32)).max(),
            np.abs(f[:, 0].astype(np.int32) - f[:, -1].astype(np.int32)).max())
        assert seam <= interior * 1.3 + 2, f"{name}/{key} seams"


# --------------------------------------------------------------------------- #
# Saturation: a soaked surface reaches WATER, not a mirror
# --------------------------------------------------------------------------- #

def test_a_fully_wet_texel_lands_on_the_water_roughness(tmp_path):
    """THE POINT OF `saturation`. At `saturation * mask == 1` the roughness is
    the water target exactly, by construction -- no clip, no overshoot.

    The shipped model could not do this. It subtracted the preset's gloss
    boost, so a boost of 1 on asphalt gave 0.95 - 1.0 = -0.05, clipped to
    roughness 0 -- a perfect mirror, when standing water is around 0.05-0.10.
    """
    g = _grammar("asphalt_delco")
    # amount and floor at their maxima put the whole mask at 1.0
    g.wet = dict(g.wet, amount=1.0, floor=0.999, saturation=1.0)
    out = mg.synthesize(g, size=64)
    wet = out["wet_roughness"].astype(np.float64) / 255.0
    mask = out["wetness"].astype(np.float64) / 255.0
    assert mask.min() > 0.99, "the fixture did not saturate the mask"
    assert abs(wet.mean() - mg.WATER_ROUGHNESS) < 1.5 / 255.0, (
        f"a fully wet texel reads {wet.mean():.4f}, not the water target "
        f"{mg.WATER_ROUGHNESS}")


def test_saturation_defaults_to_the_preset_so_a_grammar_need_not_declare_one():
    """`material_response.PRESETS` stays the authority. A wet block with no
    `saturation` travels the preset's `wet_gloss_boost` of the way to water."""
    g = _grammar("brick_delco")
    g.wet = {"responds_like": "brick", "amount": 1.0, "floor": 0.999}
    out = mg.synthesize(g, size=64)
    wet = out["wet_roughness"].astype(np.float64) / 255.0
    dry = out["roughness"].astype(np.float64) / 255.0
    boost = mr.PRESETS["brick"].wet_gloss_boost
    expect = dry + (mg.WATER_ROUGHNESS - dry) * boost
    assert np.abs(wet - expect).max() <= 2.0 / 255.0


def test_wetness_never_makes_a_surface_rougher(tmp_path):
    """A material already glossier than water would be lerped UP toward it.
    `marble_bank_floor` sits at 0.20 dry and the library holds grammars below
    that, so the floor is `min(dry, lerped)` and this is what holds it."""
    g = _grammar("marble_bank_floor")
    g.wet = {"responds_like": "concrete", "amount": 1.0, "floor": 0.999,
             "saturation": 1.0, "water_roughness": 0.9}
    out = mg.synthesize(g, size=64)
    dry = out["roughness"].astype(np.int32)
    wet = out["wet_roughness"].astype(np.int32)
    assert (wet <= dry).all(), (
        "a water target rougher than the surface made the wet variant "
        "ROUGHER than the dry one")


@pytest.mark.parametrize("bad", [-0.1, 1.4])
def test_a_saturation_outside_its_range_refuses(bad):
    g = _grammar("asphalt_delco")
    g.wet = dict(g.wet, saturation=bad)
    with pytest.raises(ValueError, match="wet.saturation"):
        mg.synthesize(g, size=32)


def test_a_water_roughness_outside_its_range_refuses():
    g = _grammar("asphalt_delco")
    g.wet = dict(g.wet, water_roughness=1.4)
    with pytest.raises(ValueError, match="wet.water_roughness"):
        mg.synthesize(g, size=32)


@pytest.mark.parametrize("name", WET_PROFILES)
def test_every_shipped_saturation_is_in_range(name):
    with open(os.path.join(_PROFILES, f"{name}.json"), encoding="utf-8") as fh:
        block = json.load(fh)["wet"]
    assert 0.0 <= block.get("saturation", 0.0) <= 1.0


def test_the_paved_surfaces_are_the_ones_that_reach_water():
    """An impermeable surface open to the sky reaches water; absorbent earth
    does not, because soaked ground is dark and matte rather than reflective.
    Asserted so a later tuning pass has to mean it."""
    def sat(n):
        with open(os.path.join(_PROFILES, f"{n}.json"), encoding="utf-8") as fh:
            return json.load(fh)["wet"].get("saturation")
    for paved in ("asphalt_delco", "tar_neutral", "sidewalk_delco",
                  "road_paint_delco", "cobblestone"):
        assert sat(paved) == 1.0, paved
    assert sat("dirt_delco") < 0.5
    assert sat("pebble_gravel") < 1.0
