"""Glass you can see through: the `glass` kind's contract, held at the owner.

Measured on walk 9050 (cold run 9050, delco_1997): `M_Skin_glass_delco_1997`
exported alphaMode OPAQUE on 12 GLBs -- 7 window modules, the teller line, the
bus shelter, the newspaper box, the parking meter and the car. The shipped
pack `glass_delco_1997/glass_delco.pack.json` carried no
`import_hints.transparency`, because the grammar `glass_delco.json` never
declared one, so Zoo's `materials._textured` never blended it. Every other
`glass` grammar in the library did declare one; nothing asked that they all
did.

These tests ask it three ways: statically over every shipped grammar and every
shipped theme, at `build_theme_library` (which now refuses), and through a
written pack, so the declaration is proven to reach the manifest Zoo reads.
"""

import glob
import json
import os

import pytest

from pixelcoat.core import material_grammar as mg

_PROFILES = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "profiles"))
_MATERIALS = os.path.join(_PROFILES, "materials")
_THEMES = os.path.join(_PROFILES, "themes")


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _grammar_paths(kinds):
    out = []
    for path in sorted(glob.glob(os.path.join(_MATERIALS, "*.json"))):
        if _load(path).get("kind") in kinds:
            out.append(path)
    return out


def _ids(p):
    return os.path.basename(p)[:-5]


def test_there_is_glass_to_check():
    """A glob that matches nothing passes every parametrised test below."""
    assert len(_grammar_paths(mg.SEE_THROUGH_KINDS)) >= 7
    assert len(_grammar_paths(mg.OPAQUE_GLAZING_KINDS)) >= 3


@pytest.mark.parametrize("path", _grammar_paths(mg.SEE_THROUGH_KINDS), ids=_ids)
def test_every_glass_grammar_is_see_through(path):
    g = mg.MaterialGrammar.from_dict(_load(path))
    assert mg.see_through_fault(g) is None, mg.see_through_fault(g)


@pytest.mark.parametrize("path", _grammar_paths(mg.OPAQUE_GLAZING_KINDS),
                         ids=_ids)
def test_every_facade_glass_grammar_stays_opaque(path):
    g = mg.MaterialGrammar.from_dict(_load(path))
    assert mg.see_through_fault(g) is None, mg.see_through_fault(g)


@pytest.mark.parametrize("path", sorted(glob.glob(os.path.join(_THEMES,
                                                               "*.json"))),
                         ids=_ids)
def test_every_theme_glazes_its_windows_see_through(path):
    """The slot a building's windows resolve, per theme -- the question the
    delco_1997 walk answered wrongly."""
    theme = _load(path)
    gid = theme["materials"]["glass"]
    g = mg.MaterialGrammar.load(os.path.join(_MATERIALS, gid + ".json"))
    t = g.transparency
    assert t and 0.0 < float(t["opacity"]) < 1.0, (theme["theme"], gid, t)


def test_delco_1997_glass_round_trips_into_the_pack(tmp_path):
    """The declaration reaches the manifest Zoo's `skins.load_pack` reads as
    `import_hints.transparency` -- not just the grammar file."""
    theme = _load(os.path.join(_THEMES, "delco_1997.json"))
    g = mg.MaterialGrammar.load(
        os.path.join(_MATERIALS, theme["materials"]["glass"] + ".json"))
    man = mg.build_material_pack(g, str(tmp_path / "glass_delco_1997"), size=32)
    hint = man["import_hints"]["transparency"]
    assert hint["alpha_mode"] == "blend"
    assert 0.0 < hint["opacity"] < 1.0
    on_disk = _load(str(tmp_path / "glass_delco_1997" / f"{man['asset_id']}"
                        ".pack.json"))
    assert on_disk["import_hints"]["transparency"] == hint


def _one_slot_theme(tmp_path, kind, raw):
    gdir = tmp_path / "grammars"
    gdir.mkdir()
    (gdir / f"{raw['id']}.json").write_text(json.dumps(raw), encoding="utf-8")
    profile = {"theme": "probe", "materials": {kind: raw["id"]}}
    return profile, str(gdir)


def test_theme_library_refuses_opaque_glass(tmp_path):
    raw = {"id": "slab_glass", "kind": "glass", "base_colors": ["#2b3a3d"]}
    profile, gdir = _one_slot_theme(tmp_path, "glass", raw)
    with pytest.raises(ValueError, match="declares no transparency"):
        mg.build_theme_library(profile, gdir, str(tmp_path / "out"), size=16)


def test_theme_library_refuses_cutout_glass(tmp_path):
    raw = {"id": "cut_glass", "kind": "glass", "base_colors": ["#2b3a3d"],
           "transparency": {"alpha_mode": "scissor"}}
    profile, gdir = _one_slot_theme(tmp_path, "glass", raw)
    with pytest.raises(ValueError, match="glass blends"):
        mg.build_theme_library(profile, gdir, str(tmp_path / "out"), size=16)


def test_theme_library_refuses_fully_opaque_opacity(tmp_path):
    raw = {"id": "one_glass", "kind": "glass", "base_colors": ["#2b3a3d"],
           "transparency": {"opacity": 1.0}}
    profile, gdir = _one_slot_theme(tmp_path, "glass", raw)
    with pytest.raises(ValueError, match="0 < opacity < 1"):
        mg.build_theme_library(profile, gdir, str(tmp_path / "out"), size=16)


def test_theme_library_refuses_see_through_facade(tmp_path):
    raw = {"id": "clear_facade", "kind": "glass_facade",
           "base_colors": ["#1b2a34"], "transparency": {"opacity": 0.5}}
    profile, gdir = _one_slot_theme(tmp_path, "glass_facade", raw)
    with pytest.raises(ValueError, match="declares transparency"):
        mg.build_theme_library(profile, gdir, str(tmp_path / "out"), size=16)


def test_other_kinds_are_unconstrained():
    """Road paint and foliage are scissor cutouts; the contract must not
    reach them."""
    for raw in ({"id": "p", "kind": "road_paint", "base_colors": ["#fff"],
                 "transparency": {"alpha_mode": "scissor"}},
                {"id": "b", "kind": "brick", "base_colors": ["#800"]}):
        assert mg.see_through_fault(mg.MaterialGrammar.from_dict(raw)) is None
