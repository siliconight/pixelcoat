"""Frequency separation + edge-preserving cleanup (Gen7 roadmap §5, §6).

Broad material forms and fine detail drive different outputs: the low band
feeds base-color variation, macro height, and broad occlusion; the high
band feeds grain, detail normal, cavity, and sharpening. Everything here is
pure NumPy (no OpenCV, no GPU), deterministic, and wrap-aware so tiled
surfaces stay seamless through every derived map.

The workhorse is a separable cumsum box blur — three passes approximate a
Gaussian closely enough for material work and stay fast at 2048 squared.
"""

from __future__ import annotations

import numpy as np


def box_blur(a: np.ndarray, radius: int,
             wrap_x: bool = False, wrap_y: bool = False) -> np.ndarray:
    """Separable box blur on (H, W) or (H, W, C). ``wrap_*`` uses periodic
    padding on that axis (tile-safe); otherwise edge padding."""
    r = int(radius)
    if r <= 0:
        return a.astype(np.float32, copy=True)
    out = _box_axis(a.astype(np.float32), r, axis=0, wrap=wrap_y)
    return _box_axis(out, r, axis=1, wrap=wrap_x)


def smooth_blur(a: np.ndarray, radius: int,
                wrap_x: bool = False, wrap_y: bool = False) -> np.ndarray:
    """Gaussian-ish blur: three box passes (radius split so the effective
    support stays close to the requested radius)."""
    r = max(1, int(radius))
    part = max(1, int(round(r * 0.55)))
    out = a
    for _ in range(3):
        out = box_blur(out, part, wrap_x, wrap_y)
    return out


def _box_axis(a: np.ndarray, r: int, axis: int, wrap: bool) -> np.ndarray:
    n = a.shape[axis]
    r = min(r, n - 1) if n > 1 else 0
    if r <= 0:
        return a
    pad = [(0, 0)] * a.ndim
    pad[axis] = (r, r)
    p = np.pad(a, pad, mode="wrap" if wrap else "edge")
    c = np.cumsum(p, axis=axis, dtype=np.float64)
    zero_shape = list(c.shape)
    zero_shape[axis] = 1
    c = np.concatenate([np.zeros(zero_shape, np.float64), c], axis=axis)
    w = 2 * r + 1
    hi = _slice(c, axis, w, w + n)
    lo = _slice(c, axis, 0, n)
    return ((hi - lo) / w).astype(np.float32)


def _slice(a: np.ndarray, axis: int, start: int, stop: int) -> np.ndarray:
    idx = [slice(None)] * a.ndim
    idx[axis] = slice(start, stop)
    return a[tuple(idx)]


# ------------------------------------------------------ band separation

def separate(luma: np.ndarray, macro_radius: int, micro_radius: int,
             noise_threshold: float, detail_gain: float,
             wrap_x: bool, wrap_y: bool) -> tuple[np.ndarray, np.ndarray]:
    """Split (H, W) luminance into (macro, micro_detail).

    ``macro`` is the broad-form band (blurred field, same range as input).
    ``micro_detail`` is the SIGNED fine band with small amplitudes soft-
    thresholded away — compression noise must not become false geometry —
    then scaled by ``detail_gain``. macro + untouched residual == source
    (reconstruction is exact before threshold/gain, by construction).
    """
    macro = smooth_blur(luma, macro_radius, wrap_x, wrap_y)
    micro_base = smooth_blur(luma, micro_radius, wrap_x, wrap_y)
    micro = luma - micro_base
    micro = soft_threshold(micro, noise_threshold) * float(detail_gain)
    return macro.astype(np.float32), micro.astype(np.float32)


def soft_threshold(band: np.ndarray, t: float) -> np.ndarray:
    """Shrink amplitudes toward zero by ``t``; kills sub-threshold noise
    without the hard edge a binary cutoff would leave."""
    if t <= 0.0:
        return band.astype(np.float32)
    return (np.sign(band) * np.maximum(np.abs(band) - t, 0.0)
            ).astype(np.float32)


# ----------------------------------------------- edge-preserving cleanup

def edge_preserving_smooth(linear_rgb: np.ndarray, strength: float,
                           chroma_strength: float,
                           wrap_x: bool, wrap_y: bool) -> np.ndarray:
    """Remove camera noise and JPEG artifacts without erasing material
    boundaries (roadmap §5 MVP): median + small blur, blended back by an
    edge mask so real boundaries keep the original pixels. Chroma is
    smoothed harder than luminance — chroma noise carries almost no
    material information.
    """
    if strength <= 0.0 and chroma_strength <= 0.0:
        return linear_rgb
    from .color_space import luminance, scale_to_luminance

    luma = luminance(linear_rgb)
    # Edge mask from luminance gradients: 1 at boundaries, 0 in flats.
    gx = np.abs(_shift_diff(luma, axis=1, wrap=wrap_x))
    gy = np.abs(_shift_diff(luma, axis=0, wrap=wrap_y))
    edges = np.clip((gx + gy) * 8.0, 0.0, 1.0)

    smoothed = _median3(linear_rgb, wrap_x, wrap_y)
    smoothed = box_blur(smoothed, 1, wrap_x, wrap_y)

    keep = 1.0 - float(np.clip(strength, 0.0, 1.0)) * (1.0 - edges)
    luma_out = luminance(linear_rgb) * keep + luminance(smoothed) * (1 - keep)

    cs = float(np.clip(chroma_strength, 0.0, 1.0))
    chroma_src = linear_rgb * (1 - cs) + smoothed * cs
    out = scale_to_luminance(chroma_src, luma_out)
    return np.clip(out, 0.0, 1.0).astype(np.float32)


def _shift_diff(a: np.ndarray, axis: int, wrap: bool) -> np.ndarray:
    pad = [(0, 0)] * a.ndim
    pad[axis] = (1, 1)
    p = np.pad(a, pad, mode="wrap" if wrap else "edge")
    hi = _slice(p, axis, 2, 2 + a.shape[axis])
    lo = _slice(p, axis, 0, a.shape[axis])
    return (hi - lo) * 0.5


def _median3(rgb: np.ndarray, wrap_x: bool, wrap_y: bool) -> np.ndarray:
    p = np.pad(rgb, ((1, 1), (0, 0), (0, 0)),
               mode="wrap" if wrap_y else "edge")
    p = np.pad(p, ((0, 0), (1, 1), (0, 0)),
               mode="wrap" if wrap_x else "edge")
    stack = [p[y:y + rgb.shape[0], x:x + rgb.shape[1]]
             for y in range(3) for x in range(3)]
    return np.median(np.stack(stack), axis=0).astype(np.float32)
