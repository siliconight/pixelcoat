"""Tests for the shipped theme profiles (profiles/themes/*.json).

A theme profile is a declarative map of one grammar per material kind, and
``build_theme_library`` raises if a grammar's declared ``kind`` doesn't match
the slot the profile maps it to. That check only fires at build time, once a
theme is actually run -- so a profile can sit in the tree looking correct and
fail the first time anyone asks for its library. Two of the three rockay_*
profiles shipped that way: cinderblock_delco and travertine_warm are both
kind 'concrete', authored into the 'brick' and 'tile' slots.

These tests validate every profile against the grammar library statically, so
a mis-slotted grammar is a red test rather than a failed art pass.
"""

import glob
import json
import os

import pytest

_PROFILES = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "profiles"))
_THEMES = os.path.join(_PROFILES, "themes")
_MATERIALS = os.path.join(_PROFILES, "materials")


def _grammar_kinds():
    """grammar_id -> declared kind, for every shipped material grammar."""
    kinds = {}
    for path in glob.glob(os.path.join(_MATERIALS, "*.json")):
        with open(path, encoding="utf-8") as f:
            kinds[os.path.basename(path)[:-5]] = json.load(f).get("kind")
    return kinds


def _theme_paths():
    return sorted(glob.glob(os.path.join(_THEMES, "*.json")))


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def test_theme_dir_is_not_empty():
    assert _theme_paths(), f"no theme profiles under {_THEMES}"


@pytest.mark.parametrize("path", _theme_paths(),
                         ids=lambda p: os.path.basename(p)[:-5])
def test_theme_grammars_exist_and_match_their_slot(path):
    """Every curated grammar exists, and its declared kind IS the slot.

    This is the same invariant build_theme_library enforces -- asserted here
    without paying for synthesis, so it fails in CI instead of mid-art-pass.
    """
    kinds = _grammar_kinds()
    theme = _load(path)
    faults = []
    for slot, grammar_id in theme.get("materials", {}).items():
        if grammar_id not in kinds:
            faults.append(f"slot '{slot}': no grammar '{grammar_id}'")
        elif kinds[grammar_id] != slot:
            faults.append(f"slot '{slot}': grammar '{grammar_id}' is kind "
                          f"'{kinds[grammar_id]}'")
    assert not faults, f"{theme.get('theme')}: " + "; ".join(faults)


@pytest.mark.parametrize("path", _theme_paths(),
                         ids=lambda p: os.path.basename(p)[:-5])
def test_theme_name_matches_its_filename(path):
    """find_pack resolves <kind>_<theme>/ by the theme NAME, so a profile
    whose 'theme' field disagrees with its filename builds packs nobody
    looks up."""
    theme = _load(path)
    assert theme.get("theme") == os.path.basename(path)[:-5]


@pytest.mark.parametrize("path", _theme_paths(),
                         ids=lambda p: os.path.basename(p)[:-5])
def test_theme_covers_the_exterior_kinds(path):
    """A building's exterior reads from these four. A profile missing one
    falls through to whatever the kit defaults to, which is how a themed
    street ends up wearing one skin."""
    theme = _load(path)
    missing = {"brick", "concrete", "glass", "metal"} - set(
        theme.get("materials", {}))
    assert not missing, f"{theme.get('theme')}: no {sorted(missing)}"


# --------------------------------------------------------------------------- #
# A kind no LEVEL theme maps is a material nothing can ever wear
# --------------------------------------------------------------------------- #
#
# 0.44.0 shipped `wood_panel_delco` and `slatwall_retail` and mapped them in
# `card_shop` only. Every level this pipeline generates runs on `delco` or
# `delco_1997`, neither of which had the kinds -- so cold run 9061's package
# instanced 21 modules whose stems end `_mwood_panel` or `_mslatwall`, Zoo's
# `find_pack` returned None for both, and the card shop's whole intended look
# shipped as flat grey. Measured in that package
# (`_runs/walk_export_card_block_001`): of the 11 kinds its GLBs carry, the
# only two whose kind-named material has no `baseColorTexture` are those two;
# every other kind resolved to an `M_Skin_<pack>_<theme>` with a texture on it.
#
# WHY THAT IS A KIND-LEVEL RULE AND NOT A GRAMMAR-LEVEL ONE. A theme holds one
# grammar per kind, so picking `brick_buff_civic` over `brick_delco` is a style
# choice and the other grammar is not "unreachable" -- it is simply not this
# theme's brick. 32 of the 86 shipped grammars sit in that bucket today and
# demanding they all be mapped would be a gate nobody could keep green. A KIND,
# though, is the slot itself: a kind no level theme maps is a surface no level
# can ever show, whatever grammar it would have chosen.
#
# WHICH THEMES ARE "LEVEL" THEMES IS DERIVED, NOT LISTED. Level Factory's
# `GROUND_SKIN_KINDS` (apps/cli/commands/__init__.py) points Lot's six outdoor
# families at four kinds -- ground and road at `asphalt`, path and sidewalk at
# `sidewalk`, courtyard at `concrete`, the markings at `road_paint`. A theme
# that cannot answer all four cannot dress a site's outdoors and is a palette
# for rooms, not a theme a brief can name. On the shipped tree that picks out
# `delco` and `delco_1997` and nothing else -- including `card_shop`, which is
# the actual mistake behind 9061: the card shop is one building on a street,
# and a brief carries ONE theme for the whole mission
# (`schemas/mission.brief.schema.json`), so its surfaces have to live in the
# street's theme or not at all.
LEVEL_GROUND_KINDS = frozenset({"asphalt", "sidewalk", "concrete", "road_paint"})


def _level_themes():
    """Theme name -> materials map, for the themes that can dress a whole site."""
    out = {}
    for path in _theme_paths():
        theme = _load(path)
        if LEVEL_GROUND_KINDS <= set(theme.get("materials", {})):
            out[theme["theme"]] = theme["materials"]
    return out


def test_the_level_theme_derivation_separates_something():
    """The rule below is only worth anything if it does not classify every
    theme as a level theme, and is not vacuous if it classifies none. Both
    failure modes read as a green suite, which is the shape this whole file
    exists to refuse."""
    level = set(_level_themes())
    every = {_load(p)["theme"] for p in _theme_paths()}
    assert level, f"no theme maps all of {sorted(LEVEL_GROUND_KINDS)}"
    assert every - level, ("every theme qualifies as a level theme; the "
                           "derivation has stopped separating anything")


def test_every_kind_any_theme_maps_is_mapped_by_every_level_theme():
    """RED on 0.44.0 with `wood_panel` and `slatwall`, on both level themes.

    The direction matters: a partial theme is allowed to be partial -- `bank`
    maps 24 kinds and is a room palette -- but it is not allowed to be the ONLY
    place a kind is answered, because then that kind reaches no level.
    """
    every = {t["theme"]: t.get("materials", {})
             for t in (_load(p) for p in _theme_paths())}
    level = _level_themes()
    wanted = set().union(*(set(m) for m in every.values()))
    faults = []
    for name in sorted(level):
        for kind in sorted(wanted - set(level[name])):
            where = sorted(t for t, m in every.items() if kind in m)
            faults.append(f"{name} maps no '{kind}' (mapped by "
                          f"{', '.join(where)})")
    assert not faults, "; ".join(faults)


def test_carpet_tournament_is_still_unreachable_and_that_is_recorded():
    """A TRIPWIRE, not an endorsement -- read the 0.45.0 changelog entry.

    `carpet_tournament` is kind `carpet`, and a theme holds one grammar per
    kind. `delco_1997`'s carpet is `carpet_delco`, the burgundy the walker
    asked in as many words to keep (see that grammar's own notes), so the card
    shop's play floor gets the burgundy and the tournament loop reaches no
    surface in any level. The kind vocabulary CANNOT express "this room's
    carpet differs from the level's carpet"; expressing it needs a kind of its
    own, exactly the way `carpet_club` was added for the club floor, and that
    is a four-repo change this branch did not make (Pixelcoat's kind and theme
    maps, Zoo's `KNOWN_KINDS`, Deli Counter's `material_kind.KIND_BY_MATERIAL`
    and `level_design._CARD_SHOP_FINISHES`).

    Deliberately NOT fixed by mapping the grammar into the level themes: that
    would add a 682.7 KiB pack to every delco and delco_1997 library for a
    surface nothing asks for, which is the performance rule paying for a look
    that does not exist yet. When the kind lands, this test goes red and its
    reader is pointed at the decision rather than at a surprise.
    """
    level = _level_themes()
    assert level, "derivation broken; see the test above"
    for name, materials in level.items():
        assert materials.get("carpet") != "carpet_tournament", (
            f"{name} now maps the tournament carpet -- if the `carpet_tournament` "
            f"KIND landed, delete this test and say so in the changelog")


def _rockay_family():
    """Every theme in the family INCLUDING the base `rockay`.

    An earlier version of these tests matched `rockay_` with the underscore,
    which silently excluded the base theme the variants are variants OF. It
    passed while rockay and rockay_civic shared their brick, their tile and
    their metal -- so two buildings on the same street rendered identically
    and the suite said the family was varied. A contact sheet caught it; the
    test could not, because it was not looking at the pair that collided.
    """
    return [_load(p) for p in _theme_paths()
            if os.path.basename(p).startswith("rockay")]


def test_rockay_family_shares_its_signature_surfaces():
    """Cohesion from the surface that reads at distance: every theme in the
    family wears the same curtain wall, so a mixed-theme street reads as one
    city."""
    family = _rockay_family()
    assert len(family) >= 2, "expected the rockay family"
    shared = {t["materials"].get("glass_facade") for t in family}
    assert shared == {"glass_facade_mirror_blue"}, shared


def test_rockay_family_varies_the_wall():
    """...and variety from the wall itself: no two themes in the family wear
    the same brick, or the street reads as differently-shaped buildings in
    identical paint -- which is the complaint that started this work."""
    family = _rockay_family()
    bricks = [t["materials"].get("brick") for t in family]
    assert len(set(bricks)) == len(bricks), bricks


# --------------------------------------------------------------------------- #
# Roadmap 140: a skin must read as a surface, not as noise
# --------------------------------------------------------------------------- #
#
# Walked 2026-09-11 on cold run 9005: the delco_1997 drywall read as "fizzy,
# too much digital noise". Two numbers over the albedo's luminance say why --
# its spread (std, 0-255) and the correlation between a texel and its
# neighbour (1.0 = smooth, 0.0 = every texel independent). Measured on the
# shipped packs that day: drywall std 23.9 / ac1 0.12, carpet 10.0 / 0.08,
# against plaster 12.1 / 0.34, ceiling_tile 15.6 / 0.51, concrete 28.2 /
# 0.75, brick 31.5 / 0.80. Brick's amplitude at carpet's correlation is
# static. The dial was `detail_strength`, the per-texel hash grain: 0.18 on
# drywall, 0.22 on carpet, and sweeping it alone took drywall to 10.7 / 0.61.
# The micro band was NOT the dial -- its weight (0.30 x 0.12 of a +-0.5
# field) sits under one posterize step and quantises away, so changing it
# moved nothing at one decimal.
#
# The floor below is the check: correlation at least 0.5, the ceiling_tile /
# concrete band, for the interior finishes a person stands next to.

_SURFACE_NOT_NOISE = {
    # kind -> (min ac1, std range) at the pack size the theme ships
    "drywall": (0.5, (9.0, 16.0)),
    "carpet": (0.5, (5.0, 12.0)),
    "plaster": (0.3, (8.0, 16.0)),
}


def _albedo_metric(albedo_u8):
    import numpy as np
    a = albedo_u8.astype(np.float64)
    lum = 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]
    d = lum - lum.mean()
    var = (d * d).mean()
    ax = (d[:, :-1] * d[:, 1:]).mean() / var
    ay = (d[:-1, :] * d[1:, :]).mean() / var
    return float(lum.std()), float((ax + ay) / 2.0)


@pytest.mark.parametrize("kind", sorted(_SURFACE_NOT_NOISE))
def test_delco_interior_finishes_read_as_surface_not_noise(kind):
    from pixelcoat.core import material_grammar as mg
    theme = _load(os.path.join(_THEMES, "delco_1997.json"))
    grammar_id = theme["materials"][kind]
    raw = _load(os.path.join(_MATERIALS, grammar_id + ".json"))
    g = mg.MaterialGrammar.from_dict(raw)
    size = mg.pack_size_for(raw.get("meters_per_tile"))
    std, ac1 = _albedo_metric(mg.synthesize(g, size=size)["albedo"])
    min_ac1, (lo, hi) = _SURFACE_NOT_NOISE[kind]
    assert ac1 >= min_ac1, (grammar_id, std, ac1)
    assert lo <= std <= hi, (grammar_id, std, ac1)
