"""Repeating close-range detail textures (roadmap §16).

Large Generation 7 surfaces pair a modest base texture with a small,
highly repeated detail albedo + detail normal for close-range sharpness.
This module builds that tile deterministically from one of three sources:

extracted   Crop a representative window of the working image's
            high-frequency band. The window is chosen as the candidate
            whose micro energy is closest to the median over all
            candidates — deliberately the most ORDINARY patch, because a
            unique landmark repeated 8 times per meter reads instantly
            as tiling.
procedural  Seeded multi-octave value noise — generic surface grain.
imported    A reusable authored tile, resized and wrap-repaired.

Every tile is forced wrap-continuous on both axes (a detail tile always
repeats both ways regardless of the base surface's tiling), and the
albedo is re-centered on mid-gray so overlay/linear blending is neutral
at strength 0. All arrays are linear-light float32 in [0, 1].
"""

from __future__ import annotations

import numpy as np

from . import color_space as cs
from . import frequency, image_io, maps, tiling, weathering


def build(g, lin: np.ndarray, micro_detail: np.ndarray, preset,
          warnings: list[str], wrap_x: bool = False,
          wrap_y: bool = False) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Returns (detail_albedo_tile, detail_normal_tile, detail_mask).

    Tiles are (size, size, 3); the mask is full working resolution.
    ``lin`` is the cleaned linear working image (pre-stylization, so
    palette clustering can never band the detail tile), ``micro_detail``
    the signed micro band from frequency separation.
    """
    dt = g.detail_texture
    size = int(dt.size)
    h, w = lin.shape[:2]
    if size > min(h, w):
        size = 1 << (min(h, w).bit_length() - 1)
        warnings.append(
            f"detail_texture.size {dt.size} exceeds working resolution; "
            f"clamped to {size}")

    if dt.source == "imported":
        albedo_tile, height_tile = _imported(dt.import_path, size, warnings)
    elif dt.source == "procedural":
        albedo_tile, height_tile = _procedural(size, g.weathering.seed)
    else:
        albedo_tile, height_tile = _extracted(lin, micro_detail, size)

    normal_tile = maps.normal_from_height(
        height_tile, g.normal.detail_strength * preset.detail_normal * 4.0,
        wrap_x=True, wrap_y=True, flip_g=g.normal.flip_green)

    mask = _detail_mask(micro_detail, wrap_x, wrap_y)
    return albedo_tile, normal_tile, mask


# ------------------------------------------------------------- sources

def _extracted(lin: np.ndarray, micro_detail: np.ndarray,
               size: int) -> tuple[np.ndarray, np.ndarray]:
    h, w = lin.shape[:2]
    energy = frequency.smooth_blur(np.abs(micro_detail), 8, False, False)

    # Candidate windows on a half-tile grid; keep the most ordinary one.
    stride = max(8, size // 2)
    ys = list(range(0, h - size + 1, stride)) or [0]
    xs = list(range(0, w - size + 1, stride)) or [0]
    scores = np.array([[energy[y:y + size, x:x + size].mean()
                        for x in xs] for y in ys], np.float64)
    target = float(np.median(scores))
    iy, ix = np.unravel_index(np.abs(scores - target).argmin(),
                              scores.shape)
    y0, x0 = ys[iy], xs[ix]

    window = lin[y0:y0 + size, x0:x0 + size]
    # The tile is the window's own high-frequency band, not the window:
    # broad color belongs to the base albedo, only grain repeats.
    low = frequency.smooth_blur(window, max(4, size // 8), False, False)
    hf = window - low
    tile = np.clip(0.5 + hf, 0.0, 1.0)
    tile = tiling.make_tileable_wrap(tile, "both")
    tile = _recenter(tile)

    luma_hf = cs.luminance(tile) - 0.5
    height = np.clip(0.5 + luma_hf, 0.0, 1.0)
    return tile.astype(np.float32), height.astype(np.float32)


def _procedural(size: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    grain = np.zeros((size, size), np.float32)
    amp, total = 1.0, 0.0
    for octave, cells in enumerate((8, 16, 32)):
        n = weathering.value_noise((size, size), cells, seed + 31 * octave,
                                   wrap_x=True, wrap_y=True)
        grain += amp * (n - 0.5)
        total += amp
        amp *= 0.5
    grain = grain / total * 0.5
    height = np.clip(0.5 + grain, 0.0, 1.0)
    albedo = height[..., None].repeat(3, axis=-1)
    return albedo.astype(np.float32), height.astype(np.float32)


def _imported(path: str, size: int,
              warnings: list[str]) -> tuple[np.ndarray, np.ndarray]:
    arr, _sha = image_io.load(path)
    from PIL import Image
    im = Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8),
                         "RGBA")
    if im.size != (size, size):
        warnings.append(
            f"detail_texture import {im.size[0]}x{im.size[1]} resized to "
            f"{size}x{size}")
        im = im.resize((size, size), Image.LANCZOS)
    tile = cs.srgb_to_linear(np.asarray(im, np.float32)[..., :3] / 255.0)
    tile = tiling.make_tileable_wrap(tile, "both")
    luma = cs.luminance(tile)
    height = np.clip(0.5 + (luma - float(luma.mean())), 0.0, 1.0)
    return tile.astype(np.float32), height.astype(np.float32)


# ------------------------------------------------------------- helpers

def _recenter(tile: np.ndarray) -> np.ndarray:
    """Force per-channel mean to 0.5 so neutral blending stays neutral."""
    mean = tile.reshape(-1, 3).mean(axis=0)
    return np.clip(tile + (0.5 - mean), 0.0, 1.0)


def _detail_mask(micro_detail: np.ndarray, wrap_x: bool,
                 wrap_y: bool) -> np.ndarray:
    """Full-res application mask: detail fades where the base maps already
    carry strong unique high-frequency content, so the repeating grain
    never fights real features. Wraps with the surface."""
    energy = frequency.smooth_blur(np.abs(micro_detail), 8, wrap_x, wrap_y)
    return np.clip(1.0 - 0.6 * cs.normalize01(energy),
                   0.0, 1.0).astype(np.float32)
