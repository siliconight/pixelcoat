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


def downsample(arr: np.ndarray, size: tuple[int, int], method: str) -> np.ndarray:
    im = Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8), "RGBA")
    resample = Image.BOX if method == "box" else Image.NEAREST
    return np.asarray(im.resize(size, resample), np.float32) / 255.0
