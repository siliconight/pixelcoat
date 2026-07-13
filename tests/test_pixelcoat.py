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


# ------------------------------------------------------ v0.3 generation 7

from pixelcoat.core import (color_space as cs, frequency, material_response
                            as mr, tiling as tiling_mod, weathering)


@pytest.fixture
def g7_source(tmp_path):
    """Brick-ish synthetic: mortar grid + noise + a lighting gradient."""
    rng = np.random.default_rng(11)
    img = np.full((128, 128, 3), (0.55, 0.28, 0.20), np.float32)
    img += rng.normal(0, 0.04, (128, 128, 3))
    img[::32] = (0.62, 0.60, 0.55)
    img[:, ::32] = (0.62, 0.60, 0.55)
    grad = np.linspace(0.7, 1.2, 128, dtype=np.float32)[None, :, None]
    img = np.clip(img * grad, 0, 1)
    p = tmp_path / "g7src.png"
    Image.fromarray((img * 255).astype(np.uint8)).save(p)
    return str(p)


def _g7_recipe(source, preset="brick", size=128, **kw):
    r = Recipe(asset_id="g", source_path=source)
    r.processing_mode = "generation_7"
    r.generation_7.resolution.working_width = size
    r.generation_7.resolution.working_height = size
    r.generation_7.material.preset = preset
    for k, v in kw.items():
        group, attr = k.split("__")
        setattr(getattr(r.generation_7, group), attr, v)
    return r


# ----------------------------------------------------------- unit: math

def test_linear_srgb_roundtrip():
    rng = np.random.default_rng(2)
    c = rng.random((32, 32, 3)).astype(np.float32)
    assert np.allclose(cs.srgb_to_linear(cs.linear_to_srgb(c)), c, atol=2e-4)
    assert np.allclose(cs.linear_to_srgb(cs.srgb_to_linear(c)), c, atol=2e-4)


def test_wrap_blur_roll_invariant():
    rng = np.random.default_rng(3)
    a = rng.random((48, 48)).astype(np.float32)
    b1 = frequency.smooth_blur(a, 5, wrap_x=True, wrap_y=True)
    b2 = frequency.smooth_blur(np.roll(a, 13, axis=1), 5,
                               wrap_x=True, wrap_y=True)
    assert np.allclose(np.roll(b1, 13, axis=1), b2, atol=1e-4)


def test_frequency_band_reconstruction():
    rng = np.random.default_rng(4)
    luma = rng.random((64, 64)).astype(np.float32)
    _, micro = frequency.separate(luma, 12, 2, noise_threshold=0.0,
                                  detail_gain=1.0, wrap_x=False,
                                  wrap_y=False)
    micro_base = frequency.smooth_blur(luma, 2, False, False)
    assert np.allclose(micro + micro_base, luma, atol=1e-4)


def test_soft_threshold_kills_small_amplitudes():
    band = np.array([-0.05, -0.01, 0.0, 0.01, 0.05], np.float32)
    out = frequency.soft_threshold(band, 0.02)
    assert np.allclose(out, [-0.03, 0.0, 0.0, 0.0, 0.03], atol=1e-6)


def test_make_tileable_wrap_guarantees_continuity():
    rng = np.random.default_rng(0)
    base = np.linspace(0, 1, 64, np.float32)[:, None].repeat(64, axis=1)
    a = (base + 0.1 * rng.random((64, 64)).astype(np.float32)
         )[..., None].repeat(3, -1)
    out = tiling_mod.make_tileable_wrap(a, "both")
    interior_y = np.abs(np.diff(out, axis=0)).mean()
    interior_x = np.abs(np.diff(out, axis=1)).mean()
    assert np.abs(out[0] - out[-1]).mean() <= interior_y * 1.5
    assert np.abs(out[:, 0] - out[:, -1]).mean() <= interior_x * 1.5


# ------------------------------------------------------- unit: material

def test_gloss_roughness_relationship(tmp_path, g7_source):
    r = _g7_recipe(g7_source)
    pipeline.build(r, str(tmp_path / "b"))
    out = tmp_path / "b" / "g"
    gl = np.asarray(Image.open(out / "g_gloss.png"), np.int32)[..., 0]
    ro = np.asarray(Image.open(out / "g_roughness.png"), np.int32)[..., 0]
    assert np.abs((gl + ro) - 255).max() <= 1  # within one 8-bit value


def test_cavity_responds_to_synthetic_recess(tmp_path):
    img = np.full((64, 64, 3), 0.7, np.float32)
    img[28:36, :] = 0.15                       # a dark recessed channel
    p = tmp_path / "recess.png"
    Image.fromarray((img * 255).astype(np.uint8)).save(p)
    r = _g7_recipe(str(p), preset="brick", size=64,
                   color__lighting_flatten_strength=0.0,
                   cleanup__strength=0.0)
    pipeline.build(r, str(tmp_path / "b"))
    cav = np.asarray(Image.open(tmp_path / "b" / "g" / "g_cavity.png"),
                     np.float32)[..., 0] / 255
    assert cav[28:36].mean() < cav[:20].mean() - 0.05  # crevice darker


def test_wear_favors_raised_edges():
    h = np.full((64, 64), 0.3, np.float32)
    h[24:40, 24:40] = 0.9                      # raised plateau
    wear = weathering.edge_wear_mask(h, 0.5, 1999, False, False)
    edge_band = wear[22:26, 20:44].mean()      # plateau rim
    flat = wear[4:12, 4:12].mean()
    center = wear[30:34, 30:34].mean()         # raised but not an edge
    assert edge_band > flat + 0.05
    assert edge_band > center + 0.05


def test_grime_favors_cavities():
    recess = np.zeros((64, 64), np.float32)
    recess[30:34, :] = 1.0
    g = weathering.grime_mask(recess, 0.5, 1999, False, False)
    assert g[30:34].mean() > g[:20].mean() + 0.1


def test_streaks_decay_along_direction():
    src = np.zeros((64, 64), np.float32)
    src[8, 20:44] = 1.0
    s = weathering.streaks(src, 0.8, 0.9, "down", 1999, wrap=False)
    col = s[:, 32]
    assert col[9] > 0.1 and col[20] > 0.0
    assert col[9] > col[20] > col[40]          # decays downward
    assert s[:8, 32].max() == 0.0              # nothing above the source


def test_streaks_deterministic_by_seed():
    src = np.zeros((32, 32), np.float32)
    src[4] = 1.0
    a = weathering.streaks(src, 0.5, 0.9, "down", 7, wrap=False)
    b = weathering.streaks(src, 0.5, 0.9, "down", 7, wrap=False)
    c = weathering.streaks(src, 0.5, 0.9, "down", 8, wrap=False)
    assert np.array_equal(a, b) and not np.array_equal(a, c)


def test_metallic_only_from_preset_rule(tmp_path, g7_source):
    for preset, expected in (("painted_metal", True), ("concrete", False)):
        r = _g7_recipe(g7_source, preset=preset, size=64,
                       weathering__edge_wear=0.4)
        r.asset_id = preset
        report = pipeline.build(r, str(tmp_path / "b"))
        assert ("metallic" in report["maps"]) is expected


def test_wetness_isolated_to_mask(tmp_path, g7_source):
    r = _g7_recipe(g7_source, size=64, wetness__enabled=True,
                   wetness__amount=0.8)
    pipeline.build(r, str(tmp_path / "b"))
    out = tmp_path / "b" / "g"
    mask = np.asarray(Image.open(out / "g_wetness.png"),
                      np.float32)[..., 0] / 255
    dry = np.asarray(Image.open(out / "g_albedo.png"), np.int32)[..., :3]
    wet = np.asarray(Image.open(out / "g_wet_albedo.png"),
                     np.int32)[..., :3]
    dry_zone = mask < 1e-3
    if dry_zone.any():
        assert np.abs(dry[dry_zone] - wet[dry_zone]).max() <= 1
    wet_zone = mask > 0.5
    assert (wet[wet_zone].mean() < dry[wet_zone].mean())  # wet darkens
    dro = np.asarray(Image.open(out / "g_roughness.png"),
                     np.int32)[..., 0]
    wro = np.asarray(Image.open(out / "g_wet_roughness.png"),
                     np.int32)[..., 0]
    assert wro[wet_zone].mean() < dro[wet_zone].mean()    # wet smoother


# -------------------------------------------------- integration: builds

def test_dispatch_default_and_unknown_mode(g7_source):
    r = Recipe(asset_id="d", source_path=g7_source)
    assert r.processing_mode == "pixel"
    r.processing_mode = "voxel"
    with pytest.raises(ValueError):
        pipeline.build(r, "/tmp/nope")


def test_g7_pack_manifest_and_alignment(tmp_path, g7_source):
    r = _g7_recipe(g7_source, weathering__edge_wear=0.3,
                   weathering__cavity_grime=0.3, weathering__streaks=0.2)
    r.tiling.enabled = True
    r.export.meters_per_tile = 2.0
    report = pipeline.build(r, str(tmp_path / "b"))
    out = tmp_path / "b" / "g"
    pack = json.loads((out / "g.pack.json").read_text())
    assert pack["schema"] == "pixelcoat-pack/2"
    assert pack["processing_mode"] == "generation_7"
    assert pack["material_profile"] == "brick"
    assert pack["meters_per_tile"] == 2.0
    assert pack["import_hints"]["normal_format"] == "opengl"
    assert pack["import_hints"]["color_space"]["albedo"] == "srgb"
    assert pack["import_hints"]["color_space"]["normal"] == "linear"
    sizes = set()
    for fname in pack["maps"].values():
        assert (out / fname).exists()
        sizes.add(Image.open(out / fname).size)
    assert len(sizes) == 1                      # every map aligned
    assert report["warnings"] == []             # tiled build seam-clean
    for name in ("albedo", "normal", "detail_normal", "specular", "gloss",
                 "roughness", "height", "cavity", "surface_occlusion",
                 "wear", "grime"):
        assert name in pack["maps"]


def test_g7_deterministic(tmp_path, g7_source):
    r = _g7_recipe(g7_source, size=64, weathering__edge_wear=0.3,
                   weathering__streaks=0.2, color__maximum_colors=32)
    pipeline.build(r, str(tmp_path / "a"))
    pipeline.build(r, str(tmp_path / "b"))
    for f in sorted((tmp_path / "a" / "g").glob("*.png")):
        assert f.read_bytes() == \
            (tmp_path / "b" / "g" / f.name).read_bytes(), f.name


def test_g7_recipe_roundtrip(tmp_path, g7_source):
    r = _g7_recipe(g7_source, preset="wood",
                   weathering__cavity_grime=0.4, normal__flip_green=True)
    p = tmp_path / "r.json"
    r.save(str(p))
    r2 = Recipe.load(str(p))
    assert r2.processing_mode == "generation_7"
    assert r2.generation_7.material.preset == "wood"
    assert r2.generation_7.weathering.cavity_grime == 0.4
    assert r2.generation_7.normal.flip_green is True


def test_presets_differ_meaningfully(tmp_path, g7_source):
    means = {}
    for preset in ("concrete", "brick", "wood", "painted_metal"):
        r = _g7_recipe(g7_source, preset=preset, size=64)
        r.asset_id = preset
        pipeline.build(r, str(tmp_path / "b"))
        ro = np.asarray(Image.open(
            tmp_path / "b" / preset / f"{preset}_roughness.png"),
            np.float32)[..., 0].mean()
        means[preset] = ro
    vals = sorted(means.values())
    assert all(b - a > 5 for a, b in zip(vals, vals[1:])), means


def test_pixel_pack_gains_mode_field(tmp_path, source):
    r = _recipe(source)
    pipeline.build(r, str(tmp_path / "b"))
    pack = json.loads((tmp_path / "b" / "t" / "t.pack.json").read_text())
    assert pack["schema"] == "pixelcoat-pack/1"   # unchanged for pixel
    assert pack["processing_mode"] == "pixel"     # additive


def test_v02_recipe_defaults_to_pixel(tmp_path, source):
    raw = {"schema_version": "0.2", "asset_id": "old",
           "source": {"path": source},
           "pixel": {"working_width": 32, "working_height": 32}}
    r = Recipe.from_dict(raw)
    assert r.processing_mode == "pixel"
    report = pipeline.build(r, str(tmp_path / "b"))
    assert report["processing_mode"] == "pixel"


def test_g7_slice4_validation(g7_source):
    r = _g7_recipe(g7_source)
    r.generation_7.detail_texture.enabled = True
    r.generation_7.detail_texture.source = "telepathy"
    with pytest.raises(ValueError, match="source"):
        r.validate()
    r = _g7_recipe(g7_source)
    r.generation_7.detail_texture.enabled = True
    r.generation_7.detail_texture.source = "imported"
    with pytest.raises(ValueError, match="import_path"):
        r.validate()
    r = _g7_recipe(g7_source)
    r.generation_7.preview.compression_preview = "jpeg"
    with pytest.raises(ValueError, match="compression_preview"):
        r.validate()


def test_g7_imported_height(tmp_path, g7_source):
    hmap = np.zeros((128, 128), np.float32)
    hmap[:, 64:] = 1.0
    p = tmp_path / "h.png"
    Image.fromarray((hmap * 255).astype(np.uint8)).save(p)
    r = _g7_recipe(g7_source, height__source="imported",
                   height__import_path=str(p), size=128)
    pipeline.build(r, str(tmp_path / "b"))
    out = np.asarray(Image.open(tmp_path / "b" / "g" / "g_height.png"),
                     np.float32)[..., 0]
    assert out[:, 80:].mean() > out[:, :48].mean() + 30


def test_g7_resolution_warnings(tmp_path, g7_source):
    r = _g7_recipe(g7_source, size=98)          # not pow2, not mult of 4
    report = pipeline.build(r, str(tmp_path / "b"))
    joined = " ".join(report["warnings"])
    assert "power of two" in joined
    assert "multiple of four" in joined


def test_cli_g7_process_with_profile(tmp_path, g7_source):
    env = dict(os.environ, PYTHONPATH=os.getcwd())
    out = tmp_path / "cli_g7"
    res = subprocess.run(
        [sys.executable, "-m", "pixelcoat.cli.main", "process", g7_source,
         "--mode", "generation_7",
         "--profile", "profiles/generation_7/concrete.json",
         "--width", "64", "--height", "64", "--tile", "both",
         "--output", str(out), "--json"],
        capture_output=True, text=True, env=env)
    assert res.returncode == 0, res.stderr
    report = json.loads(res.stdout)
    assert report["processing_mode"] == "generation_7"
    assert report["material_profile"] == "concrete"
    recipe_path = out / report["asset_id"] / \
        f"{report['asset_id']}.pixelcoat.json"
    res2 = subprocess.run(
        [sys.executable, "-m", "pixelcoat.cli.main", "validate",
         str(recipe_path)], capture_output=True, text=True, env=env)
    assert res2.returncode == 0, res2.stdout + res2.stderr


# ------------------------------------------------------ v0.4 slice 4

from pixelcoat.core import preview as pv_mod


def test_detail_tiles_and_mask(tmp_path, g7_source):
    r = _g7_recipe(g7_source)
    r.generation_7.detail_texture.enabled = True
    r.generation_7.detail_texture.size = 64
    report = pipeline.build(r, str(tmp_path / "b"))
    out = tmp_path / "b" / "g"
    pack = json.loads((out / "g.pack.json").read_text())
    for key in ("detail_albedo", "detail_normal", "detail_mask"):
        assert key in pack["maps"]
    da = Image.open(out / "g_detail_albedo.png")
    dn = Image.open(out / "g_detail_normal.png")
    assert da.size == (64, 64) and dn.size == (64, 64)  # unpadded tiles
    mask = Image.open(out / "g_detail_mask.png")
    assert mask.size == Image.open(out / "g_albedo.png").size
    # tile seam sits inside the distribution of interior row/col pairs
    # (same p99 test the pipeline applies) + mean-neutral for blending
    a = np.asarray(da, np.float32)[..., :3] / 255
    pairs_y = np.abs(np.diff(a, axis=0)).mean(axis=(1, 2))
    pairs_x = np.abs(np.diff(a, axis=1)).mean(axis=(0, 2))
    assert np.abs(a[0] - a[-1]).mean() <= \
        max(1.5 * np.percentile(pairs_y, 99), 2.5 / 255)
    assert np.abs(a[:, 0] - a[:, -1]).mean() <= \
        max(1.5 * np.percentile(pairs_x, 99), 2.5 / 255)
    assert abs(cs.srgb_to_linear(a).mean() - 0.5) < 0.1  # linear-neutral
    assert pack["detail"]["repeats_per_meter"] == 8.0
    assert pack["import_hints"]["wet_detail_strength_scale"] == 0.3
    assert not report["warnings"]


def test_detail_off_keeps_v03_outputs(tmp_path, g7_source):
    r1 = _g7_recipe(g7_source, weathering__edge_wear=0.3)
    pipeline.build(r1, str(tmp_path / "a"))
    r2 = _g7_recipe(g7_source, weathering__edge_wear=0.3)
    r2.generation_7.detail_texture.enabled = True
    pipeline.build(r2, str(tmp_path / "b"))
    base = np.asarray(Image.open(tmp_path / "a" / "g" / "g_albedo.png"))
    with_dt = np.asarray(Image.open(tmp_path / "b" / "g" / "g_albedo.png"))
    assert np.array_equal(base, with_dt)      # albedo untouched by detail


def test_previews_do_not_change_canonical_outputs(tmp_path, g7_source):
    r1 = _g7_recipe(g7_source, size=64)
    pipeline.build(r1, str(tmp_path / "a"))
    r2 = _g7_recipe(g7_source, size=64)
    r2.generation_7.preview.generate_mipmaps = True
    r2.generation_7.preview.compression_preview = "legacy_bc"
    report = pipeline.build(r2, str(tmp_path / "b"))
    for f in sorted((tmp_path / "a" / "g").glob("*.png")):
        assert f.read_bytes() == \
            (tmp_path / "b" / "g" / f.name).read_bytes(), f.name
    pdir = tmp_path / "b" / "g" / "previews"
    assert (pdir / report["preview"]["mip_strips"]["albedo"]).exists()
    assert (pdir / report["preview"]["compression"]["normal"]["file"]
            ).exists()
    assert report["preview"]["compression"]["normal"]["family"] == \
        "two_channel"
    assert report["preview"]["compression"]["albedo"]["family"] in (
        "color_block", "color_alpha")


def test_bc1_reduces_to_four_colors_per_block():
    rng = np.random.default_rng(9)
    a = rng.random((16, 16, 3)).astype(np.float32)
    out = pv_mod.preview_block_compression(a, "color_block")
    block = out[:4, :4].reshape(-1, 3)
    assert len(np.unique(block, axis=0)) <= 4


def test_bc5_reconstructs_unit_normals():
    rng = np.random.default_rng(10)
    vec = rng.normal(size=(32, 32, 3)).astype(np.float32)
    vec[..., 2] = np.abs(vec[..., 2]) + 0.5
    vec /= np.linalg.norm(vec, axis=-1, keepdims=True)
    enc = (vec * 0.5 + 0.5).astype(np.float32)
    out = pv_mod.preview_block_compression(enc, "two_channel")
    dec = out * 2.0 - 1.0
    ln = np.linalg.norm(dec, axis=-1)
    assert np.abs(ln - 1.0).max() < 0.02      # renormalized
    assert (dec[..., 2] >= 0).all()           # Z reconstructed positive


def test_mip_chain_renormalizes_and_flags_noise():
    rng = np.random.default_rng(12)
    noisy = rng.random((128, 128, 3)).astype(np.float32)
    levels, lengths = pv_mod.mip_chain(noisy, is_normal=True)
    assert lengths[3] < 0.82                  # shimmer metric triggers
    vec = levels[3] * 2.0 - 1.0
    assert np.abs(np.linalg.norm(vec, axis=-1) - 1.0).max() < 1e-3
    flat = np.zeros((64, 64, 3), np.float32)
    flat[..., 2] = 1.0
    _, flat_lengths = pv_mod.mip_chain((flat * 0.5 + 0.5), is_normal=True)
    assert min(flat_lengths) > 0.98           # clean normal stays long


def test_procedural_and_imported_detail(tmp_path, g7_source):
    r = _g7_recipe(g7_source)
    r.generation_7.detail_texture.enabled = True
    r.generation_7.detail_texture.source = "procedural"
    r.generation_7.detail_texture.size = 64
    pipeline.build(r, str(tmp_path / "a"))
    proc = np.asarray(Image.open(tmp_path / "a" / "g" /
                                 "g_detail_albedo.png"))

    tile_src = tmp_path / "tile.png"
    rng = np.random.default_rng(3)
    Image.fromarray((rng.random((96, 96, 3)) * 255).astype(np.uint8)) \
        .save(tile_src)
    r = _g7_recipe(g7_source)
    r.generation_7.detail_texture.enabled = True
    r.generation_7.detail_texture.source = "imported"
    r.generation_7.detail_texture.import_path = str(tile_src)
    r.generation_7.detail_texture.size = 64
    report = pipeline.build(r, str(tmp_path / "b"))
    imp = np.asarray(Image.open(tmp_path / "b" / "g" /
                                "g_detail_albedo.png"))
    assert imp.shape[:2] == (64, 64)
    assert not np.array_equal(proc, imp)
    assert any("resized" in w for w in report["warnings"])


def test_landmark_warning_on_unique_feature(tmp_path):
    rng = np.random.default_rng(6)
    img = 0.45 + 0.05 * rng.random((256, 256, 3)).astype(np.float32)
    img[96:160, 96:160] = 0.95                # one glaring landmark
    p = tmp_path / "landmark.png"
    Image.fromarray((img * 255).astype(np.uint8)).save(p)
    r = _g7_recipe(str(p), size=256)
    r.tiling.enabled = True
    report = pipeline.build(r, str(tmp_path / "b"))
    assert any("landmark" in w for w in report["warnings"])


def test_cli_preview_compression(tmp_path, g7_source):
    r = _g7_recipe(g7_source, size=64)
    pipeline.build(r, str(tmp_path / "b"))
    pack = tmp_path / "b" / "g" / "g.pack.json"
    env = dict(os.environ, PYTHONPATH=os.getcwd())
    res = subprocess.run(
        [sys.executable, "-m", "pixelcoat.cli.main", "preview-compression",
         str(pack), "--profile", "legacy_bc"],
        capture_output=True, text=True, env=env)
    assert res.returncode == 0, res.stderr
    pdir = tmp_path / "b" / "g" / "previews" / "compression"
    assert (pdir / "g_albedo_bc.png").exists()
    assert (pdir / "g_normal_bc.png").exists()
    # canonical pack untouched
    assert json.loads(pack.read_text())["schema"] == "pixelcoat-pack/2"


# ------------------------------------------------------ v0.5 slice 5

def test_variations_validation(g7_source):
    r = _g7_recipe(g7_source)
    r.generation_7.variations = ["darker", "sparkly"]
    with pytest.raises(ValueError, match="variation"):
        r.validate()


def test_variation_exports(tmp_path, g7_source):
    r = _g7_recipe(g7_source, preset="painted_metal", size=64,
                   weathering__edge_wear=0.3,
                   weathering__cavity_grime=0.3, weathering__streaks=0.2)
    r.generation_7.variations = ["darker", "lighter", "dirtier", "damaged"]
    pipeline.build(r, str(tmp_path / "b"))
    out = tmp_path / "b" / "g"
    pack = json.loads((out / "g.pack.json").read_text())
    assert pack["variants"] == ["damaged", "darker", "dirtier", "lighter"]
    base = np.asarray(Image.open(out / "g_albedo.png"),
                      np.float32)[..., :3]
    dark = np.asarray(Image.open(out / "g_albedo_darker.png"),
                      np.float32)[..., :3]
    light = np.asarray(Image.open(out / "g_albedo_lighter.png"),
                       np.float32)[..., :3]
    assert dark.mean() < base.mean() < light.mean()
    assert dark.shape == base.shape            # same UV boundaries
    for v in ("dirtier", "damaged"):           # gloss shifted -> roughness
        assert (out / f"g_roughness_{v}.png").exists()


def test_variations_off_keeps_outputs(tmp_path, g7_source):
    r1 = _g7_recipe(g7_source, size=64, weathering__edge_wear=0.3)
    pipeline.build(r1, str(tmp_path / "a"))
    r2 = _g7_recipe(g7_source, size=64, weathering__edge_wear=0.3)
    r2.generation_7.variations = ["darker"]
    pipeline.build(r2, str(tmp_path / "b"))
    for f in sorted((tmp_path / "a" / "g").glob("*.png")):
        assert f.read_bytes() == \
            (tmp_path / "b" / "g" / f.name).read_bytes(), f.name


def test_variation_recipe_roundtrip(tmp_path, g7_source):
    r = _g7_recipe(g7_source)
    r.generation_7.variations = ["dirtier"]
    p = tmp_path / "r.json"
    r.save(str(p))
    assert Recipe.load(str(p)).generation_7.variations == ["dirtier"]


def test_godot_addon_files_sane():
    base = "integrations/godot/addons/pixelcoat_importer"
    cfg = open(f"{base}/plugin.cfg").read()
    assert 'script="pixelcoat_importer.gd"' in cfg
    plugin = open(f"{base}/pixelcoat_importer.gd").read()
    assert plugin.startswith("@tool")
    assert "add_tool_menu_item" in plugin and \
        "remove_tool_menu_item" in plugin
    imp = open(f"{base}/pack_importer.gd").read()
    assert imp.startswith("@tool")
    for needle in ("import_pack", "roughness/src_normal",
                   "compress/normal_map", "normal_map_invert_y",
                   "DETAIL_UV_2", "uv2_scale", "wet_albedo",
                   "surface_occlusion"):
        assert needle in imp, needle
    # metadata-driven, never filename guessing
    assert 'maps[' in imp and ".png\"" not in imp


def test_blender_addon_parses_and_covers_maps():
    import ast
    src = open("integrations/blender/pixelcoat_import.py").read()
    tree = ast.parse(src)                      # syntax-valid python
    names = {n.name for n in ast.walk(tree)
             if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    assert {"build_material", "register", "unregister",
            "IMPORT_OT_pixelcoat_pack"} <= names
    for needle in ("Non-Color", "wet_albedo", "normal_format",
                   "repeats_per_meter", "detail_mask",
                   "wet_detail_strength_scale"):
        assert needle in src, needle


# --------------------------------------------- v0.6 simplification/masks

from pixelcoat.core import simplification as simp, transforms as tf


def test_edge_aware_downsample_keeps_boundaries_crisp():
    # boundary at a 25/75 cell split: box smears, edge-aware commits to
    # the majority side (a 50/50 split would be genuinely ambiguous)
    src = np.zeros((256, 256, 4), np.float32)
    src[..., 3] = 1.0
    src[:, :98, :3] = (0.9, 0.1, 0.1)
    src[:, 98:, :3] = (0.1, 0.1, 0.9)
    box = tf.downsample(src, (32, 32), "box")
    ea = tf.downsample(src, (32, 32), "edge_aware", edge_preserve=1.0)

    def mud(a):  # pixels that are neither source tone
        d_red = np.abs(a[..., :3] - (0.9, 0.1, 0.1)).sum(-1)
        d_blue = np.abs(a[..., :3] - (0.1, 0.1, 0.9)).sum(-1)
        return int((np.minimum(d_red, d_blue) > 0.3).sum())

    assert mud(ea) < mud(box)
    assert mud(ea) == 0                        # fully committed at 1.0


def test_edge_aware_low_strength_approaches_box():
    rng = np.random.default_rng(4)
    src = rng.random((128, 128, 4)).astype(np.float32)
    src[..., 3] = 1.0
    box = tf.downsample(src, (32, 32), "box")
    soft = tf.downsample(src, (32, 32), "edge_aware", edge_preserve=0.0)
    assert np.abs(soft - box).mean() < 0.03


def test_island_removal_end_to_end(tmp_path, source):
    rng = np.random.default_rng(8)
    img = np.zeros((128, 128, 3), np.float32)
    img[:, :64] = (0.85, 0.1, 0.1)
    img[:, 64:] = (0.1, 0.1, 0.85)
    speck = rng.random((128, 128)) > 0.995     # isolated bright specks
    img[speck] = (1.0, 1.0, 0.2)
    p = tmp_path / "specks.png"
    Image.fromarray((img * 255).astype(np.uint8)).save(p)

    def build(island):
        r = _recipe(str(p))
        r.pixel.working_width = 64
        r.pixel.working_height = 64
        r.pixel.downsample_method = "nearest"  # keep specks alive
        r.palette.max_colors = 8
        r.simplification.island_removal = island
        r.asset_id = f"i{island}"
        pipeline.build(r, str(tmp_path / "b"))
        return np.asarray(Image.open(
            tmp_path / "b" / f"i{island}" / f"i{island}_albedo.png"))

    dirty = build(0)
    clean = build(3)
    yellow = lambda a: int(((a[..., 0] > 180) & (a[..., 1] > 180)).sum())
    assert yellow(dirty) > 0
    assert yellow(clean) < yellow(dirty) * 0.2  # specks dissolved


def test_protected_mask_preserves_detail(tmp_path):
    # background 0.70 and band 0.78 collapse into the SAME value band
    # (2 bands: both round to 1), so banding erases the band — unless
    # the protected mask keeps it.
    img = np.full((128, 128, 3), 0.70, np.float32)
    img[60:68, :] = 0.78                       # subtle detail band
    p = tmp_path / "subtle.png"
    Image.fromarray((img * 255).astype(np.uint8)).save(p)
    mask = np.zeros((128, 128), np.uint8)
    mask[56:72, :] = 255
    mp = tmp_path / "mask.png"
    Image.fromarray(mask).save(mp)

    def band_contrast(mask_path, aid):
        r = _recipe(str(p))
        r.asset_id = aid
        r.pixel.working_width = 128
        r.pixel.working_height = 128
        r.simplification.value_bands = 2
        r.simplification.protected_mask = mask_path
        r.palette.max_colors = 8
        pipeline.build(r, str(tmp_path / "b"))
        a = np.asarray(Image.open(tmp_path / "b" / aid /
                                  f"{aid}_albedo.png"), np.float32)
        return abs(a[60:68, :, 0].mean() - a[10:40, :, 0].mean())

    assert band_contrast(None, "raw") < 2      # banding erased it
    assert band_contrast(str(mp), "prot") > 8  # mask kept it


def test_emissive_mask_mode(tmp_path, source):
    mask = np.zeros((32, 32), np.uint8)
    mask[8:16, 8:16] = 255
    mp = tmp_path / "em.png"
    Image.fromarray(mask).save(mp)
    r = _recipe(source)
    r.maps.emissive_mode = "mask"
    r.maps.emissive_mask_path = str(mp)
    report = pipeline.build(r, str(tmp_path / "b"))
    assert "emissive" in report["maps"]
    em = np.asarray(Image.open(tmp_path / "b" / "t" / "t_emissive.png"))
    assert em[..., 0].max() == 255 and em[..., 0].min() == 0
    r2 = _recipe(source)
    r2.maps.emissive_mode = "mask"
    with pytest.raises(ValueError, match="emissive_mask_path"):
        r2.validate()


def test_v06_defaults_keep_pixel_bytes(tmp_path, source):
    r = _recipe(source)
    r.dither.method = "bayer"
    r.tiling.enabled = True
    pipeline.build(r, str(tmp_path / "a"))
    r2 = Recipe.from_dict(r.to_dict())         # 0.6 round trip
    r2.asset_id = "t"
    pipeline.build(r2, str(tmp_path / "b"))
    for f in sorted((tmp_path / "a" / "t").glob("*.png")):
        assert f.read_bytes() == \
            (tmp_path / "b" / "t" / f.name).read_bytes()


# --------------------------------------------------- v0.7 alpha / decals

from pixelcoat.core import alpha as alpha_mod


@pytest.fixture
def keyed_source(tmp_path):
    """Magenta background, red square subject, thin blue border detail."""
    img = np.zeros((128, 128, 3), np.float32)
    img[:] = (1.0, 0.0, 1.0)                   # magenta key
    img[32:96, 32:96] = (0.8, 0.1, 0.1)        # subject
    img[32:36, 32:96] = (0.1, 0.2, 0.9)        # top border detail
    p = tmp_path / "keyed.png"
    Image.fromarray((img * 255).astype(np.uint8)).save(p)
    return str(p)


def _decal_recipe(src, **alpha_kw):
    r = _recipe(src)
    r.pixel.working_width = 64
    r.pixel.working_height = 64
    r.palette.max_colors = 8
    r.alpha.source = alpha_kw.pop("source", "color_key")
    for k, v in alpha_kw.items():
        setattr(r.alpha, k, v)
    r.export.type = "decal"
    return r


def test_color_key_decal_end_to_end(tmp_path, keyed_source):
    r = _decal_recipe(keyed_source, color_key="#ff00ff")
    r.export.padding = 4
    report = pipeline.build(r, str(tmp_path / "b"))
    out = tmp_path / "b" / "t"
    pack = json.loads((out / "t.pack.json").read_text())
    assert pack["export_type"] == "decal"
    assert pack["maps"]["albedo"] == "t_decal.png"   # TDD 8.2 naming
    a = np.asarray(Image.open(out / "t_decal.png"), np.float32) / 255
    assert a.shape[2] == 4
    # background transparent, subject opaque
    assert a[36, 36, 3] == 1.0
    assert a[4, 4, 3] == 0.0
    # padding transparent (not extruded alpha)
    assert a[:4, :, 3].max() == 0.0 and a[:, :4, 3].max() == 0.0
    assert "final_color_count" in report


def test_transparent_rgb_has_no_fringe(tmp_path, keyed_source):
    r = _decal_recipe(keyed_source, color_key="#ff00ff")
    pipeline.build(r, str(tmp_path / "b"))
    a = np.asarray(Image.open(tmp_path / "b" / "t" / "t_decal.png"),
                   np.float32) / 255
    transparent = a[..., 3] == 0
    # acceptance: no magenta left behind under transparent pixels
    rgb = a[..., :3][transparent]
    magenta_like = (rgb[:, 0] > 0.6) & (rgb[:, 1] < 0.3) & (rgb[:, 2] > 0.6)
    assert magenta_like.sum() == 0


def test_pixel_hard_alpha_is_binary(tmp_path, keyed_source):
    r = _decal_recipe(keyed_source, color_key="#ff00ff", feather=6.0,
                      pixel_hard=True)
    pipeline.build(r, str(tmp_path / "b"))
    a = np.asarray(Image.open(tmp_path / "b" / "t" / "t_decal.png"))
    assert set(np.unique(a[..., 3])) <= {0, 255}
    r2 = _decal_recipe(keyed_source, color_key="#ff00ff", feather=6.0,
                       pixel_hard=False, cutoff=0.1)
    r2.asset_id = "soft"
    pipeline.build(r2, str(tmp_path / "b"))
    a2 = np.asarray(Image.open(tmp_path / "b" / "soft" / "soft_decal.png"))
    assert len(np.unique(a2[..., 3])) > 2      # soft edge survives


def test_alpha_dilate_grows_coverage(tmp_path, keyed_source):
    def coverage(dilate, aid):
        r = _decal_recipe(keyed_source, color_key="#ff00ff", dilate=dilate)
        r.asset_id = aid
        pipeline.build(r, str(tmp_path / "b"))
        a = np.asarray(Image.open(tmp_path / "b" / aid /
                                  f"{aid}_decal.png"))
        return int((a[..., 3] > 0).sum())
    assert coverage(2, "d2") > coverage(0, "d0")


def test_luminance_and_mask_sources(tmp_path):
    img = np.zeros((64, 64, 3), np.float32)
    img[16:48, 16:48] = 0.9                    # bright subject on black
    p = tmp_path / "lum.png"
    Image.fromarray((img * 255).astype(np.uint8)).save(p)
    r = _decal_recipe(str(p), source="luminance", luminance_threshold=0.5)
    pipeline.build(r, str(tmp_path / "b"))
    a = np.asarray(Image.open(tmp_path / "b" / "t" / "t_decal.png"))
    assert a[32, 32, 3] == 255 and a[4, 4, 3] == 0

    mask = np.zeros((64, 64), np.uint8)
    mask[:, 32:] = 255
    mp = tmp_path / "amask.png"
    Image.fromarray(mask).save(mp)
    r2 = _decal_recipe(str(p), source="mask", mask_path=str(mp))
    r2.asset_id = "m"
    pipeline.build(r2, str(tmp_path / "b"))
    a2 = np.asarray(Image.open(tmp_path / "b" / "m" / "m_decal.png"))
    assert a2[32, 48, 3] == 255 and a2[32, 8, 3] == 0


def test_flood_select_keeps_enclosed_holes(tmp_path):
    # ring subject: the enclosed center matches the background color but
    # is NOT corner-connected, so flood must keep it opaque
    img = np.zeros((96, 96, 3), np.float32)
    img[:] = (0.2, 0.6, 0.2)                   # background
    img[24:72, 24:72] = (0.8, 0.2, 0.1)        # subject block
    img[40:56, 40:56] = (0.2, 0.6, 0.2)        # enclosed hole, bg color
    p = tmp_path / "ring.png"
    Image.fromarray((img * 255).astype(np.uint8)).save(p)
    r = _decal_recipe(str(p), source="flood", flood_tolerance=0.08)
    pipeline.build(r, str(tmp_path / "b"))
    a = np.asarray(Image.open(tmp_path / "b" / "t" / "t_decal.png"))
    assert a[4, 4, 3] == 0                     # background gone
    assert a[32, 32, 3] == 255                 # enclosed center kept


def test_premultiplied_export(tmp_path, keyed_source):
    r = _decal_recipe(keyed_source, color_key="#ff00ff",
                      premultiplied=True)
    pipeline.build(r, str(tmp_path / "b"))
    a = np.asarray(Image.open(tmp_path / "b" / "t" / "t_decal.png"))
    transparent = a[..., 3] == 0
    assert a[..., :3][transparent].max() == 0  # premult: rgb*0 = 0


def test_decal_requires_alpha_source(tmp_path, source):
    r = _recipe(source)
    r.export.type = "decal"
    with pytest.raises(ValueError, match="alpha source"):
        r.validate()


def test_v07_defaults_keep_pixel_bytes(tmp_path, source):
    r = _recipe(source)
    r.dither.method = "bayer"
    r.tiling.enabled = True
    pipeline.build(r, str(tmp_path / "a"))
    r2 = Recipe.from_dict(r.to_dict())
    r2.asset_id = "t"
    pipeline.build(r2, str(tmp_path / "b"))
    for f in sorted((tmp_path / "a" / "t").glob("*.png")):
        assert f.read_bytes() == \
            (tmp_path / "b" / "t" / f.name).read_bytes()


def test_cli_decal(tmp_path, keyed_source):
    env = dict(os.environ, PYTHONPATH=os.getcwd())
    out = tmp_path / "cli"
    res = subprocess.run(
        [sys.executable, "-m", "pixelcoat.cli.main", "process",
         keyed_source, "--width", "64", "--height", "64",
         "--alpha", "color_key", "--alpha-key", "#ff00ff",
         "--alpha-feather", "2", "--decal",
         "--output", str(out), "--json"],
        capture_output=True, text=True, env=env)
    assert res.returncode == 0, res.stderr
    report = json.loads(res.stdout)
    aid = report["asset_id"]
    assert (out / aid / f"{aid}_decal.png").exists()


# ---------------------------------------------------------- v0.8 atlas

from pixelcoat.core import atlas as atlas_mod


@pytest.fixture
def three_packs(tmp_path):
    """Three decal packs of different sizes (one tall for rotation)."""
    rng = np.random.default_rng(15)
    paths = []
    for aid, (w, h), color in (("poster", (48, 48), (0.8, 0.2, 0.2)),
                               ("sign", (32, 32), (0.2, 0.8, 0.2)),
                               ("banner", (24, 64), (0.2, 0.2, 0.8))):
        img = np.full((128, 128, 3), (1.0, 0.0, 1.0), np.float32)
        img[16:112, 16:112] = color
        img[20:40, 20:60] += rng.normal(0, 0.05, (20, 40, 3))
        p = tmp_path / f"{aid}.png"
        Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)) \
            .save(p)
        r = _recipe(str(p))
        r.asset_id = aid
        r.pixel.working_width = w
        r.pixel.working_height = h
        r.palette.max_colors = 6
        r.alpha.source = "color_key"
        r.alpha.color_key = "#ff00ff"
        r.export.type = "decal"
        pipeline.build(r, str(tmp_path / "packs"))
        paths.append(str(tmp_path / "packs" / aid / f"{aid}.pack.json"))
    return paths


def test_atlas_end_to_end(tmp_path, three_packs):
    report = atlas_mod.build_atlas(three_packs, "city01",
                                   str(tmp_path / "out"), gutter=2)
    out = tmp_path / "out" / "city01"
    man = json.loads((out / "city01_atlas.json").read_text())
    assert man["schema_version"] == "pixelcoat-atlas/1"
    assert len(man["entries"]) == 3
    aw, ah = man["width"], man["height"]
    atlas_alb = np.asarray(Image.open(
        out / man["maps"]["albedo"]), np.float32) / 255.0
    assert atlas_alb.shape[:2] == (ah, aw)

    # no overlaps
    cover = np.zeros((ah, aw), np.int32)
    for e in man["entries"]:
        x, y, w, h = e["rect_px"]
        cover[y:y + h, x:x + w] += 1
    assert cover.max() == 1

    # rects crop back to exact source pixels (rotation honored)
    for e in man["entries"]:
        x, y, w, h = e["rect_px"]
        crop = atlas_alb[y:y + h, x:x + w]
        pack_dir = os.path.dirname(three_packs[0]).replace(
            "poster", e["id"])
        src_pack = json.loads(open(os.path.join(
            os.path.dirname(os.path.dirname(three_packs[0])),
            e["id"], e["source_pack"])).read())
        src_img = np.asarray(Image.open(os.path.join(
            os.path.dirname(os.path.dirname(three_packs[0])), e["id"],
            src_pack["maps"]["albedo"])).convert("RGBA"),
            np.float32) / 255.0
        if e["rotated"]:
            src_img = np.rot90(src_img, k=-1)
        assert np.abs(crop - src_img).max() < 1 / 254.0, e["id"]

    # uv consistent with rect
    e0 = man["entries"][0]
    assert abs(e0["uv"][0] - e0["rect_px"][0] / aw) < 1e-9
    assert report["occupancy"] > 0.3
    assert (out / "city01_preview.png").exists()


def test_atlas_deterministic(tmp_path, three_packs):
    atlas_mod.build_atlas(three_packs, "a", str(tmp_path / "o1"))
    atlas_mod.build_atlas(three_packs, "a", str(tmp_path / "o2"))
    for f in sorted((tmp_path / "o1" / "a").glob("*")):
        assert f.read_bytes() == (tmp_path / "o2" / "a" / f.name) \
            .read_bytes(), f.name


def test_atlas_rotation_and_toggle(tmp_path, three_packs):
    man_r = atlas_mod.build_atlas(three_packs, "r", str(tmp_path / "o"))
    m = json.loads((tmp_path / "o" / "r" / "r_atlas.json").read_text())
    banner = next(e for e in m["entries"] if e["id"] == "banner")
    assert banner["rotated"] is True           # 24x64 -> laid on its side
    assert banner["rect_px"][2] > banner["rect_px"][3]
    atlas_mod.build_atlas(three_packs, "nr", str(tmp_path / "o"),
                          allow_rotate=False)
    m2 = json.loads((tmp_path / "o" / "nr" / "nr_atlas.json").read_text())
    banner2 = next(e for e in m2["entries"] if e["id"] == "banner")
    assert banner2["rotated"] is False


def test_atlas_pow2_and_alpha_gutter(tmp_path, three_packs):
    atlas_mod.build_atlas(three_packs, "p2", str(tmp_path / "o"),
                          gutter=4, pow2=True)
    man = json.loads((tmp_path / "o" / "p2" / "p2_atlas.json").read_text())
    assert man["width"] & (man["width"] - 1) == 0
    assert man["height"] & (man["height"] - 1) == 0
    alb = np.asarray(Image.open(
        tmp_path / "o" / "p2" / man["maps"]["albedo"]))
    # decal atlas: gutters transparent everywhere outside entry rects
    inside = np.zeros(alb.shape[:2], bool)
    for e in man["entries"]:
        x, y, w, h = e["rect_px"]
        inside[y:y + h, x:x + w] = True
    assert alb[..., 3][~inside].max() == 0
    assert all(e["alpha_mode"] == "cutout" for e in man["entries"])


def test_atlas_neutral_fill_for_missing_maps(tmp_path, three_packs, source):
    # a pack without normal/roughness joins one that has them
    r = _recipe(source)
    r.asset_id = "flat"
    r.maps.normal = False
    r.maps.roughness = False
    pipeline.build(r, str(tmp_path / "extra"))
    packs = three_packs + [str(tmp_path / "extra" / "flat" /
                               "flat.pack.json")]
    atlas_mod.build_atlas(packs, "mix", str(tmp_path / "o"))
    man = json.loads((tmp_path / "o" / "mix" / "mix_atlas.json").read_text())
    normal = np.asarray(Image.open(
        tmp_path / "o" / "mix" / man["maps"]["normal"]), np.int32)
    flat = next(e for e in man["entries"] if e["id"] == "flat")
    x, y, w, h = flat["rect_px"]
    region = normal[y:y + h, x:x + w, :3]
    assert np.abs(region - (128, 128, 255)).max() <= 1  # neutral normal


def test_atlas_rejects_mixed_modes(tmp_path, three_packs, g7_source):
    r = _g7_recipe(g7_source, size=64)
    pipeline.build(r, str(tmp_path / "g7"))
    with pytest.raises(ValueError, match="mixed processing modes"):
        atlas_mod.build_atlas(
            three_packs + [str(tmp_path / "g7" / "g" / "g.pack.json")],
            "bad", str(tmp_path / "o"))


def test_cli_atlas(tmp_path, three_packs):
    env = dict(os.environ, PYTHONPATH=os.getcwd())
    res = subprocess.run(
        [sys.executable, "-m", "pixelcoat.cli.main", "atlas",
         os.path.dirname(os.path.dirname(three_packs[0])),
         "--name", "cli01", "--output", str(tmp_path / "o"),
         "--pow2", "--json"],
        capture_output=True, text=True, env=env)
    assert res.returncode == 0, res.stderr
    report = json.loads(res.stdout)
    assert report["entries"] == 3
    assert (tmp_path / "o" / "cli01" / "cli01_atlas.json").exists()
