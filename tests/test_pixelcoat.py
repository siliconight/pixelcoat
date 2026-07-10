"""v0.1 scaffold tests: schema, quantization, dithering, pipeline,
determinism (TDD 20.1 + 20.3 property slices)."""

import json
import os
import subprocess
import sys

import numpy as np
import pytest
from PIL import Image

from pixelcoat.recipe import Recipe
from pixelcoat.core import quantization as q
from pixelcoat.core import dithering, pipeline


@pytest.fixture
def source(tmp_path):
    rng = np.random.default_rng(7)
    img = (rng.random((96, 128, 3)) * 255).astype(np.uint8)
    img[20:60, 30:90] = (200, 40, 40)
    p = tmp_path / "src.png"
    Image.fromarray(img).save(p)
    return str(p)


def _recipe(source, **kw):
    r = Recipe(asset_id="t", source_path=source)
    r.pixel.working_width = 64
    r.pixel.working_height = 48
    for k, v in kw.items():
        obj, attr = k.split("__")
        setattr(getattr(r, obj), attr, v)
    return r


def test_recipe_roundtrip(tmp_path, source):
    r = _recipe(source, dither__method="bayer")
    p = tmp_path / "r.json"
    r.save(str(p))
    r2 = Recipe.load(str(p))
    assert r2.dither.method == "bayer"
    assert r2.pixel.working_width == 64


def test_recipe_validation_rejects_bad_dither(source):
    r = _recipe(source)
    r.dither.method = "ostrich"
    with pytest.raises(ValueError):
        r.validate()


def test_oklab_roundtrip():
    rgb = np.array([[0.2, 0.5, 0.8], [1.0, 0.0, 0.3]])
    back = q.oklab_to_srgb(q.srgb_to_oklab(rgb))
    assert np.allclose(rgb, back, atol=1e-4)


def test_palette_max_colors(source):
    arr = np.asarray(Image.open(source), np.float32) / 255.0
    pal = q.extract_palette(arr.reshape(-1, 3), 8, seed=1999)
    assert len(pal) <= 8


def test_dither_stays_in_palette():
    rng = np.random.default_rng(3)
    rgb = rng.random((16, 16, 3)).astype(np.float32)
    pal = np.array([[0, 0, 0], [1, 1, 1], [1, 0, 0]], np.float32)
    for method in ("none", "bayer", "floyd_steinberg"):
        out = dithering.apply(rgb, pal, method, 0.6)
        flat = out.reshape(-1, 3)
        d = np.linalg.norm(flat[:, None, :] - pal[None, :, :], axis=2)
        assert d.min(axis=1).max() < 1e-6


def test_pipeline_builds_pack(tmp_path, source):
    r = _recipe(source, palette__max_colors=8, export__padding=2,
                pixel__display_scale=2)
    report = pipeline.build(r, str(tmp_path / "build"))
    out = tmp_path / "build" / "t"
    assert (out / "t_albedo.png").exists()
    assert (out / "t.pixelcoat.json").exists()
    assert (out / "build_report.json").exists()
    # 64x48 working, x2 scale, +2 pad each side
    assert report["output_resolution"] == [64 * 2 + 4, 48 * 2 + 4]
    assert report["final_color_count"] <= 8


def test_deterministic(tmp_path, source):
    r = _recipe(source, dither__method="bayer")
    pipeline.build(r, str(tmp_path / "a"))
    pipeline.build(r, str(tmp_path / "b"))
    a = (tmp_path / "a" / "t" / "t_albedo.png").read_bytes()
    b = (tmp_path / "b" / "t" / "t_albedo.png").read_bytes()
    assert a == b


def test_perspective_quad(tmp_path, source):
    r = _recipe(source)
    r.transform.perspective_quad = [[30, 20], [90, 20], [90, 60], [30, 60]]
    report = pipeline.build(r, str(tmp_path / "build"))
    arr = np.asarray(Image.open(
        tmp_path / "build" / "t" / "t_albedo.png"), np.float32)
    center = arr[16:32, 16:48, :3].mean(axis=(0, 1))
    assert center[0] > 120 and center[1] < 110  # red block fills the frame


def test_cli_process_and_validate(tmp_path, source):
    env = dict(os.environ, PYTHONPATH=os.getcwd())
    out = tmp_path / "cli_build"
    res = subprocess.run(
        [sys.executable, "-m", "pixelcoat.cli.main", "process", source,
         "--width", "32", "--height", "32", "--output", str(out), "--json"],
        capture_output=True, text=True, env=env)
    assert res.returncode == 0, res.stderr
    report = json.loads(res.stdout)
    recipe_path = out / report["asset_id"] / f"{report['asset_id']}.pixelcoat.json"
    res2 = subprocess.run(
        [sys.executable, "-m", "pixelcoat.cli.main", "validate",
         str(recipe_path)], capture_output=True, text=True, env=env)
    assert res2.returncode == 0, res2.stdout + res2.stderr


# ---------------------------------------------------------------- v0.2 maps

from pixelcoat.core import maps


def test_maps_emitted_and_pack_manifest(tmp_path, source):
    r = _recipe(source, palette__max_colors=8)
    report = pipeline.build(r, str(tmp_path / "build"))
    out = tmp_path / "build" / "t"
    assert (out / "t_normal.png").exists()
    assert (out / "t_roughness.png").exists()
    pack = json.loads((out / "t.pack.json").read_text())
    assert pack["schema"] == "pixelcoat-pack/1"
    assert pack["meters_per_tile"] == 1.0
    for fname in pack["maps"].values():
        assert (out / fname).exists()
    assert set(report["maps"]) == {"albedo", "normal", "roughness"}


def test_maps_align_with_albedo(tmp_path, source):
    r = _recipe(source, export__padding=2, pixel__display_scale=2)
    pipeline.build(r, str(tmp_path / "build"))
    out = tmp_path / "build" / "t"
    a = Image.open(out / "t_albedo.png").size
    assert Image.open(out / "t_normal.png").size == a
    assert Image.open(out / "t_roughness.png").size == a


def test_normal_flat_height_is_neutral():
    n = maps.normal_from_height(np.full((8, 8), 0.5, np.float32), 2.0)
    assert np.allclose(n, [0.5, 0.5, 1.0], atol=1e-6)


def test_normal_wrap_continuity():
    rng = np.random.default_rng(9)
    h = rng.random((16, 16)).astype(np.float32)
    n = maps.normal_from_height(h, 2.0, wrap_x=True, wrap_y=True)
    n_rolled = maps.normal_from_height(
        np.roll(h, 5, axis=1), 2.0, wrap_x=True, wrap_y=True)
    assert np.allclose(np.roll(n, 5, axis=1), n_rolled, atol=1e-6)


def test_normal_opengl_green_convention():
    # Height increasing downward in image space -> OpenGL Y+ green > 0.5.
    h = np.linspace(0, 1, 16, dtype=np.float32)[:, None].repeat(16, axis=1)
    n = maps.normal_from_height(h, 2.0)
    assert (n[1:-1, :, 1] > 0.5).all()
    flipped = maps.normal_from_height(h, 2.0, flip_g=True)
    assert (flipped[1:-1, :, 1] < 0.5).all()


def test_roughness_levels_and_range():
    rng = np.random.default_rng(4)
    h = rng.random((32, 32)).astype(np.float32)
    r = maps.roughness_from_height(h, 0.6, 0.3, levels=4)
    assert r.min() >= 0.0 and r.max() <= 1.0
    assert len(np.unique(np.round(r, 6))) <= 4


def test_emissive_indices_selects_palette_entries():
    pal = np.array([[0, 0, 0], [1, 0.2, 0.1], [0.3, 0.3, 0.3]], np.float32)
    rgb = pal[np.array([[0, 1], [2, 1]])]
    e = maps.emissive_indices(rgb, pal, [1])
    assert np.allclose(e[0, 1], pal[1]) and np.allclose(e[1, 1], pal[1])
    assert np.allclose(e[0, 0], 0) and np.allclose(e[1, 0], 0)


def test_maps_deterministic(tmp_path, source):
    r = _recipe(source, dither__method="bayer")
    pipeline.build(r, str(tmp_path / "a"))
    pipeline.build(r, str(tmp_path / "b"))
    for name in ("normal", "roughness"):
        a = (tmp_path / "a" / "t" / f"t_{name}.png").read_bytes()
        b = (tmp_path / "b" / "t" / f"t_{name}.png").read_bytes()
        assert a == b


def test_v01_recipe_still_builds(tmp_path, source):
    raw = {"schema_version": "0.1", "asset_id": "old",
           "source": {"path": source},
           "pixel": {"working_width": 32, "working_height": 32}}
    r = Recipe.from_dict(raw)
    report = pipeline.build(r, str(tmp_path / "build"))
    assert "normal" in report["maps"]          # 0.2 defaults apply
    assert (tmp_path / "build" / "old" / "old.pack.json").exists()
