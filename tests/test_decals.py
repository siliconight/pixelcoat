"""Tests for pixelcoat.core.decals — the emissive traffic-lens generator."""

import glob
import json
import os

import numpy as np
import pytest

from pixelcoat.core import decals


def test_lens_shapes_and_dtype():
    out = decals.traffic_lens(64, color="red", state="lit")
    assert out["albedo"].shape == (64, 64, 3)
    assert out["emissive"].shape == (64, 64, 3)
    assert out["roughness"].shape == (64, 64)
    assert out["albedo"].dtype == np.uint8


def test_lit_glows_more_than_off():
    lit = decals.traffic_lens(64, color="green", state="lit")
    off = decals.traffic_lens(64, color="green", state="off")
    assert lit["emissive"].mean() > off["emissive"].mean() * 3
    assert lit["albedo"].mean() > off["albedo"].mean()


def test_lens_is_deterministic():
    a = decals.traffic_lens(48, color="yellow", state="lit")
    b = decals.traffic_lens(48, color="yellow", state="lit")
    for k in a:
        assert np.array_equal(a[k], b[k])


def test_colors_are_distinct():
    red = decals.traffic_lens(48, color="red", state="lit")["albedo"].reshape(-1, 3).mean(0)
    grn = decals.traffic_lens(48, color="green", state="lit")["albedo"].reshape(-1, 3).mean(0)
    assert red[0] > red[1] and grn[1] > grn[0]     # red is reddest, green is greenest


def test_bad_state_raises():
    with pytest.raises(ValueError):
        decals.traffic_lens(32, color="red", state="flashing")


def test_build_lens_pack_is_zoo_consumable(tmp_path):
    pack_dir = tmp_path / "signal_lens_red_lit"
    manifest = decals.build_lens_pack(str(pack_dir), color="red", state="lit", size=48)
    assert manifest["asset_id"] == "signal_lens_red_lit"
    assert "albedo" in manifest["maps"] and "emissive" in manifest["maps"]
    assert manifest["tileable"] is None            # a lens never tiles
    for fname in manifest["maps"].values():
        assert not os.path.isabs(fname)
        assert (pack_dir / fname).is_file()
    on_disk = json.loads((pack_dir / "signal_lens_red_lit.pack.json").read_text())
    assert on_disk["import_hints"]["extension"] == "extend"
