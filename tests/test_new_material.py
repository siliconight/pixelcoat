"""tools/new_material.py mints a profile that synthesizes, maps it into a theme,
refuses to overwrite, and reports the kinds a theme cannot dress (roadmap 150).
"""
from __future__ import annotations

import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))

import new_material  # noqa: E402

_PROFILES = os.path.join(HERE, "..", "profiles", "materials")


def _dirs(tmp_path):
    p = tmp_path / "materials"
    t = tmp_path / "themes"
    p.mkdir()
    t.mkdir()
    shutil.copy(os.path.join(_PROFILES, "metal_rusted_street.json"), p / "metal_rusted_street.json")
    (t / "delco_1997.json").write_text(json.dumps(
        {"theme": "delco_1997", "materials": {"metal": "metal_rusted_street"}}), encoding="utf-8")
    return str(p), str(t)


def test_a_minted_profile_synthesizes_and_maps_into_the_theme(tmp_path, capsys):
    p, t = _dirs(tmp_path)
    rc = new_material.main(["new", "enamel_pump_delco", "--kind", "metal_painted",
                            "--like", "metal_rusted_street", "--colors", "#c8442a,#d95a3c,#b03a22",
                            "--theme", "delco_1997", "--profiles-dir", p, "--themes-dir", t])
    assert rc == 0
    raw = json.load(open(os.path.join(p, "enamel_pump_delco.json"), encoding="utf-8"))
    assert raw["id"] == "enamel_pump_delco" and raw["kind"] == "metal_painted"
    assert raw["base_colors"] == ["#c8442a", "#d95a3c", "#b03a22"]
    theme = json.load(open(os.path.join(t, "delco_1997.json"), encoding="utf-8"))
    assert theme["materials"]["metal_painted"] == "enamel_pump_delco"
    assert theme["materials"]["metal"] == "metal_rusted_street"
    out = capsys.readouterr().out
    assert "renders: albedo std" in out and "metal_painted_delco_1997/" in out


def test_minting_refuses_to_overwrite_and_to_take_a_mapped_kind(tmp_path, capsys):
    p, t = _dirs(tmp_path)
    base = ["--like", "metal_rusted_street", "--profiles-dir", p, "--themes-dir", t]
    assert new_material.main(["new", "rust2", "--kind", "metal", "--theme", "delco_1997", *base]) == 0
    assert "already maps 'metal'" in capsys.readouterr().out
    theme = json.load(open(os.path.join(t, "delco_1997.json"), encoding="utf-8"))
    assert theme["materials"]["metal"] == "metal_rusted_street"
    assert new_material.main(["new", "rust2", "--kind", "metal", *base]) == 2
    assert new_material.main(["new", "rust3", "--kind", "metal", "--theme", "delco_1997",
                              "--replace", *base]) == 0
    theme = json.load(open(os.path.join(t, "delco_1997.json"), encoding="utf-8"))
    assert theme["materials"]["metal"] == "rust3"


def test_bad_colours_and_missing_template_are_refused(tmp_path):
    p, t = _dirs(tmp_path)
    assert new_material.main(["new", "x", "--kind", "metal", "--colors", "red,blue",
                              "--profiles-dir", p, "--themes-dir", t]) == 2
    assert new_material.main(["new", "x", "--kind", "metal", "--like", "no_such",
                              "--profiles-dir", p, "--themes-dir", t]) == 2


def test_report_names_the_kinds_a_theme_cannot_dress(tmp_path, capsys):
    p, t = _dirs(tmp_path)
    assert new_material.main(["report", "--themes-dir", t]) == 0
    out = capsys.readouterr().out
    assert "delco_1997:" in out and "no profile" in out and "concrete" in out
