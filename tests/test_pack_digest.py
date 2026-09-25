"""A pack manifest says what is in the files it names.

THE DEFECT THIS CLOSES, measured 2026-09-24. A manifest named filenames and
carried no digest of their contents, so a grammar retune -- new pixels, same
metadata, which is what a material edit usually is -- left it byte-identical:

    asphalt_delco.pack.json    fd4678dbc03ab70f -> fd4678dbc03ab70f  IDENTICAL
    asphalt_delco_albedo.png   68e2fd2cb8509e28 -> 500265cbf2630a20  differs

A consumer that hashed the manifest to ask "did this material change" therefore
got the wrong answer, and Level Factory's Zoo adapter did exactly that: the kit
job cache-hit and, because Zoo BAKES these maps into a GLB, shipped the
previously baked material. LF 0.111.0 fixed that consumer; this fixes the
producer, so the next consumer does not have to know.

WHAT THESE HOLD. That the manifest moves when the pixels move; that it does not
move when they do not; that every writer states it; that the claim is checkable;
and that a reader who has never heard of `map_sha256` is unaffected.
"""

import hashlib
import json
import os

import numpy as np
import pytest

from pixelcoat.core import material_grammar as mg
from pixelcoat.core import pack as pack_meta

_PROFILES = os.path.join(os.path.dirname(__file__), "..", "profiles",
                         "materials")


def _sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def _manifest(pack_dir, asset_id):
    with open(os.path.join(pack_dir, f"{asset_id}.pack.json"),
              encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------- #
# The defect, as an assertion
# --------------------------------------------------------------------------- #

def test_a_retune_moves_the_manifest(tmp_path):
    """THE POINT OF THE WHOLE CHANGE. Same filenames, same metadata, different
    pixels -- and the manifest's bytes must move, because hashing the manifest
    is what a consumer reaches for first."""
    src = json.loads(open(os.path.join(_PROFILES, "asphalt_delco.json"),
                          encoding="utf-8").read())
    a_prof = tmp_path / "a.json"
    a_prof.write_text(json.dumps(src), encoding="utf-8")
    mg.build_material_pack(str(a_prof), str(tmp_path / "A"), size=64)

    retuned = dict(src, base_colors=["#5a3320", "#6b4028", "#4a2a18"])
    b_prof = tmp_path / "b.json"
    b_prof.write_text(json.dumps(retuned), encoding="utf-8")
    mg.build_material_pack(str(b_prof), str(tmp_path / "B"), size=64)

    man = "asphalt_delco.pack.json"
    a_albedo = _sha(tmp_path / "A" / "asphalt_delco_albedo.png")
    b_albedo = _sha(tmp_path / "B" / "asphalt_delco_albedo.png")
    assert a_albedo != b_albedo, "the retune did not change the pixels"
    assert _sha(tmp_path / "A" / man) != _sha(tmp_path / "B" / man), (
        "the albedo changed and the manifest did not -- a consumer hashing the "
        "manifest would serve the previously baked material")


def test_an_identical_rebuild_does_not_move_it(tmp_path):
    """The other half, and it is what keeps caches working: a deterministic
    rebuild must produce the same digest, or every downstream job would
    re-run on every build."""
    src = os.path.join(_PROFILES, "asphalt_delco.json")
    mg.build_material_pack(src, str(tmp_path / "A"), size=64)
    mg.build_material_pack(src, str(tmp_path / "B"), size=64)
    man = "asphalt_delco.pack.json"
    assert _sha(tmp_path / "A" / man) == _sha(tmp_path / "B" / man)


def test_the_digest_is_of_the_file_on_disk(tmp_path):
    """Read back, not asserted from memory: the digest describes the bytes a
    consumer will open."""
    mg.build_material_pack(os.path.join(_PROFILES, "asphalt_delco.json"),
                           str(tmp_path / "p"), size=64)
    m = _manifest(tmp_path / "p", "asphalt_delco")
    assert m["map_sha256"], "no digests written"
    for key, fname in m["maps"].items():
        assert m["map_sha256"][key] == _sha(tmp_path / "p" / fname), key


def test_every_map_the_manifest_names_has_one(tmp_path):
    mg.build_material_pack(os.path.join(_PROFILES, "road_paint_delco.json"),
                           str(tmp_path / "p"), size=64)
    m = _manifest(tmp_path / "p", "road_paint_delco")
    assert set(m["map_sha256"]) == set(m["maps"])


# --------------------------------------------------------------------------- #
# Checkability
# --------------------------------------------------------------------------- #

def test_verify_is_clean_on_a_pack_as_written(tmp_path):
    mg.build_material_pack(os.path.join(_PROFILES, "sidewalk_delco.json"),
                           str(tmp_path / "p"), size=64)
    m = _manifest(tmp_path / "p", "sidewalk_delco")
    assert pack_meta.verify(str(tmp_path / "p"), m) == []


def test_verify_names_a_map_that_stopped_matching(tmp_path):
    """A truncated or half-written PNG is a corrupt pack, and saying so at the
    adapter boundary beats discovering it in Blender."""
    mg.build_material_pack(os.path.join(_PROFILES, "sidewalk_delco.json"),
                           str(tmp_path / "p"), size=64)
    m = _manifest(tmp_path / "p", "sidewalk_delco")
    (tmp_path / "p" / m["maps"]["albedo"]).write_bytes(b"truncated")
    problems = pack_meta.verify(str(tmp_path / "p"), m)
    assert len(problems) == 1
    assert "albedo" in problems[0] and "does not match its digest" in problems[0]


def test_verify_names_a_map_that_went_missing(tmp_path):
    mg.build_material_pack(os.path.join(_PROFILES, "sidewalk_delco.json"),
                           str(tmp_path / "p"), size=64)
    m = _manifest(tmp_path / "p", "sidewalk_delco")
    (tmp_path / "p" / m["maps"]["roughness"]).unlink()
    problems = pack_meta.verify(str(tmp_path / "p"), m)
    assert any("roughness" in p and "not on disk" in p for p in problems)


def test_verify_says_nothing_about_a_pack_written_before_this_existed():
    """An old pack has no claim to disagree with. Reporting one as a fault
    would turn an upgrade into a wall of findings about files that are fine."""
    assert pack_meta.verify("/nowhere", {"schema": "pixelcoat-pack/1",
                                         "maps": {"albedo": "a.png"}}) == []


def test_a_missing_map_digests_as_missing_rather_than_being_dropped(tmp_path):
    """A pack that NAMES a map it did not write must not hash the same as a
    complete one -- that is the failure this module exists to stop."""
    d = pack_meta.map_sha256(str(tmp_path), {"albedo": "nope.png"})
    assert d == {"albedo": pack_meta.MISSING}


# --------------------------------------------------------------------------- #
# Additive
# --------------------------------------------------------------------------- #

def test_the_schema_version_did_not_move(tmp_path):
    """`pixelcoat-pack/2` is the additive schema, in its own writer's words:
    downstream tools that only know pack/1 keep reading maps, tileable and
    meters_per_tile the same way. A reader that has never heard of
    `map_sha256` is unaffected by it."""
    m = mg.build_material_pack(os.path.join(_PROFILES, "brick_delco.json"),
                               str(tmp_path / "p"), size=64)
    assert m["schema"] == "pixelcoat-pack/2"


def test_the_keys_zoo_resolves_are_untouched(tmp_path):
    """Zoo's `load_pack` reads exactly these (`zoo_keeper/core/skins.py`)."""
    m = mg.build_material_pack(os.path.join(_PROFILES, "brick_delco.json"),
                               str(tmp_path / "p"), size=64)
    assert m["asset_id"] == "brick_delco"
    assert "albedo" in m["maps"]
    assert m["tileable"] == ["x", "y"]
    assert isinstance(m["meters_per_tile"], float)
    assert "tintable" in m
    for fname in m["maps"].values():
        assert not os.path.isabs(fname)
        assert (tmp_path / "p" / fname).is_file()


# --------------------------------------------------------------------------- #
# Every writer, not just the one the defect was found in
# --------------------------------------------------------------------------- #

def test_the_decal_writer_states_digests(tmp_path):
    from pixelcoat.core import decals
    m = decals.build_lens_pack(str(tmp_path / "lens"), color="red",
                               state="lit", size=32)
    assert set(m["map_sha256"]) == set(m["maps"])
    assert pack_meta.verify(str(tmp_path / "lens"), m) == []


def test_the_signage_writer_states_digests(tmp_path):
    from pixelcoat.core import signage
    arrays = {"albedo": np.zeros((16, 16, 3), np.uint8),
              "emissive": np.zeros((16, 16, 3), np.uint8)}
    m = signage.build_sign_pack(str(tmp_path / "sign"), arrays, "sign_test")
    assert set(m["map_sha256"]) == set(m["maps"])
    assert pack_meta.verify(str(tmp_path / "sign"), m) == []
