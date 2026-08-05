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
