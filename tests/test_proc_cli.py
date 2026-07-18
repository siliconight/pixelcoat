"""CLI tests for the T03 procedural commands: proc-pack and skins-library."""

import glob
import json
import os

import pytest

from pixelcoat.cli.main import main

_PROFILES = os.path.join(os.path.dirname(__file__), "..", "profiles", "materials")


def test_proc_pack_writes_a_pack(tmp_path):
    out = tmp_path / "metal_delco"
    rc = main(["proc-pack", os.path.join(_PROFILES, "painted_metal_industrial.json"),
               "--out", str(out), "--size", "48"])
    assert rc == 0
    packs = glob.glob(str(out / "*.pack.json"))
    assert len(packs) == 1
    manifest = json.loads(open(packs[0]).read())
    assert "albedo" in manifest["maps"]
    assert (out / manifest["maps"]["albedo"]).is_file()


def test_proc_pack_refuses_overwrite_without_force(tmp_path):
    src = os.path.join(_PROFILES, "concrete_delco.json")
    out = tmp_path / "concrete_delco"
    assert main(["proc-pack", src, "--out", str(out), "--size", "32"]) == 0
    # Second run without --force is an error (returns 1).
    assert main(["proc-pack", src, "--out", str(out), "--size", "32"]) == 1
    # With --force it succeeds.
    assert main(["proc-pack", src, "--out", str(out), "--size", "32", "--force"]) == 0


def test_skins_library_lays_out_kind_theme_dirs(tmp_path):
    out = tmp_path / "skins"
    rc = main(["skins-library",
               os.path.join(_PROFILES, "painted_metal_industrial.json"),
               os.path.join(_PROFILES, "concrete_delco.json"),
               os.path.join(_PROFILES, "rubber_delco.json"),
               "--out", str(out), "--theme", "delco", "--size", "40"])
    assert rc == 0
    for kind in ("metal", "concrete", "rubber"):
        d = out / f"{kind}_delco"
        assert d.is_dir()
        assert glob.glob(str(d / "*.pack.json"))


def test_skins_library_scans_a_directory(tmp_path):
    out = tmp_path / "skins"
    rc = main(["skins-library", os.path.abspath(_PROFILES),
               "--out", str(out), "--size", "32"])
    assert rc == 0
    assert (out / "metal_delco").is_dir()


def test_signal_lenses_builds_six_packs(tmp_path):
    out = tmp_path / "lenses"
    rc = main(["signal-lenses", "--out", str(out), "--size", "32"])
    assert rc == 0
    dirs = sorted(d for d in os.listdir(out) if os.path.isdir(out / d))
    assert len(dirs) == 6
    for color in ("red", "yellow", "green"):
        for state in ("lit", "off"):
            d = out / f"lens_{color}_{state}"
            assert glob.glob(str(d / "*.pack.json"))


def test_sign_command_builds_packs(tmp_path):
    out = tmp_path / "signage"
    assert main(["sign", "--type", "neon", "--text", "OPEN",
                 "--out", str(out), "--size", "48"]) == 0
    assert main(["sign", "--type", "screen", "--mode", "terminal",
                 "--out", str(out), "--size", "48"]) == 0
    assert main(["sign", "--type", "arrow", "--direction", "up",
                 "--out", str(out), "--size", "48"]) == 0
    assert glob.glob(str(out / "sign_neon_open" / "*.pack.json"))
    assert glob.glob(str(out / "screen_terminal" / "*.pack.json"))
    assert glob.glob(str(out / "arrow_up" / "*.pack.json"))


def test_unknown_kind_warns(tmp_path, capsys):
    grammar = tmp_path / "weird.json"
    grammar.write_text(json.dumps({
        "id": "weird_alloy", "kind": "brushed_aluminum",
        "base_colors": ["#888888"], "meters_per_tile": 1.0}))
    rc = main(["proc-pack", str(grammar), "--out", str(tmp_path / "w"), "--size", "24"])
    assert rc == 0
    err = capsys.readouterr().err
    assert "brushed_aluminum" in err and "not in Zoo's known vocabulary" in err
