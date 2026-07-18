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
        assert "albedo" in out and out["albedo"].shape == (48, 48, 3), f
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
