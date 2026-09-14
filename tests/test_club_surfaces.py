"""The club surfaces: a printed repeat, worn areas, and the grammars that use
them.

The walker, 2026-09-14, on two GTA IV strip-club references: "strip clubs
should have a dingy lived in feel, dark with colored lights, couches and
bars". The surfaces in those frames are a busy medallion carpet, burgundy
flocked damask on the walls, worn velvet and dark stained bar wood. Nothing
in the library could draw a figure: every primitive was a material's
structure, and a noise pushed until it reads as a figure is a blotch.

What is held here:

- `procedural_surface.medallion` is deterministic, three-level, tileable at
  every repeat count, mirror-symmetric when it should be, and each of its
  optional parts (scrolls, ogee frame, wobble) does something.
- The grammar's `motif` pours the colours it names and offsets the response
  where it says; `wear` touches the fraction of the tile it says, and a
  second pass never moves the first.
- Every club grammar builds byte-identically, wraps with no step worse than
  its own worst interior boundary on every map it emits, and meets the art
  standard's value, crush, blow, roughness and emissive clauses. Chroma is
  reported by the audit and deliberately not asserted: a burgundy wall is
  over a 0.030 budget by construction, and carpet_delco is the standing
  lesson that the walker's eye outranks that number.
- The figure still reads under the club's own light. Measured at the pack
  size, Oklab L of albedo x light in linear space (a stand-in for a lit
  surface, not a render): carpet_club_delco under magenta (1, 0.15, 0.85),
  ground 0.243 / burgundy ink 0.346; wallpaper_club_delco ground 0.316 /
  flock 0.248. No club grammar's p5 falls under 0.15 in either light.
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

CLUB = ("carpet_club_delco", "wallpaper_club_delco", "velvet_delco",
        "velvet_purple_delco", "velvet_teal_delco", "wood_stained_delco",
        "paint_block_brown_delco")
SLOTS = {"carpet_club": "carpet_club_delco",
         "wallpaper_club": "wallpaper_club_delco",
         "velvet": "velvet_delco",
         "wood_stained": "wood_stained_delco",
         "paint_block": "paint_block_brown_delco"}
MAGENTA = (1.0, 0.15, 0.85)
BLUE = (0.25, 0.35, 1.0)


def _load(gid):
    return mg.MaterialGrammar.load(os.path.join(_MATERIALS, gid + ".json"))


def _wrap_no_worse_than_interior(arr):
    """The seam test for a PATTERNED tile.

    `test_procedural_surface._seam_is_continuous` compares the wrap step to
    the largest single-texel step, which a figure with hard edges passes
    trivially. A mean over the whole seam row is the stricter question --
    does the wrap look like a boundary the tile has nowhere else -- and it
    must be compared against the WORST interior row, not the average: a
    mortar joint or an ogee line that lands on the wrap is a real boundary
    the interior also has. Returns (wrap, worst interior) per axis.
    """
    a = arr.astype(np.int32)
    if a.ndim == 2:
        a = a[..., None]
    rows = np.abs(np.diff(a, axis=0)).mean(axis=(1, 2))
    cols = np.abs(np.diff(a, axis=1)).mean(axis=(0, 2))
    wy = float(np.abs(a[0] - a[-1]).mean())
    wx = float(np.abs(a[:, 0] - a[:, -1]).mean())
    return (wy, float(rows.max())), (wx, float(cols.max()))


def test_the_wrap_check_fires_on_a_tile_that_does_not_wrap():
    """Prove the detector on a smooth field that does not wrap.

    ITS BLIND SPOT, found writing this test: a hard-edged figure cut off at
    the tile edge -- bars at 2.5 repeats -- measured wrap 255.0 against a
    worst interior column of 255.0 and PASSED, because a cut through a
    two-level figure is the same step as the figure's own edge. So this
    check cannot see a seam that looks like an edge the pattern already has.
    For the motif that case is covered by the periodicity assertion in
    `test_medallion_tiles`, which compares the first repeat to the last
    texel for texel."""
    h = 120
    ramp = np.tile(np.linspace(0.0, 255.0, h)[None, :], (h, 1))
    (_, _), (wx, worst) = _wrap_no_worse_than_interior(ramp)
    assert wx > 10 * worst


# --------------------------------------------------------------------------- #
# The primitive
# --------------------------------------------------------------------------- #

def test_medallion_is_deterministic_and_three_level():
    a = ps.medallion(128, 2, _SEED)
    b = ps.medallion(128, 2, _SEED)
    assert np.array_equal(a, b)
    assert a.dtype == np.float32
    levels = set(np.unique(a).tolist())
    assert levels == {0.0, 0.5, 1.0}, levels
    ground = float((a == 0.0).mean())
    assert 0.4 < ground < 0.9, ground              # a figure on a ground


@pytest.mark.parametrize("count", [1, 2, 3])
@pytest.mark.parametrize("opts", [{}, {"ogee": 0.5, "arms": 0},
                                  {"wobble": 0.02}],
                         ids=["rosette", "damask", "wobbled"])
def test_medallion_tiles(count, opts):
    f = ps.medallion(120, count, _SEED, **opts)
    for wrap, worst in _wrap_no_worse_than_interior(f * 255):
        assert wrap <= worst + 1e-6, (wrap, worst)
    # And the tile placed beside itself continues the figure: the repeat at
    # the wrap is the repeat at the start.
    per = 120 // count
    assert np.array_equal(f[:, :per], f[:, -per:]) or opts.get("wobble")


def test_medallion_without_scrolls_or_wobble_is_mirror_symmetric():
    """Scrolls are chiral by design; the rest of the motif is not. Sampled
    at texel centres, so a whole number of texels per repeat mirrors
    exactly."""
    f = ps.medallion(128, 2, _SEED, arms=0, ogee=0.5)
    assert np.array_equal(f, f[:, ::-1])
    assert np.array_equal(f, f[::-1, :])


def test_each_part_of_the_motif_draws():
    base = ps.medallion(128, 2, _SEED, arms=0)
    scrolls = ps.medallion(128, 2, _SEED, arms=6, swirl=0.9, scroll=0.3)
    framed = ps.medallion(128, 2, _SEED, arms=0, ogee=0.5)
    assert (scrolls == 0.5).sum() > (base == 0.5).sum()
    assert (framed == 0.5).sum() > (base == 0.5).sum()
    wobbled = ps.medallion(128, 2, _SEED, arms=0, wobble=0.02)
    assert not np.array_equal(base, wobbled)
    # The wobble is its own stream: another seed moves it, and without a
    # wobble the seed does nothing at all.
    assert not np.array_equal(
        wobbled, ps.medallion(128, 2, 7, arms=0, wobble=0.02))
    assert np.array_equal(base, ps.medallion(128, 2, 7, arms=0))


# --------------------------------------------------------------------------- #
# The grammar layers
# --------------------------------------------------------------------------- #

_PLAIN = {"id": "t", "kind": "carpet", "base_colors": ["#404040"],
          "posterize": 0, "detail_strength": 0.0,
          "bands": {"macro": 0.0, "meso": 0.0, "micro": 0.0}}


def test_motif_pours_the_colours_it_names():
    raw = dict(_PLAIN, motif={"count": 2, "colors": ["#a02020", "#2020a0"]})
    out = mg.synthesize(mg.MaterialGrammar.from_dict(raw), size=128, seed=_SEED)
    ink = ps.medallion(128, 2, ps.stream_seed(_SEED, "motif"), label="motif")
    alb = out["albedo"].astype(int)
    assert np.all(alb[ink == 1.0] == [160, 32, 32])
    assert np.all(alb[ink == 0.5] == [32, 32, 160])
    assert np.all(alb[ink == 0.0] == [64, 64, 64])


def test_motif_roughness_offsets_the_ink_only():
    raw = dict(_PLAIN, roughness={"base": 0.6, "variation": 0.0},
               motif={"count": 2, "colors": ["#202020"], "roughness": 0.1})
    out = mg.synthesize(mg.MaterialGrammar.from_dict(raw), size=128, seed=_SEED)
    ink = ps.medallion(128, 2, ps.stream_seed(_SEED, "motif"), label="motif")
    r = out["roughness"].astype(int)
    assert np.all(r[ink == 0.0] == 153)                      # 0.6
    assert np.all(r[ink > 0.0] == 179)                       # 0.7


def test_wear_touches_the_fraction_it_names_with_a_hard_edge():
    raw = dict(_PLAIN, wear={"coverage": 0.2, "feather": 0.0,
                             "color": "#c0c0c0", "strength": 1.0})
    alb = mg.synthesize(mg.MaterialGrammar.from_dict(raw), size=128,
                        seed=_SEED)["albedo"]
    touched = float((alb[..., 0] == 192).mean())
    assert abs(touched - 0.2) < 0.01, touched


def test_a_second_wear_pass_never_moves_the_first():
    one = dict(_PLAIN, wear=[{"coverage": 0.2, "feather": 0.0,
                              "color": "#c0c0c0", "strength": 1.0}])
    two = dict(_PLAIN, wear=one["wear"] + [{"coverage": 0.1, "feather": 0.0,
                                            "color": "#101010",
                                            "strength": 1.0}])
    a = mg.synthesize(mg.MaterialGrammar.from_dict(one), size=96, seed=_SEED)
    b = mg.synthesize(mg.MaterialGrammar.from_dict(two), size=96, seed=_SEED)
    first = a["albedo"][..., 0] == 192
    second = b["albedo"][..., 0] == 16
    assert np.all(b["albedo"][first & ~second] == a["albedo"][first & ~second])


def test_a_single_wear_spec_is_the_first_pass_of_a_list():
    spec = {"coverage": 0.3, "feather": 0.5, "color": "#806040",
            "strength": 0.5}
    a = mg.synthesize(mg.MaterialGrammar.from_dict(dict(_PLAIN, wear=spec)),
                      size=96, seed=_SEED)
    b = mg.synthesize(mg.MaterialGrammar.from_dict(dict(_PLAIN, wear=[spec])),
                      size=96, seed=_SEED)
    assert np.array_equal(a["albedo"], b["albedo"])


# --------------------------------------------------------------------------- #
# The grammars
# --------------------------------------------------------------------------- #

def _synth(gid):
    g = _load(gid)
    return g, mg.synthesize(g, size=mg.pack_size_for(g.meters_per_tile),
                            seed=_SEED)


@pytest.mark.parametrize("gid", CLUB)
def test_club_grammar_builds_deterministically(gid):
    g, a = _synth(gid)
    b = mg.synthesize(g, size=mg.pack_size_for(g.meters_per_tile), seed=_SEED)
    assert set(a) == set(b)
    for k in a:
        assert np.array_equal(a[k], b[k]), k


@pytest.mark.parametrize("gid", CLUB)
def test_club_grammar_tiles_on_every_map(gid):
    _, s = _synth(gid)
    for key, arr in s.items():
        for wrap, worst in _wrap_no_worse_than_interior(arr):
            assert wrap <= worst + 1e-6, (gid, key, wrap, worst)


@pytest.mark.parametrize("gid", CLUB)
def test_club_grammar_meets_the_art_standard_it_can(gid):
    g = _load(gid)
    row = audit.measure(g, mg.synthesize(g, size=256, seed=_SEED))
    b = audit.ENV_BUDGET
    assert row["crushed_frac"] == 0.0, row["crushed_frac"]
    assert row["blown_frac"] == 0.0, row["blown_frac"]
    assert row["value_range"] <= b["value_range"], row["value_range"]
    assert row["rough_mean"] >= b["rough_mean_min"], row["rough_mean"]
    assert not row["emissive"]


@pytest.mark.parametrize("gid", CLUB)
def test_club_grammar_is_a_surface_not_static(gid):
    """Roadmap 140's two numbers, at the pack size: neighbour correlation of
    the albedo's luminance at least the drywall/carpet floor, and a spread
    that is neither flat nor loud."""
    _, s = _synth(gid)
    a = s["albedo"][..., :3].astype(np.float64)
    lum = 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]
    d = lum - lum.mean()
    var = (d * d).mean()
    ac1 = ((d[:, :-1] * d[:, 1:]).mean() + (d[:-1] * d[1:]).mean()) / var / 2
    assert ac1 >= 0.5, (gid, ac1)
    assert 4.0 <= lum.std() <= 16.0, (gid, lum.std())


def _lit_L(albedo_u8, light):
    lin = audit._srgb_to_linear(albedo_u8[..., :3] / 255.0) * np.array(light)
    lin = np.clip(lin, 0.0, 1.0)
    srgb = np.where(lin <= 0.0031308, lin * 12.92,
                    1.055 * lin ** (1 / 2.4) - 0.055)
    return audit.srgb_to_oklab(np.rint(srgb * 255).astype(np.uint8))[..., 0]


@pytest.mark.parametrize("gid", CLUB)
@pytest.mark.parametrize("light", [MAGENTA, BLUE], ids=["magenta", "blue"])
def test_club_grammar_is_not_a_hole_under_coloured_light(gid, light):
    _, s = _synth(gid)
    p5 = float(np.percentile(_lit_L(s["albedo"], light), 5))
    assert p5 >= 0.15, (gid, p5)


@pytest.mark.parametrize("gid", ["carpet_club_delco", "wallpaper_club_delco"])
def test_the_figure_reads_under_magenta(gid):
    g, s = _synth(gid)
    mo = g.motif
    px = s["albedo"].shape[0]
    keys = ("petals", "radius", "arms", "swirl", "scroll", "corner",
            "aspect", "line", "ogee", "wobble")
    ink = ps.medallion(px, mo["count"], ps.stream_seed(_SEED, "motif"),
                       label="motif", **{k: mo[k] for k in keys if k in mo})
    L = _lit_L(s["albedo"], MAGENTA)
    step = abs(float(np.median(L[ink == 1.0])) - float(np.median(L[ink == 0.0])))
    assert step >= 0.05, (gid, step)


def test_the_flock_is_matte_against_the_paper():
    g, s = _synth("wallpaper_club_delco")
    mo = g.motif
    ink = ps.medallion(s["roughness"].shape[0], mo["count"],
                       ps.stream_seed(_SEED, "motif"), label="motif",
                       **{k: mo[k] for k in ("petals", "radius", "arms",
                                             "corner", "aspect", "line",
                                             "ogee", "wobble") if k in mo})
    r = s["roughness"] / 255.0
    assert abs((r[ink > 0].mean() - r[ink == 0].mean()) - mo["roughness"]) < 0.02


# --------------------------------------------------------------------------- #
# The themes
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("theme", ["delco", "delco_1997"])
def test_delco_themes_map_the_club_kinds(theme):
    with open(os.path.join(_THEMES, theme + ".json"), encoding="utf-8") as f:
        mats = json.load(f)["materials"]
    for kind, gid in SLOTS.items():
        assert mats.get(kind) == gid, (theme, kind, mats.get(kind))


@pytest.mark.parametrize("theme", ["delco", "delco_1997"])
def test_the_walker_keeps_carpet_delco(theme):
    """The club carpet is a second carpet, never a replacement: the walker
    likes carpet_delco (2026-09-13) and it keeps the `carpet` slot."""
    with open(os.path.join(_THEMES, theme + ".json"), encoding="utf-8") as f:
        assert json.load(f)["materials"]["carpet"] == "carpet_delco"


def test_every_club_grammar_is_in_the_art_standard_baseline():
    with open(os.path.join(_ROOT, "tools", "art_standard_baseline.json"),
              encoding="utf-8") as f:
        base = json.load(f)["materials"]
    assert not [g for g in CLUB if g not in base]


def test_the_audit_judges_the_club_floor_and_wall_kinds():
    """A kind missing from TERTIARY_KINDS gets no verdict at all."""
    for kind in ("carpet_club", "wallpaper_club", "wood_stained",
                 "paint_block"):
        assert kind in audit.TERTIARY_KINDS
