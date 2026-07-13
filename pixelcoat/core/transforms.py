"""Crop, rotation, perspective rectification (TDD 7.2).

Rectification samples at 2x the working resolution with bicubic, then the
downsample stage box-filters onto the pixel grid — supersampling avoids the
shimmer that direct nearest sampling bakes into rectified quads.
"""

from __future__ import annotations

import numpy as np
from PIL import Image


def apply(arr: np.ndarray, crop, quad, rotation_degrees: int,
          target: tuple[int, int]) -> np.ndarray:
    """Run the transform block. Returns float RGBA at 2x target size
    (the downsample stage owns the final grid snap)."""
    im = Image.fromarray((arr * 255).astype(np.uint8), "RGBA")
    if crop:
        x, y, w, h = crop
        if w < 1 or h < 1 or x < 0 or y < 0 \
                or x + w > im.width or y + h > im.height:
            raise ValueError(f"invalid crop {crop} for {im.width}x{im.height}")
        im = im.crop((x, y, x + w, y + h))
    if quad:
        tl, tr, br, bl = quad
        w2, h2 = target[0] * 2, target[1] * 2
        im = im.transform((w2, h2), Image.QUAD,
                          data=(tl[0], tl[1], bl[0], bl[1],
                                br[0], br[1], tr[0], tr[1]),
                          resample=Image.BICUBIC)
    if rotation_degrees % 360:
        im = im.rotate(-rotation_degrees, expand=True)
    return np.asarray(im, np.float32) / 255.0


def downsample(arr: np.ndarray, size: tuple[int, int], method: str,
               edge_preserve: float = 0.5) -> np.ndarray:
    if method == "edge_aware":
        return _downsample_edge_aware(arr, size, edge_preserve)
    im = Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8), "RGBA")
    resample = Image.BOX if method == "box" else Image.NEAREST
    return np.asarray(im.resize(size, resample), np.float32) / 255.0


def _downsample_edge_aware(arr: np.ndarray, size: tuple[int, int],
                           edge_preserve: float) -> np.ndarray:
    """TDD 7.4 edge-aware downsampling: per output cell, pixels are
    weighted by similarity to the cell's MEDIAN color, so a boundary cell
    resolves to its majority side instead of smearing both sides into a
    mud tone the palette never contained. edge_preserve 0 ~= box,
    1 = hard commitment to the dominant side. Deterministic; pure NumPy.
    """
    k = 4                                        # supersample factor
    w, h = size
    im = Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8),
                         "RGBA")
    big = np.asarray(im.resize((w * k, h * k), Image.LANCZOS),
                     np.float32) / 255.0
    cells = big.reshape(h, k, w, k, 4).transpose(0, 2, 1, 3, 4) \
        .reshape(h, w, k * k, 4)
    med = np.median(cells[..., :3], axis=2, keepdims=True)
    dist2 = ((cells[..., :3] - med) ** 2).sum(axis=-1)
    # sigma shrinks as edge_preserve grows; +eps keeps weights finite
    sigma2 = float(np.interp(np.clip(edge_preserve, 0, 1),
                             [0.0, 1.0], [1.5, 0.005]))
    wgt = np.exp(-dist2 / (2.0 * sigma2))[..., None]
    out = (cells * wgt).sum(axis=2) / np.maximum(wgt.sum(axis=2), 1e-8)
    return np.clip(out, 0.0, 1.0).astype(np.float32)
