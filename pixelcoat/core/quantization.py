"""Palette quantization in OKLab (TDD §7.5, §12.2).

Clustering happens in OKLab so perceptual distance drives color merging —
the difference between "reduced photo" and "chosen palette". Deterministic:
k-means++ seeding runs on a seeded numpy Generator, iteration order is
fixed, and ties resolve by index.
"""

from __future__ import annotations

import json

import numpy as np

# --------------------------------------------------------------- OKLab
# Björn Ottosson's OKLab, sRGB D65. Matrices are exact per the reference.
_M1 = np.array([[0.4122214708, 0.5363325363, 0.0514459929],
                [0.2119034982, 0.6806995451, 0.1073969566],
                [0.0883024619, 0.2817188376, 0.6299787005]], np.float64)
_M2 = np.array([[0.2104542553, 0.7936177850, -0.0040720468],
                [1.9779984951, -2.4285922050, 0.4505937099],
                [0.0259040371, 0.7827717662, -0.8086757660]], np.float64)


def _srgb_to_linear(c: np.ndarray) -> np.ndarray:
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _linear_to_srgb(c: np.ndarray) -> np.ndarray:
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def srgb_to_oklab(rgb: np.ndarray) -> np.ndarray:
    lin = _srgb_to_linear(rgb.astype(np.float64))
    lms = lin @ _M1.T
    return np.cbrt(lms) @ _M2.T


def oklab_to_srgb(lab: np.ndarray) -> np.ndarray:
    lms = (lab.astype(np.float64) @ np.linalg.inv(_M2).T) ** 3
    return _linear_to_srgb(lms @ np.linalg.inv(_M1).T)


# --------------------------------------------------------------- k-means
def extract_palette(rgb_pixels: np.ndarray, k: int, seed: int) -> np.ndarray:
    """K-means in OKLab over opaque pixels. Returns (k, 3) sRGB floats,
    sorted dark to light for stable output ordering."""
    lab = srgb_to_oklab(rgb_pixels.reshape(-1, 3))
    k = int(min(k, len(np.unique(lab, axis=0))))
    rng = np.random.default_rng(seed)
    centers = _kpp_init(lab, k, rng)
    for _ in range(24):
        d = np.linalg.norm(lab[:, None, :] - centers[None, :, :], axis=2)
        assign = d.argmin(axis=1)
        moved = 0.0
        for i in range(k):
            members = lab[assign == i]
            if len(members):
                new = members.mean(axis=0)
                moved += float(np.linalg.norm(new - centers[i]))
                centers[i] = new
        if moved < 1e-6:
            break
    order = np.argsort(centers[:, 0], kind="stable")
    return np.clip(oklab_to_srgb(centers[order]), 0.0, 1.0).astype(np.float32)


def _kpp_init(data: np.ndarray, k: int, rng) -> np.ndarray:
    centers = [data[rng.integers(len(data))]]
    for _ in range(1, k):
        d2 = np.min([np.sum((data - c) ** 2, axis=1) for c in centers],
                    axis=0)
        total = d2.sum()
        if total <= 0:
            centers.append(data[0])
            continue
        centers.append(data[rng.choice(len(data), p=d2 / total)])
    return np.array(centers, np.float64)


def load_fixed(path: str) -> np.ndarray:
    """Load a JSON palette: ``["#a1b2c3", ...]`` or ``{"colors": [...]}``."""
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    colors = raw["colors"] if isinstance(raw, dict) else raw
    out = []
    for h in colors:
        h = h.lstrip("#")
        out.append([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)])
    if len(out) < 2:
        raise ValueError(f"{path}: palette needs at least 2 colors")
    return np.array(out, np.float32)


def map_to_palette(rgb: np.ndarray, palette: np.ndarray) -> np.ndarray:
    """Nearest-palette-entry mapping in OKLab. Returns indices (H, W)."""
    lab = srgb_to_oklab(rgb.reshape(-1, 3))
    pal_lab = srgb_to_oklab(palette)
    d = np.linalg.norm(lab[:, None, :] - pal_lab[None, :, :], axis=2)
    return d.argmin(axis=1).reshape(rgb.shape[:2])
