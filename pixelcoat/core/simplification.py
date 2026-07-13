"""Pre-quantization simplification (TDD 7.4) — v0.1 slice.

Noise reduction (iterated 3x3 median), value banding (7.6's two-to-N tone
grouping applied in luma while keeping chroma), protected-detail masking
(7.4: masked regions keep their source detail through smoothing, banding,
and island removal), and post-quantization small-island removal (orphan
palette specks dissolve into their dominant neighbor). Edge-aware
DOWNSAMPLING lives in transforms.py with the other resamplers.
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


def load_mask(path: str, size: tuple[int, int]) -> np.ndarray:
    """Grayscale protected-detail mask, nearest-resized to working res.
    >0.5 = protected."""
    from PIL import Image
    im = Image.open(path).convert("L")
    if im.size != size:
        im = im.resize(size, Image.NEAREST)
    return (np.asarray(im, np.float32) / 255.0 > 0.5)


def protect(processed: np.ndarray, original: np.ndarray,
            mask: np.ndarray | None) -> np.ndarray:
    """Masked pixels keep the original (pre-stage) content."""
    if mask is None:
        return processed
    m = mask[..., None].astype(np.float32)
    return processed * (1.0 - m) + original * m


def remove_islands(indices: np.ndarray, max_size: int,
                   protected: np.ndarray | None = None) -> np.ndarray:
    """Dissolve connected same-palette-index regions of <= max_size
    pixels into their most common neighboring index (TDD 7.4 small-island
    removal). 8-CONNECTIVITY on purpose: ordered-dither checkerboards
    chain diagonally into large components and survive; only genuinely
    isolated specks dissolve. Deterministic label propagation; islands
    touching the protected mask are kept.
    """
    if max_size <= 0:
        return indices
    h, w = indices.shape
    labels = np.arange(h * w, dtype=np.int64).reshape(h, w)
    shifts = ((1, 0), (-1, 0), (0, 1), (0, -1),
              (1, 1), (1, -1), (-1, 1), (-1, -1))
    # Iterative min-label flood within equal-index regions.
    while True:
        prev = labels
        for dy, dx in shifts:
            nb_lab = np.roll(labels, (dy, dx), axis=(0, 1))
            nb_idx = np.roll(indices, (dy, dx), axis=(0, 1))
            edge = np.zeros((h, w), bool)          # roll wraps: cut it
            if dy:
                edge[0 if dy == 1 else -1, :] = True
            if dx:
                edge[:, 0 if dx == 1 else -1] = True
            ok = (nb_idx == indices) & ~edge
            labels = np.where(ok, np.minimum(labels, nb_lab), labels)
        if (labels == prev).all():
            break

    flat = labels.ravel()
    counts = np.bincount(flat, minlength=h * w)
    small = counts[flat].reshape(h, w) <= max_size
    if protected is not None:
        keep = np.unique(labels[protected & small])
        if len(keep):
            small &= ~np.isin(labels, keep)
    if not small.any():
        return indices

    out = indices.copy()
    # Deterministic order: smallest label first.
    for lab in np.unique(labels[small]):
        region = labels == lab
        ring = _dilate(region) & ~region
        if not ring.any():
            continue
        nb = out[ring]
        out[region] = np.bincount(nb).argmax()
    return out


def _dilate(m: np.ndarray) -> np.ndarray:
    out = m.copy()
    out[1:, :] |= m[:-1, :]
    out[:-1, :] |= m[1:, :]
    out[:, 1:] |= m[:, :-1]
    out[:, :-1] |= m[:, 1:]
    out[1:, 1:] |= m[:-1, :-1]
    out[1:, :-1] |= m[:-1, 1:]
    out[:-1, 1:] |= m[1:, :-1]
    out[:-1, :-1] |= m[1:, 1:]
    return out
