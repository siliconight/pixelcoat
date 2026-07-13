"""Seam assistance (TDD 7.12) — v0.1: half-offset + blend band.

Palette enforcement re-runs AFTER seam repair (TDD 12.5 step 4), so the
pipeline calls this before quantization.
"""

from __future__ import annotations

import numpy as np

_SEAM_BAND = 0.12


def make_tileable(arr: np.ndarray, axes: str) -> np.ndarray:
    out = arr
    if axes in ("x", "both"):
        out = _blend_axis(out, axis=1)
    if axes in ("y", "both"):
        out = _blend_axis(out, axis=0)
    return out


def _blend_axis(arr: np.ndarray, axis: int) -> np.ndarray:
    n = arr.shape[axis]
    band = max(2, int(n * _SEAM_BAND))
    rolled = np.roll(arr, n // 2, axis=axis)
    t = np.zeros(n, np.float32)
    lo = n // 2 - band // 2
    t[lo:lo + band] = np.linspace(0.0, 1.0, band, dtype=np.float32)
    t[lo + band:] = 1.0
    shape = [1] * arr.ndim
    shape[axis] = n
    t = t.reshape(shape)
    covered = rolled * (1.0 - t) + np.roll(rolled, band, axis=axis) * t
    return np.roll(covered, -(n // 2), axis=axis)


# --------------------------------------------------------- generation 7

_G7_BAND = 0.16


def make_tileable_wrap(arr: np.ndarray, axes: str) -> np.ndarray:
    """Gen7 seam repair with a hard continuity guarantee (roadmap §17).

    Per axis: crossfade the image toward its half-rolled copy inside an
    edge band. At the wrap edges the output IS the rolled copy, whose wrap
    pair is two adjacent center rows of the original — so opposite edges
    are continuous by construction, exactly, before any derived map is
    generated. The v0.1 ``make_tileable`` above is a soft assist for the
    palette pixel path and is intentionally untouched (behavior-locked).
    """
    out = arr
    if axes in ("x", "both"):
        out = _wrap_axis(out, axis=1)
    if axes in ("y", "both"):
        out = _wrap_axis(out, axis=0)
    return out


def _wrap_axis(arr: np.ndarray, axis: int) -> np.ndarray:
    n = arr.shape[axis]
    band = max(2, int(n * _G7_BAND))
    rolled = np.roll(arr, n // 2, axis=axis)
    w = np.zeros(n, np.float32)
    ramp = np.linspace(1.0, 0.0, band, dtype=np.float32)
    ramp = ramp * ramp * (3 - 2 * ramp)              # smoothstep
    w[:band] = ramp
    w[n - band:] = ramp[::-1]
    shape = [1] * arr.ndim
    shape[axis] = n
    w = w.reshape(shape)
    return (arr * (1.0 - w) + rolled * w).astype(np.float32)
