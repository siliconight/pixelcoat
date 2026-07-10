"""Material map generation (TDD §7.13) — derive the depth of a surface
from its quantized albedo.

The albedo is the paint job; these maps are what make it read as a
*material* under light: a height field inferred from luminance, a normal
map differentiated from that height, a stepped roughness response, and an
optional emissive selection. Everything is derived from the post-dither
working-resolution image so the maps stay pixel-aligned with the albedo
through upscale and padding.

Conventions:
- Normal maps are OpenGL-style (Y+ / green brightens on the TOP edge of a
  bump) — the convention Godot 4 and Blender both expect. ``flip_g``
  exists for DirectX-style consumers.
- When the recipe tiles an axis, gradients wrap on that axis so the
  normal map is seamless exactly where the albedo is.
- All functions are pure numpy, float 0..1 in and out, deterministic.
"""

from __future__ import annotations

import numpy as np

_LUMA = np.array([0.2126, 0.7152, 0.0722], np.float32)


# ------------------------------------------------------------------ height

def height_from_albedo(rgb: np.ndarray, smooth: int = 1,
                       wrap_x: bool = False, wrap_y: bool = False
                       ) -> np.ndarray:
    """Luminance height field (H, W) in 0..1. ``smooth`` iterated 3x3
    median passes knock dither speckle out of the field so the normal map
    reads surface shapes, not dither grids."""
    h = (rgb[..., :3] @ _LUMA).astype(np.float32)
    for _ in range(max(0, int(smooth))):
        h = _median3(h, wrap_x, wrap_y)
    return np.clip(h, 0.0, 1.0)


def _median3(h: np.ndarray, wrap_x: bool, wrap_y: bool) -> np.ndarray:
    p = np.pad(h, ((1, 1), (0, 0)), mode="wrap" if wrap_y else "edge")
    p = np.pad(p, ((0, 0), (1, 1)), mode="wrap" if wrap_x else "edge")
    stack = [p[y:y + h.shape[0], x:x + h.shape[1]]
             for y in range(3) for x in range(3)]
    return np.median(np.stack(stack), axis=0).astype(np.float32)


# ------------------------------------------------------------------ normal

def normal_from_height(height: np.ndarray, strength: float = 2.0,
                       wrap_x: bool = False, wrap_y: bool = False,
                       flip_g: bool = False) -> np.ndarray:
    """Tangent-space normal map (H, W, 3) encoded 0..1 from a height
    field. Central differences; wrapped on tiling axes, clamped
    (edge-padded) otherwise.

    Sign derivation for OpenGL Y+: with image row 0 at the top and GL's V
    axis pointing up, ``dh/dv = -dh/dy_img``, so the green component is
    ``+dh/dy_img`` — green bright on the top edge of a bump.
    """
    p = np.pad(height, ((1, 1), (0, 0)), mode="wrap" if wrap_y else "edge")
    p = np.pad(p, ((0, 0), (1, 1)), mode="wrap" if wrap_x else "edge")
    dx = (p[1:-1, 2:] - p[1:-1, :-2]) * 0.5
    dy = (p[2:, 1:-1] - p[:-2, 1:-1]) * 0.5

    nx = -dx * strength
    ny = dy * strength
    if flip_g:
        ny = -ny
    nz = np.ones_like(nx)
    length = np.sqrt(nx * nx + ny * ny + nz * nz)
    n = np.stack([nx / length, ny / length, nz / length], axis=-1)
    return (n * 0.5 + 0.5).astype(np.float32)


# --------------------------------------------------------------- roughness

def roughness_from_height(height: np.ndarray, base: float = 0.6,
                          variation: float = 0.25, levels: int = 4,
                          invert: bool = False) -> np.ndarray:
    """Stepped roughness (H, W): recesses (dark) read rougher, raised
    (bright) areas smoother — flip with ``invert``. Quantized to
    ``levels`` evenly spaced values for a chunky PS1-era specular
    response rather than a smooth modern gradient."""
    sign = -1.0 if invert else 1.0
    r = base + variation * sign * (0.5 - height)
    r = np.clip(r, 0.0, 1.0)
    lv = max(2, int(levels))
    return (np.round(r * (lv - 1)) / (lv - 1)).astype(np.float32)


# ---------------------------------------------------------------- emissive

def emissive_indices(rgb: np.ndarray, palette: np.ndarray,
                     indices: list[int]) -> np.ndarray:
    """Emissive map (H, W, 3): the selected palette entries glow at their
    albedo color, everything else is black. The albedo is
    palette-constrained by construction, so nearest-match indexing is
    exact."""
    flat = rgb.reshape(-1, 3)
    d = np.linalg.norm(flat[:, None, :] - palette[None, :, :], axis=2)
    idx = d.argmin(axis=1).reshape(rgb.shape[:2])
    mask = np.isin(idx, np.asarray(list(indices), dtype=int))
    return (rgb * mask[..., None]).astype(np.float32)


def emissive_threshold(rgb: np.ndarray, threshold: float) -> np.ndarray:
    """Emissive map (H, W, 3): pixels at or above the luma threshold glow
    at their albedo color."""
    luma = rgb[..., :3] @ _LUMA
    mask = luma >= threshold
    return (rgb * mask[..., None]).astype(np.float32)


# ------------------------------------------------------------------ helper

def to_rgb(single: np.ndarray) -> np.ndarray:
    """Expand a single-channel (H, W) map to (H, W, 3) for PNG export."""
    return np.repeat(single[..., None], 3, axis=-1)
