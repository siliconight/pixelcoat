"""Tests for pixelcoat.core.signage — the emissive focal layer."""

import json
import os

import numpy as np
import pytest

from pixelcoat.core import signage as sg


def test_render_text_shape_and_determinism():
    a = sg.render_text("EXIT", scale=3)
    b = sg.render_text("EXIT", scale=3)
    assert np.array_equal(a, b)
    assert a.shape[0] == 7 * 3                     # 5x7 font scaled
    assert a.max() == 1.0 and a.min() == 0.0       # binary ink


def test_neon_powered_glows_more_than_unpowered():
    on = sg.neon_sign("OPEN", 96, powered=True)
    off = sg.neon_sign("OPEN", 96, powered=False)
    assert on["emissive"].mean() > off["emissive"].mean()
    assert off["emissive"].max() == 0             # unpowered emits nothing


def test_panel_sign_builds():
    out = sg.panel_sign("EXIT", 96, panel="#0d2a14", text_color="#4dff7a")
    assert out["albedo"].shape == (96, 96, 3)
    assert "emissive" in out


def test_screen_modes():
    for mode in ("bars", "static", "terminal"):
        out = sg.screen(mode, 64)
        assert out["albedo"].shape == (64, 64, 3)
        assert out["emissive"].mean() > 0
    off = sg.screen("off", 64)
    assert off["emissive"].mean() < 0.2 * 255     # off screen is dark
    with pytest.raises(ValueError):
        sg.screen("hologram", 64)


def test_screen_static_is_deterministic():
    a = sg.screen("static", 64, seed=7)
    b = sg.screen("static", 64, seed=7)
    assert np.array_equal(a["emissive"], b["emissive"])


def test_hazard_has_two_tones():
    alb = sg.hazard_stripes(64)["albedo"]
    assert len(np.unique(alb.reshape(-1, 3), axis=0)) >= 2


def test_arrow_points_toward_direction():
    # A right arrow's vertex (rightmost ink column) sits in the right half.
    ink = sg.arrow(64, direction="right")["albedo"].mean(2) > 40
    rightmost = np.max(np.where(ink.any(0))[0])
    assert rightmost > 40                          # vertex reaches the right side
    with pytest.raises(ValueError):
        sg.arrow(64, direction="sideways")


def test_build_sign_pack_zoo_consumable(tmp_path):
    arrays = sg.neon_sign("BAR", 48)
    manifest = sg.build_sign_pack(str(tmp_path / "sign_neon_bar"), arrays,
                                  "sign_neon_bar")
    assert "albedo" in manifest["maps"] and "emissive" in manifest["maps"]
    assert manifest["tileable"] is None
    assert manifest["import_hints"]["extension"] == "extend"
    on_disk = json.loads((tmp_path / "sign_neon_bar" / "sign_neon_bar.pack.json").read_text())
    assert on_disk["maps"] == manifest["maps"]
