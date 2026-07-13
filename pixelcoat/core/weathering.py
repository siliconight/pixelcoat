"""Weathering (Gen7 roadmap §12–§15): wear, grime, streaks, rust, wetness.

Nothing here is uniform noise slapped on top. Wear grows from height
gradients on RAISED transitions; grime accumulates IN cavities; streaks
run a decaying recurrence along a chosen direction; wetness darkens,
glosses, and softens micro response only inside its own mask. Every
stochastic input comes from one seeded generator, so weathering is
deterministic by (recipe, seed, version) like everything else Pixelcoat
emits. All masks are exported so downstream tools drive their own
variants from the same data.
"""

from __future__ import annotations

import numpy as np

from . import frequency

_EPS = 1e-5


# ---------------------------------------------------------------- noise

def value_noise(shape: tuple[int, int], cells: int, seed: int,
                wrap_x: bool, wrap_y: bool) -> np.ndarray:
    """Seeded low-frequency value noise (H, W) in 0..1. A coarse random
    grid bilinearly upsampled; the lattice is periodic on wrapped axes so
    tiled surfaces weather seamlessly."""
    h, w = shape
    cells = max(2, int(cells))
    rng = np.random.default_rng(seed)
    grid = rng.random((cells, cells)).astype(np.float32)

    ys = np.linspace(0.0, cells if wrap_y else cells - 1, h,
                     endpoint=False if wrap_y else True, dtype=np.float32)
    xs = np.linspace(0.0, cells if wrap_x else cells - 1, w,
                     endpoint=False if wrap_x else True, dtype=np.float32)
    y0 = np.floor(ys).astype(int)
    x0 = np.floor(xs).astype(int)
    fy = (ys - y0)[:, None]
    fx = (xs - x0)[None, :]
    fy = fy * fy * (3 - 2 * fy)  # smoothstep
    fx = fx * fx * (3 - 2 * fx)

    def g(yy, xx):
        return grid[yy % cells][:, xx % cells]

    a = g(y0, x0)
    b = g(y0, x0 + 1)
    c = g(y0 + 1, x0)
    d = g(y0 + 1, x0 + 1)
    top = a * (1 - fx) + b * fx
    bot = c * (1 - fx) + d * fx
    return (top * (1 - fy) + bot * fy).astype(np.float32)


# ------------------------------------------------------------- edge wear

def edge_wear_mask(macro_height: np.ndarray, amount: float, seed: int,
                   wrap_x: bool, wrap_y: bool) -> np.ndarray:
    """(H, W) wear mask 0..1: gradient strength x raised-area x seeded
    noise (roadmap §12) — wear favors raised transitions, never flats or
    recesses."""
    if amount <= 0.0:
        return np.zeros_like(macro_height, dtype=np.float32)
    gx = frequency._shift_diff(macro_height, axis=1, wrap=wrap_x)
    gy = frequency._shift_diff(macro_height, axis=0, wrap=wrap_y)
    edge = np.sqrt(gx * gx + gy * gy)
    edge = edge / max(float(edge.max()), _EPS)

    local_mean = frequency.box_blur(macro_height,
                                    max(2, macro_height.shape[0] // 16),
                                    wrap_x, wrap_y)
    raised = np.maximum(macro_height - local_mean, 0.0)
    raised = raised / max(float(raised.max()), _EPS)

    noise = value_noise(macro_height.shape, 12, seed, wrap_x, wrap_y)
    mask = np.sqrt(edge) * (0.35 + 0.65 * raised) * (0.4 + 0.6 * noise)
    mask = mask / max(float(mask.max()), _EPS)
    return np.clip(mask * float(amount) * 2.0, 0.0, 1.0).astype(np.float32)


# ------------------------------------------------------------- grime

def grime_mask(cavity_recess: np.ndarray, amount: float, seed: int,
               wrap_x: bool, wrap_y: bool) -> np.ndarray:
    """(H, W) grime mask 0..1: cavity x seeded accumulation noise
    (roadmap §13) — dirt collects in recesses, not on proud surfaces."""
    if amount <= 0.0:
        return np.zeros_like(cavity_recess, dtype=np.float32)
    noise = value_noise(cavity_recess.shape, 9, seed + 101, wrap_x, wrap_y)
    broad = frequency.smooth_blur(cavity_recess,
                                  max(2, cavity_recess.shape[0] // 24),
                                  wrap_x, wrap_y)
    mask = (cavity_recess * 0.7 + broad * 0.3) * (0.3 + 0.7 * noise)
    mask = mask / max(float(mask.max()), _EPS)
    return np.clip(mask * float(amount) * 2.0, 0.0, 1.0).astype(np.float32)


# ------------------------------------------------------------- streaks

_DIRECTIONS = ("down", "up", "left", "right")


def streaks(source_mask: np.ndarray, amount: float, decay: float,
            direction: str, seed: int, wrap: bool,
            wrap_cross: bool = False) -> np.ndarray:
    """(H, W) directional streak mask via the roadmap §14 recurrence
    ``streak[y] = max(source[y], streak[y-1] * decay)``, scanned along the
    chosen direction. When the streak axis tiles, a second pass carries
    the wrapped tail across the seam so the mask stays seamless."""
    if amount <= 0.0:
        return np.zeros_like(source_mask, dtype=np.float32)
    if direction not in _DIRECTIONS:
        raise ValueError(f"streak direction must be one of {_DIRECTIONS}")

    m = source_mask
    # Canonicalize to "down": rows scanned top to bottom.
    if direction == "up":
        m = m[::-1]
    elif direction == "left":
        m = m.T[::-1]
    elif direction == "right":
        m = m.T

    # In canonical orientation, rows are the scan axis: its wrap is the
    # streak wrap; columns carry the cross-axis wrap.
    noise = value_noise(m.shape, 24, seed + 202,
                        wrap_x=wrap_cross, wrap_y=wrap)
    src = np.clip(m * (0.5 + 0.5 * noise) * float(amount) * 2.0, 0.0, 1.0)

    d = float(np.clip(decay, 0.0, 0.999))
    out = _scan(src, d)
    if wrap:
        carry = out[-1] * d
        seeded = src.copy()
        seeded[0] = np.maximum(seeded[0], carry)
        out = _scan(seeded, d)

    if direction == "up":
        out = out[::-1]
    elif direction == "left":
        out = out[::-1].T
    elif direction == "right":
        out = out.T
    return np.clip(out, 0.0, 1.0).astype(np.float32)


def _scan(src: np.ndarray, decay: float) -> np.ndarray:
    out = np.empty_like(src, dtype=np.float32)
    prev = np.zeros(src.shape[1], np.float32)
    for y in range(src.shape[0]):
        prev = np.maximum(src[y], prev * decay)
        out[y] = prev
    return out


# ------------------------------------------------------------- wetness

def wetness_mask(cavity_recess: np.ndarray, amount: float,
                 cavity_bias: float, bottom_bias: float, seed: int,
                 wrap_x: bool, wrap_y: bool) -> np.ndarray:
    """(H, W) wetness mask 0..1: water pools in cavities, clings low on
    the surface, varies by seed (roadmap §15)."""
    if amount <= 0.0:
        return np.zeros_like(cavity_recess, dtype=np.float32)
    h = cavity_recess.shape[0]
    if wrap_y:
        # A y-tiling surface has no "bottom"; a linear ramp would cut a
        # seam by construction. Redistribute the bias into cavities.
        bottom = np.zeros((h, 1), np.float32)
        cavity_bias = min(1.0, cavity_bias + bottom_bias)
        bottom_bias = 0.0
    else:
        bottom = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
    noise = value_noise(cavity_recess.shape, 7, seed + 303, wrap_x, wrap_y)
    mask = (cavity_recess * float(cavity_bias)
            + bottom * float(bottom_bias)
            + noise * max(0.0, 1.0 - cavity_bias - bottom_bias))
    mask = mask / max(float(mask.max()), _EPS)
    return np.clip(mask * float(amount), 0.0, 1.0).astype(np.float32)
