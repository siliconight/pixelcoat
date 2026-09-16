"""The card-shop surfaces: two grooved panels, a drab carpet, and the theme.

The walker, 2026-09-15, with nine photos of trading-card shops
(`docs/SET_DRESSING_REFERENCES.md`, "The walker's trading card shop
references"). The Pixelcoat line there is one sentence: "wood panelling for
the lower walls, slatwall, and a tournament carpet."

What is held here, and why each clause exists:

- THE PITCH IS THE POINT. A slatwall at any spacing other than 3 in on centre
  is not slatwall, and panelling without a score line at a sheet pitch is a
  brown wall. Both are asserted in METRES against the real dimension, not in
  cells, because `count` and `meters_per_tile` can drift together and leave
  the grammar looking unchanged.
- THE DIRT IS IN THE GROOVE. `slatwall_retail` gets it by drawing its first
  wear mask from `ribs` at the meso stripes' own count and axis: a rib peaks
  where a stripe seam falls, because both are keyed on the band fraction
  reaching zero. That coincidence is load-bearing and invisible from either
  file, so it is measured here -- if `stripes` ever moves its seam or `ribs`
  its phase, the grime silently lands on the face instead.
- A GROOVE IS STRUCTURE AND ROADMAP 140 CANNOT TELL IT FROM NOISE. The two
  numbers that gate a skin (luminance spread and neighbour correlation) read
  slatwall at std 18.6 / ac1 0.43 for the whole tile, and that number is
  almost entirely the 16 hard groove rows. The face alone is std 4.8 /
  ac1 0.39, and the face is what "is this static?" is asking about, so the
  clause below splits them and checks both.
- THE MAP COUNT IS A PERFORMANCE BUDGET. Every frame is spent on somebody
  else's machine: two maps at the library's density is 170.7 KiB of RGBA8
  plus mips for each panel and 682.7 KiB for the carpet. A normal map would
  add a third sampler and a third again of that, and is inert on the default
  per-vertex path (`core/material_grammar` module docstring). A future edit
  that adds one should have to argue with a test.
"""

import glob
import json
import os

import numpy as np
import pytest

from pixelcoat.core import material_grammar as mg
from pixelcoat.core import procedural_surface as ps
from tools import art_standard_audit as audit

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_MATERIALS = os.path.join(_ROOT, "profiles", "materials")
_THEMES = os.path.join(_ROOT, "profiles", "themes")
_SEED = 1999
_INCH = 0.0254

CARD_SHOP = ("wood_panel_delco", "slatwall_retail", "carpet_tournament")
SLOTS = {"wood_panel": "wood_panel_delco",
         "slatwall": "slatwall_retail",
         "carpet": "carpet_tournament"}
#: (grammar, the axis its grooves run across, the real pitch it claims)
GROOVED = (("wood_panel_delco", "x", 8 * _INCH),
           ("slatwall_retail", "y", 3 * _INCH))


def _raw(gid):
    with open(os.path.join(_MATERIALS, gid + ".json"), encoding="utf-8") as f:
        return json.load(f)


def _load(gid):
    return mg.MaterialGrammar.load(os.path.join(_MATERIALS, gid + ".json"))


def _theme(name):
    with open(os.path.join(_THEMES, name + ".json"), encoding="utf-8") as f:
        return json.load(f)


def _synth(gid):
    g = _load(gid)
    px = mg.pack_size_for(g.meters_per_tile)
    return g, px, mg.synthesize(g, size=px, seed=_SEED)


def _luma(albedo_u8):
    a = albedo_u8[..., :3].astype(np.float64)
    return 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]


def _spread_and_correlation(albedo_u8):
    """Roadmap 140's two numbers: luminance spread, neighbour correlation."""
    lum = _luma(albedo_u8)
    d = lum - lum.mean()
    var = (d * d).mean()
    ax = (d[:, :-1] * d[:, 1:]).mean() / var
    ay = (d[:-1, :] * d[1:, :]).mean() / var
    return float(lum.std()), float((ax + ay) / 2.0)


def _band_fraction(px, count):
    """Where each line of the tile falls inside its band, 0 at the seam.

    The same expression `procedural_surface.stripes` uses, so a change to
    how a band is laid out moves this with it rather than past it.
    """
    return (np.arange(px, dtype=np.float64) / px * count) % 1.0


def _wrap_no_worse_than_interior(arr):
    a = arr.astype(np.int32)
    if a.ndim == 2:
        a = a[..., None]
    rows = np.abs(np.diff(a, axis=0)).mean(axis=(1, 2))
    cols = np.abs(np.diff(a, axis=1)).mean(axis=(0, 2))
    wy = float(np.abs(a[0] - a[-1]).mean())
    wx = float(np.abs(a[:, 0] - a[:, -1]).mean())
    return (wy, float(rows.max())), (wx, float(cols.max()))


# --------------------------------------------------------------------------- #
# The grammars
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("gid", CARD_SHOP)
def test_card_shop_grammar_builds_deterministically(gid):
    g, px, a = _synth(gid)
    b = mg.synthesize(g, size=px, seed=_SEED)
    assert set(a) == set(b)
    for k in a:
        assert np.array_equal(a[k], b[k]), k


@pytest.mark.parametrize("gid", CARD_SHOP)
def test_card_shop_grammar_tiles_on_every_map(gid):
    _, _, s = _synth(gid)
    for key, arr in s.items():
        for wrap, worst in _wrap_no_worse_than_interior(arr):
            assert wrap <= worst + 1e-6, (gid, key, wrap, worst)


@pytest.mark.parametrize("gid", CARD_SHOP)
def test_card_shop_grammar_meets_the_art_standard_it_can(gid):
    """Value, crush, blow, roughness and emissive. Chroma is left to the
    report: `wood_panel_delco` is a brown wall at 0.049 against a 0.030
    budget, which is the whole wood family's position (hardwood_plank 0.074,
    wood_delco 0.070, wood_stained_delco 0.047) and `carpet_delco` is the
    standing lesson about which of the two wins."""
    g = _load(gid)
    row = audit.measure(g, mg.synthesize(g, size=256, seed=_SEED))
    b = audit.ENV_BUDGET
    assert row["crushed_frac"] == 0.0, row["crushed_frac"]
    assert row["blown_frac"] == 0.0, row["blown_frac"]
    assert row["value_range"] <= b["value_range"], row["value_range"]
    assert row["rough_mean"] >= b["rough_mean_min"], row["rough_mean"]
    assert not row["emissive"]


@pytest.mark.parametrize("gid", CARD_SHOP)
def test_card_shop_grammar_emits_albedo_and_roughness_only(gid):
    """The performance clause. A normal map is a third sampler and a third
    again of the pack's bytes, and it is inert on the default per-vertex
    path -- adding one is a decision with a number attached, not a tweak."""
    g, px, s = _synth(gid)
    assert set(s) == {"albedo", "roughness"}, sorted(s)
    vram = sum(int(round(a.shape[0] * a.shape[1] * 4 * 4 / 3))
               for a in s.values())
    assert vram / 1024 == pytest.approx(
        {128: 170.7, 256: 682.7}[px], abs=0.1), (gid, px, vram)


def test_the_two_panels_are_128_px_and_the_carpet_256():
    """The size `build_theme_library` picks at the library's 128 px/m. A
    grammar that moves its meters_per_tile moves its memory with it."""
    assert mg.pack_size_for(_load("wood_panel_delco").meters_per_tile) == 128
    assert mg.pack_size_for(_load("slatwall_retail").meters_per_tile) == 128
    assert mg.pack_size_for(_load("carpet_tournament").meters_per_tile) == 256


# --------------------------------------------------------------------------- #
# The grooves
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("gid,axis,pitch_m", GROOVED,
                         ids=[g for g, _, _ in GROOVED])
def test_the_groove_pitch_is_the_real_one_in_metres(gid, axis, pitch_m):
    g = _load(gid)
    count = g.meso["count"]
    assert g.meso["generator"] == "stripes" and g.meso["axis"] == axis
    assert g.meters_per_tile / count == pytest.approx(pitch_m, abs=1e-6), (
        gid, g.meters_per_tile / count, pitch_m)
    # Integer bands per tile is what makes `stripes` wrap-exact; a fractional
    # count draws a cut-off band at the seam.
    assert count == int(count)


@pytest.mark.parametrize("gid,axis,pitch_m", GROOVED,
                         ids=[g for g, _, _ in GROOVED])
def test_the_groove_is_darker_than_the_face_and_is_where_it_says(gid, axis,
                                                                 pitch_m):
    """Measured off the albedo, not off the grammar: the lines the seam falls
    on are the darkest lines in the tile, by a step a person can see."""
    g, px, s = _synth(gid)
    count = g.meso["count"]
    prof = _luma(s["albedo"]).mean(axis=0 if axis == "x" else 1)
    frac = _band_fraction(px, count)
    # `stripes`' own mask, both sides of the joint. It is a fraction of the
    # BAND, so how many tile lines it covers depends on the pitch: 16 of 128
    # for the slatwall (one line per 8) and 8 of 128 for the panelling (a
    # wider band, and only the leading side of the joint lands on a line).
    seam = (frac < 0.06) | (frac > 1.0 - 0.06)
    assert seam.sum() >= count, (gid, int(seam.sum()), count)
    assert seam.mean() <= 0.14, (gid, float(seam.mean()))
    bands = np.floor(np.arange(px) / px * count).astype(int)
    assert len(set(bands[seam].tolist())) == count, "a band with no joint"
    # Medians, not extremes: at a pitch that is not a whole number of texels
    # the outermost seam line is only partly in the joint (the panelling's
    # 21.33 texel band puts 1.28 lines each side of it), so its luma sits
    # between the groove and the face by construction. The ordering
    # assertion below is the crisp claim; this one is the size of the step.
    step = float(np.median(prof[~seam]) - np.median(prof[seam]))
    assert step >= 10.0, (gid, step, np.median(prof[seam]),
                          np.median(prof[~seam]))
    assert prof[seam].max() < prof[~seam].min(), (
        gid, prof[seam].max(), prof[~seam].min())


def test_the_slatwall_grime_lands_in_the_groove_and_not_beside_it():
    """The coincidence the grammar is built on, measured.

    `ribs` at the meso's count and axis peaks exactly where `stripes` puts
    its seam, so a hard 12% quantile cut on that field selects the groove
    lines and nothing else. Neither file can show this; a change to either
    primitive breaks it silently.
    """
    g, px, _ = _synth("slatwall_retail")
    wear = g.wear[0]
    spec = wear["generator"]
    assert spec["generator"] == "ribs"
    assert (spec["count"], spec["axis"]) == (g.meso["count"], g.meso["axis"])
    assert wear["feather"] == 0.0, "a feathered cut would bleed onto the face"

    field = ps.ribs((px, px), spec["count"], ps.stream_seed(_SEED, "wear"),
                    axis=spec["axis"])
    cut = float(np.quantile(field, 1.0 - wear["coverage"]))
    touched = field >= cut
    seam = _band_fraction(px, g.meso["count"]) < 0.06
    expect = np.broadcast_to(seam[:, None], (px, px))
    assert np.array_equal(touched, expect), (
        int(touched.sum()), int(expect.sum()))


@pytest.mark.parametrize("gid,axis,_pitch", GROOVED,
                         ids=[g for g, _, _ in GROOVED])
def test_the_panel_face_reads_as_a_surface_not_static(gid, axis, _pitch):
    """Roadmap 140's two numbers on the FACE, with the groove lines removed.

    The whole-tile figure is dominated by the grooves -- slatwall measures
    ac1 0.43 over the tile and 0.39 over the face, and its spread falls from
    18.6 to 4.8 -- so the whole-tile number cannot answer "is the panel
    fizzy". The floor is the one `new_material.AC1_FLOOR` uses (0.3): the
    interior-finish floor of 0.5 is set for an unstructured wall, and these
    two are not.
    """
    g, px, s = _synth(gid)
    frac = _band_fraction(px, g.meso["count"])
    face = (frac >= 0.12) & (frac <= 0.88)
    alb = s["albedo"]
    sub = alb[:, face] if axis == "x" else alb[face, :]
    std, ac1 = _spread_and_correlation(sub)
    assert ac1 >= 0.3, (gid, std, ac1)
    assert 3.0 <= std <= 12.0, (gid, std, ac1)
    # ...and the grooves really are what the whole-tile number is made of.
    whole_std, _ = _spread_and_correlation(alb)
    assert whole_std > std, (gid, whole_std, std)


# --------------------------------------------------------------------------- #
# The carpet
# --------------------------------------------------------------------------- #

def test_the_tournament_carpet_is_duller_than_both_the_others():
    """The brief's one measurable word. carpet_delco is the walker's
    burgundy and carpet_club_delco a medallion figure; this one is a stage,
    so it is the only one of the three inside the environment budget."""
    rows = {gid: audit.measure(_load(gid),
                               mg.synthesize(_load(gid), size=256, seed=_SEED))
            for gid in ("carpet_tournament", "carpet_club_delco",
                        "carpet_delco")}
    c = {k: v["chroma_mean"] for k, v in rows.items()}
    assert c["carpet_tournament"] < c["carpet_club_delco"] < c["carpet_delco"]
    assert c["carpet_tournament"] <= audit.ENV_BUDGET["chroma_mean"], c
    # Flatter, too: a loop pile is a duller response than a cut pile.
    assert (rows["carpet_tournament"]["rough_mean"]
            > rows["carpet_delco"]["rough_mean"])
    assert (rows["carpet_tournament"]["hf_energy"]
            < rows["carpet_club_delco"]["hf_energy"])


def test_the_tournament_carpet_reads_as_a_surface_not_noise():
    """The carpet is a plain field, so it answers to the interior-finish
    floor `tests/test_theme_profiles.py` holds the delco carpet to."""
    _, _, s = _synth("carpet_tournament")
    std, ac1 = _spread_and_correlation(s["albedo"])
    assert ac1 >= 0.5, (std, ac1)
    assert 5.0 <= std <= 12.0, (std, ac1)


def test_no_card_shop_grammar_draws_a_loop_it_cannot_resolve():
    """A 1/10 in loop gauge is 0.33 of a texel at 128 px/m. Pixelcoat
    0.43.0 measured what happens when a weave is authored under the texel
    grid (64 threads on a 128 px tile: a hard per-texel alternation,
    ac1 0.15), so none of these three names a `weave`, and no band's
    lattice is finer than the grid it is sampled on."""
    assert 0.0254 / 10 * mg.DEFAULT_DENSITY < 1.0
    for gid in CARD_SHOP:
        g = _load(gid)
        px = mg.pack_size_for(g.meters_per_tile)
        for name in ("macro", "meso", "micro"):
            spec = getattr(g, name) or {}
            assert spec.get("generator") != "weave", (gid, name)
            cells = spec.get("cells") or spec.get("cells_across")
            if cells:
                assert px / cells >= 1.0, (gid, name, cells, px)


# --------------------------------------------------------------------------- #
# The theme
# --------------------------------------------------------------------------- #

def test_card_shop_names_every_key_bank_names():
    """`bank` is the reference key set for a finished interior. A theme that
    drops one of its slots falls through to whatever the kit defaults to,
    which is how a themed room ends up wearing one skin."""
    missing = set(_theme("bank")["materials"]) - set(
        _theme("card_shop")["materials"])
    assert not missing, sorted(missing)


def test_card_shop_wires_the_three_new_surfaces():
    mats = _theme("card_shop")["materials"]
    for slot, gid in SLOTS.items():
        assert mats.get(slot) == gid, (slot, mats.get(slot))


def test_card_shop_adds_exactly_the_two_new_kinds():
    extra = set(_theme("card_shop")["materials"]) - set(
        _theme("bank")["materials"])
    assert extra == {"wood_panel", "slatwall"}, sorted(extra)


def test_card_shop_still_carries_a_plank_wood_beside_its_panelling():
    """The reason `wood_panel` is its own kind: a theme holds one grammar per
    kind, and a card shop needs shelving and trim at the same time as a
    wainscot. If the panelling took the `wood` slot this test is how you
    find out the shelves became grooved wall panels."""
    mats = _theme("card_shop")["materials"]
    assert mats["wood"] != mats["wood_panel"]
    assert _load(mats["wood"]).meso["generator"] == "stripes"
    assert _load(mats["wood"]).meters_per_tile >= 2.0


def test_the_audit_judges_the_two_new_wall_kinds():
    """A kind missing from TERTIARY_KINDS gets no verdict at all -- 0.42.0's
    lesson, and the reason a new wall surface has to be named there."""
    for kind in ("wood_panel", "slatwall"):
        assert kind in audit.TERTIARY_KINDS


def test_card_shop_carries_no_unjustified_value_step():
    """The neighbour-pair gate over the theme's own environment surfaces.

    It is the reason `concrete` is `cinderblock_delco` and `drywall` is
    `drywall_orangepeel_delco`: with `concrete_delco` in the slot this theme
    carried four faults, every one of them a value step against an interior
    finish with no structure, chroma or hue to justify it (all four are also
    carried today by `delco` and `delco_1997`, so none of them was new).
    """
    rows = []
    for path in sorted(glob.glob(os.path.join(_MATERIALS, "*.json"))):
        g = mg.MaterialGrammar.load(path)
        rows.append(audit.measure(g, mg.synthesize(g, size=256, seed=_SEED)))
    mats = _theme("card_shop")["materials"]
    faults = audit.pair_faults(audit.neighbour_pairs(rows, mats))
    assert not faults, "\n  " + "\n  ".join(faults)


def test_every_card_shop_grammar_is_in_the_art_standard_baseline():
    with open(os.path.join(_ROOT, "tools", "art_standard_baseline.json"),
              encoding="utf-8") as f:
        base = json.load(f)["materials"]
    assert not [g for g in CARD_SHOP if g not in base]


def test_the_new_kinds_are_not_claimed_as_kinds_zoo_knows():
    """`cli.main._ZOO_KINDS` mirrors Zoo's `skins.KNOWN_KINDS`, and the
    warning it drives is the only thing that tells an author a pack will
    reach no mesh. `wood_panel` and `slatwall` are not in Zoo's vocabulary
    yet, so listing them here would turn a true warning into a false
    reassurance. When Zoo grows them, this test is what says so.
    """
    from pixelcoat.cli import main as cli
    for kind in ("wood_panel", "slatwall"):
        assert kind not in cli._ZOO_KINDS, (
            f"{kind} is listed as a kind Zoo knows -- check "
            f"zoo_keeper/core/skins.KNOWN_KINDS actually has it")
