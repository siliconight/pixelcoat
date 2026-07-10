"""Dithering (TDD 7.8): none, bayer, floyd_steinberg for v0.1.

Grid-aligned, deterministic, and constrained to the active palette by
construction — both methods pick real palette entries per pixel, never
blended colors.
"""

from __future__ import annotations

import numpy as np

from . import quantization as q

_BAYER4 = (np.array([[0, 8, 2, 10],
                     [12, 4, 14, 6],
                     [3, 11, 1, 9],
                     [15, 7, 13, 5]], np.float32) + 0.5) / 16.0 - 0.5


def apply(rgb: np.ndarray, palette: np.ndarray, method: str,
          strength: float) -> np.ndarray:
    """Return palette-indexed RGB (H, W, 3) for the chosen method."""
    if method == "none" or strength <= 0.0:
        idx = q.map_to_palette(rgb, palette)
        return palette[idx]
    if method == "bayer":
        return _bayer(rgb, palette, strength)
    if method == "floyd_steinberg":
        return _floyd(rgb, palette, strength)
    raise ValueError(f"unknown dither method '{method}'")


def _bayer(rgb: np.ndarray, palette: np.ndarray, strength: float) -> np.ndarray:
    h, w = rgb.shape[:2]
    # Threshold offset scaled by the palette's mean neighbor spacing.
    spread = _palette_spread(palette) * strength
    ty = np.tile(_BAYER4, (h // 4 + 1, w // 4 + 1))[:h, :w]
    jittered = np.clip(rgb + ty[..., None] * spread, 0.0, 1.0)
    return palette[q.map_to_palette(jittered, palette)]


def _floyd(rgb: np.ndarray, palette: np.ndarray, strength: float) -> np.ndarray:
    lab = q.srgb_to_oklab(rgb)
    pal_lab = q.srgb_to_oklab(palette)
    h, w = lab.shape[:2]
    out = np.zeros((h, w), np.int64)
    buf = lab.copy()
    for y in range(h):
        for x in range(w):
            px = buf[y, x]
            i = int(np.argmin(np.linalg.norm(pal_lab - px, axis=1)))
            out[y, x] = i
            err = (px - pal_lab[i]) * strength
            if x + 1 < w:
                buf[y, x + 1] += err * (7 / 16)
            if y + 1 < h:
                if x > 0:
                    buf[y + 1, x - 1] += err * (3 / 16)
                buf[y + 1, x] += err * (5 / 16)
                if x + 1 < w:
                    buf[y + 1, x + 1] += err * (1 / 16)
    return palette[out]


def _palette_spread(palette: np.ndarray) -> float:
    if len(palette) < 2:
        return 0.0
    d = np.linalg.norm(palette[:, None, :] - palette[None, :, :], axis=2)
    d[d == 0] = np.inf
    return float(np.mean(d.min(axis=1)))
