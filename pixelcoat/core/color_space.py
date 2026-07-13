"""Linear <-> sRGB working data (Gen7 roadmap §3).

Generation 7 mode does its lighting math, blending, height extraction, and
roughness work on LINEAR values; display albedo is encoded back to sRGB
only at export. Data maps (height, normal, roughness, gloss, masks) never
receive gamma. These are shared core utilities, deliberately not embedded
in any one Gen7 node.

Same transfer curves as quantization.py's private helpers; public here
because the whole Gen7 graph depends on them.
"""

from __future__ import annotations

import numpy as np

# Rec.709 luminance weights — valid on LINEAR RGB.
LUMA_LINEAR = np.array([0.2126, 0.7152, 0.0722], np.float32)

_EPS = 1e-5


def srgb_to_linear(c: np.ndarray) -> np.ndarray:
    c = np.asarray(c, np.float32)
    return np.where(c <= 0.04045, c / 12.92,
                    ((c + 0.055) / 1.055) ** 2.4).astype(np.float32)


def linear_to_srgb(c: np.ndarray) -> np.ndarray:
    c = np.clip(np.asarray(c, np.float32), 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92,
                    1.055 * c ** (1 / 2.4) - 0.055).astype(np.float32)


def luminance(linear_rgb: np.ndarray) -> np.ndarray:
    """(H, W) linear luminance from (H, W, 3) linear RGB."""
    return (linear_rgb[..., :3] @ LUMA_LINEAR).astype(np.float32)


def scale_to_luminance(linear_rgb: np.ndarray,
                       new_luma: np.ndarray) -> np.ndarray:
    """Rescale RGB so its luminance matches ``new_luma``, preserving
    chroma ratios. The luma/chroma recombine primitive used by lighting
    flattening and stylization."""
    old = luminance(linear_rgb)
    scale = new_luma / np.maximum(old, _EPS)
    return np.clip(linear_rgb * scale[..., None], 0.0, 4.0).astype(np.float32)


def normalize01(a: np.ndarray) -> np.ndarray:
    """Stretch to 0..1; a constant field maps to all 0.5 (flat)."""
    lo, hi = float(a.min()), float(a.max())
    if hi - lo < _EPS:
        return np.full_like(a, 0.5, dtype=np.float32)
    return ((a - lo) / (hi - lo)).astype(np.float32)
