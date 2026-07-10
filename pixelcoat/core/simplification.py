"""Pre-quantization simplification (TDD 7.4) — v0.1 slice.

Noise reduction (iterated 3x3 median) and value banding (7.6's two-to-N tone
grouping applied in luma while keeping chroma). Edge-aware machinery lands
in a later minor; the stage boundary and recipe fields are already here so
recipes stay forward-compatible.
"""

from __future__ import annotations

import numpy as np


def noise_reduce(arr: np.ndarray, strength: float) -> np.ndarray:
    """0..1 strength -> 0..3 median passes on RGB (alpha untouched)."""
    passes = int(round(np.clip(strength, 0.0, 1.0) * 3))
    out = arr.copy()
    for _ in range(passes):
        out[..., :3] = _median3(out[..., :3])
    return out


def _median3(rgb: np.ndarray) -> np.ndarray:
    p = np.pad(rgb, ((1, 1), (1, 1), (0, 0)), mode="edge")
    stack = [p[y:y + rgb.shape[0], x:x + rgb.shape[1]]
             for y in range(3) for x in range(3)]
    return np.median(np.stack(stack), axis=0)


def value_band(arr: np.ndarray, bands: int) -> np.ndarray:
    """Quantize luma into ``bands`` levels, preserving chroma (TDD 7.6)."""
    if bands < 2:
        return arr
    out = arr.copy()
    rgb = out[..., :3]
    luma = rgb @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    banded = np.round(luma * (bands - 1)) / (bands - 1)
    scale = np.where(luma > 1e-5, banded / np.maximum(luma, 1e-5), 0.0)
    out[..., :3] = np.clip(rgb * scale[..., None], 0.0, 1.0)
    return out
