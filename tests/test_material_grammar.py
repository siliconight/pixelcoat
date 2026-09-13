"""Tests for pixelcoat.core.material_grammar (roadmap T03 synthesis + pack).

Proves: deterministic byte-identical synthesis, the emit flags are honoured,
materials are visually distinct, albedo tiles, and the written pack matches the
contract Zoo's core.skins.load_pack requires (a *.pack.json naming an existing
albedo, relative map filenames, meters_per_tile).
"""

import json
import os

import numpy as np
import pytest

from pixelcoat.core import material_grammar as mg
from pixelcoat.core import procedural_surface as ps

_PROFILES = os.path.join(os.path.dirname(__file__), "..", "profiles", "materials")


def _grammar(name):
    return mg.MaterialGrammar.load(os.path.join(_PROFILES, f"{name}.json"))


def _seam_ok(field, factor=1.3):
    interior = max(np.abs(np.diff(field.astype(np.int32), axis=0)).max(),
                   np.abs(np.diff(field.astype(np.int32), axis=1)).max())
    seam = max(np.abs(field[0].astype(np.int32) - field[-1].astype(np.int32)).max(),
               np.abs(field[:, 0].astype(np.int32) - field[:, -1].astype(np.int32)).max())
    return seam <= interior * factor + 2


# --------------------------------------------------------------------------- #
# Synthesis
# --------------------------------------------------------------------------- #

def test_synthesize_albedo_shape_and_dtype():
    out = mg.synthesize(_grammar("concrete_delco"), size=128)
    assert out["albedo"].shape == (128, 128, 3)
    assert out["albedo"].dtype == np.uint8


def test_emit_flags_honoured():
    metal = mg.synthesize(_grammar("painted_metal_industrial"), size=96)
    assert "roughness" in metal and "normal" in metal        # both emitted
    concrete = mg.synthesize(_grammar("concrete_delco"), size=96)
    assert "roughness" in concrete and "normal" not in concrete  # normal off


def test_synthesis_is_deterministic():
    g = _grammar("painted_metal_industrial")
    a = mg.synthesize(g, size=96, seed=1999)
    b = mg.synthesize(g, size=96, seed=1999)
    for k in a:
        assert np.array_equal(a[k], b[k]), k


def test_seed_changes_placement_not_identity():
    g = _grammar("painted_metal_industrial")
    a = mg.synthesize(g, size=96, seed=1999)["albedo"]
    b = mg.synthesize(g, size=96, seed=2026)["albedo"]
    assert not np.array_equal(a, b)                      # different placement
    # Same material identity: mean colour stays close across seeds.
    assert np.abs(a.reshape(-1, 3).mean(0) - b.reshape(-1, 3).mean(0)).max() < 12


def test_materials_are_distinct():
    metal = mg.synthesize(_grammar("painted_metal_industrial"), size=96)["albedo"]
    concrete = mg.synthesize(_grammar("concrete_delco"), size=96)["albedo"]
    rubber = mg.synthesize(_grammar("rubber_delco"), size=96)["albedo"]
    mm = metal.reshape(-1, 3).mean(0)
    cm = concrete.reshape(-1, 3).mean(0)
    rm = rubber.reshape(-1, 3).mean(0)
    assert np.abs(mm - cm).max() > 20
    assert np.abs(cm - rm).max() > 20
    assert rm.mean() < mm.mean() < cm.mean()             # rubber dark, concrete light


def test_albedo_and_normal_tile():
    out = mg.synthesize(_grammar("painted_metal_industrial"), size=128)
    assert _seam_ok(out["albedo"])
    assert _seam_ok(out["normal"])


# --------------------------------------------------------------------------- #
# Pack writer — Zoo-consumable contract
# --------------------------------------------------------------------------- #

def test_all_shipped_grammars_build():
    import glob
    files = glob.glob(os.path.join(_PROFILES, "*.json"))
    assert files, "no shipped grammars found"
    for f in files:
        g = mg.MaterialGrammar.load(f)
        out = mg.synthesize(g, size=48)
        # RGB, or RGBA for a grammar with a cutout (road paint)
        assert "albedo" in out and out["albedo"].shape[:2] == (48, 48), f
        assert out["albedo"].shape[2] == (4 if g.cutout else 3), f
        assert g.kind, f                                 # every grammar names a kind


def test_build_pack_matches_zoo_contract(tmp_path):
    pack_dir = tmp_path / "metal_delco"          # Zoo <kind>_<theme> layout
    manifest = mg.build_material_pack(
        os.path.join(_PROFILES, "painted_metal_industrial.json"),
        str(pack_dir), size=64)

    # Manifest shape Zoo's load_pack reads.
    assert manifest["asset_id"] == "painted_metal_industrial"
    assert manifest["material_kind"] == "metal"          # a Zoo KNOWN_KIND
    assert "albedo" in manifest["maps"]                  # required by Zoo
    assert isinstance(manifest["meters_per_tile"], float)
    assert manifest["tileable"] == ["x", "y"]

    # Every named map file exists and is a relative filename (Zoo joins to dir).
    for key, fname in manifest["maps"].items():
        assert not os.path.isabs(fname)
        assert (pack_dir / fname).is_file()

    # The on-disk manifest parses and round-trips.
    on_disk = json.loads((pack_dir / "painted_metal_industrial.pack.json").read_text())
    assert on_disk["maps"] == manifest["maps"]


def test_pack_write_is_deterministic(tmp_path):
    src = os.path.join(_PROFILES, "concrete_delco.json")
    m1 = mg.build_material_pack(src, str(tmp_path / "a"), size=48)
    m2 = mg.build_material_pack(src, str(tmp_path / "b"), size=48)
    for key in m1["maps"]:
        pa = (tmp_path / "a" / m1["maps"][key]).read_bytes()
        pb = (tmp_path / "b" / m2["maps"][key]).read_bytes()
        assert pa == pb, key           # byte-identical PNGs


# --------------------------------------------------------------------------- #
# Aggregate / emissive / transparency / multi-scale veins / albedo_pattern
# --------------------------------------------------------------------------- #

def test_aggregate_layer_tiles():
    # cobblestone uses the voronoi_cells aggregate layer; still tiles.
    out = mg.synthesize(_grammar("cobblestone"), size=128)
    assert out["albedo"].shape == (128, 128, 3)
    assert _seam_ok(out["albedo"])


def test_emissive_emitted_only_when_requested():
    glow = mg.MaterialGrammar.from_dict(
        {"id": "glow", "kind": "glass", "base_colors": ["#20c040"],
         "emissive": {"strength": 1.0}})
    assert "emissive" in mg.synthesize(glow, size=48)
    dark = mg.MaterialGrammar.from_dict(
        {"id": "dark", "kind": "glass", "base_colors": ["#20c040"]})
    assert "emissive" not in mg.synthesize(dark, size=48)


def test_transparency_hint_only_on_see_through_glass(tmp_path):
    win = mg.MaterialGrammar.from_dict(
        {"id": "win", "kind": "glass", "base_colors": ["#cfd6d4"],
         "transparency": {"opacity": 0.5, "ior": 1.45},
         "emit": {"roughness": True, "normal": True}})
    man = mg.build_material_pack(win, str(tmp_path / "win"), size=48)
    hint = man["import_hints"].get("transparency")
    assert hint and hint["opacity"] == 0.5 and hint["alpha_mode"] == "blend"
    # opaque facade glass ships no transparency hint
    fac = mg.MaterialGrammar.from_dict(
        {"id": "fac", "kind": "glass_facade", "base_colors": ["#1b2a34"]})
    man2 = mg.build_material_pack(fac, str(tmp_path / "fac"), size=48)
    assert "transparency" not in man2["import_hints"]


def test_multiscale_veins_accepts_list_and_tiles():
    # marble now uses a list of vein passes (broad + hairline); still tiles.
    out = mg.synthesize(_grammar("marble_bank_floor"), size=128)
    assert _seam_ok(out["albedo"])


def test_albedo_pattern_decouples_albedo_from_normal():
    base = {"id": "g", "kind": "glass", "base_colors": ["#cfd6d4"],
            "bands": {"macro": 0.15, "meso": 0.5, "micro": 0.1},
            "meso": {"generator": "ribs", "count": 20},
            "emit": {"roughness": True, "normal": True}}
    strong = mg.synthesize(mg.MaterialGrammar.from_dict({**base, "albedo_pattern": 1.0}), size=96)
    flat = mg.synthesize(mg.MaterialGrammar.from_dict({**base, "albedo_pattern": 0.1}), size=96)
    # low albedo_pattern flattens the albedo's response to the pattern...
    assert flat["albedo"].astype(np.float32).std() < strong["albedo"].astype(np.float32).std()
    # ...but the normal (built from the height field) is unchanged.
    assert np.array_equal(strong["normal"], flat["normal"])


def test_a_directional_warp_moves_the_pattern_and_keeps_it_tiling():
    """The Substance node of the same name (the walker's frames, 2026-09-13):
    blending a noise over a grid changes its colour and leaves the grid;
    warping MOVES it, so a joint bends."""
    base = {"id": "w", "kind": "brick", "base_colors": ["#8a5a44"],
            "masonry": {"rows": 6, "cols": 3}, "emit": {"roughness": True,
                                                        "normal": True}}
    flat = mg.synthesize(mg.MaterialGrammar.from_dict(base), size=96)
    warped = mg.synthesize(mg.MaterialGrammar.from_dict(
        {**base, "warp": {"generator": {"generator": "fbm", "cells": 4,
                                        "octaves": 3},
                          "intensity": 0.06, "angle": 143}}), size=96)
    assert not np.array_equal(flat["albedo"], warped["albedo"])
    # the height bends with the colour, or the normal slides off the surface
    assert not np.array_equal(flat["normal"], warped["normal"])
    # and it still tiles: the wrap means column 0 continues from column -1
    a = warped["albedo"].astype(np.int16)
    seam = np.abs(a[:, 0] - a[:, -1]).mean()
    middle = np.abs(a[:, 48] - a[:, 47]).mean()
    assert seam <= middle * 3.0 + 6.0, (seam, middle)


def test_the_warp_is_deterministic_and_zero_intensity_is_a_no_op():
    base = {"id": "w2", "kind": "concrete", "base_colors": ["#808080"],
            "masonry": {"rows": 4, "cols": 4}}
    spec = {**base, "warp": {"intensity": 0.05, "angle": 30}}
    one = mg.synthesize(mg.MaterialGrammar.from_dict(spec), size=64)["albedo"]
    two = mg.synthesize(mg.MaterialGrammar.from_dict(spec), size=64)["albedo"]
    assert np.array_equal(one, two)
    none = mg.synthesize(mg.MaterialGrammar.from_dict(
        {**base, "warp": {"intensity": 0.0}}), size=64)["albedo"]
    flat = mg.synthesize(mg.MaterialGrammar.from_dict(base), size=64)["albedo"]
    assert np.array_equal(none, flat)


def test_the_ground_grammars_stopped_reading_as_paving():
    """Roadmap 45, and the refutation that got there: the cell mosaic was
    read as the meso band and it was the `edges` crack network. A 3 m
    asphalt tile with 50 cm cracks at a quarter strength is crazy paving."""
    for name in ("asphalt_delco", "sidewalk_delco"):
        g = mg.MaterialGrammar.load(os.path.join(_PROFILES, f"{name}.json"))
        assert g.edges["cells"] <= 3, (name, g.edges)
        assert g.edges["strength"] <= 0.2, (name, g.edges)
        assert g.edges["thr"] >= 0.95, (name, g.edges)
        assert g.meso["cells"] >= 100, (name, g.meso)   # aggregate, not cobbles
        assert g.warp, name
    slab = mg.MaterialGrammar.load(os.path.join(_PROFILES, "sidewalk_delco.json"))
    assert slab.masonry["rows"] == slab.masonry["cols"] == 2   # 1.25 m squares
    assert slab.masonry["offset"] == 0.0                       # a grid, not a bond
