"""Approximate lighting flattening (Gen7 roadmap §4).

Photographs carry directional illumination, shadows, and exposure drift
that must not be baked into a reusable material. This pass estimates
illumination with a large-radius blur, divides it out of luminance,
recombines with the source chroma, and blends by an artist strength.

This is an APPROXIMATION — it is not, and must never be documented as,
physically accurate delighting or photogrammetric albedo reconstruction.
All math runs on linear working data.
"""

from __future__ import annotations

import numpy as np

from . import frequency
from .color_space import luminance, scale_to_luminance

_EPS = 1e-4


def flatten(linear_rgb: np.ndarray, strength: float, radius: int,
            shadow_recovery: float, highlight_compression: float,
            wrap_x: bool, wrap_y: bool) -> np.ndarray:
    """Return lighting-flattened linear RGB.

    strength 0..1 blends original -> fully flattened; radius is the
    illumination-estimate blur in working pixels; shadow_recovery lifts
    deep shadows; highlight_compression soft-knees blown highlights.
    """
    rgb = np.clip(linear_rgb.astype(np.float32), 0.0, 1.0)
    luma = luminance(rgb)

    out_l = luma
    s = float(np.clip(strength, 0.0, 1.0))
    if s > 0.0:
        illum = frequency.smooth_blur(luma, max(2, int(radius)),
                                      wrap_x, wrap_y)
        mean = max(float(illum.mean()), _EPS)
        flat_l = luma * (mean / np.maximum(illum, _EPS))
        out_l = luma * (1.0 - s) + flat_l * s

    sr = float(np.clip(shadow_recovery, 0.0, 1.0))
    if sr > 0.0:
        # Gamma-style lift on linear luma: pulls shadow detail up without
        # touching midtones much. Exponent 1 at sr=0 -> 1/(1+sr) at full.
        lifted = np.clip(out_l, 0.0, 1.0) ** (1.0 / (1.0 + sr))
        out_l = out_l * (1.0 - sr) + lifted * sr

    hc = float(np.clip(highlight_compression, 0.0, 1.0))
    if hc > 0.0:
        knee = 0.75
        over = np.maximum(out_l - knee, 0.0)
        out_l = np.where(out_l > knee,
                         knee + over / (1.0 + hc * 3.0), out_l)

    out = scale_to_luminance(rgb, np.clip(out_l, 0.0, 1.0))
    return np.clip(out, 0.0, 1.0).astype(np.float32)
