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
