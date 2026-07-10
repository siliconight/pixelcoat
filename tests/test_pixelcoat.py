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
