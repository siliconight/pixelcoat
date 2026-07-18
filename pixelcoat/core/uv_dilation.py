"""UV-island-aware gutter dilation (roadmap Technique T06).

Fills the empty texels around packed UV islands with edge colour so that
bilinear filtering and mipmaps do not sample background through the gutter,
*without* letting one island's colour bleed across the ownership boundary
into a neighbouring island.

Design constraints (kept deliberately narrow so this module never locks the
project into a Skin Job schema):

- Inputs are plain NumPy arrays, not Pixelcoat/Skin Job objects. Anything
  that can produce a coverage mask and an integer island-id map can drive it
  (a Blender bake, an existing atlas, or a unit-test fixture).
- Pure ``numpy`` — no SciPy, no mesh library — matching the package's
  numpy+pillow dependency floor.
- Deterministic: identical inputs give byte-identical outputs. No RNG.

The core is an exact Euclidean distance transform that also returns, for every
texel, the index of the nearest occupied texel (Felzenszwalb & Huttenlocher,
"Distance Transforms of Sampled Functions", linear-time separable method).
Because each empty texel copies from *exactly one* nearest source texel, two
different islands are never averaged together — the "nearest island wins"
ownership rule falls out for free.
"""

from __future__ import annotations

from typing import Tuple

import numpy as np

__all__ = [
    "edt_nearest_indices",
    "dilate_islands",
]

_INF = 1e20


# ---------------------------------------------------------------------------
# Exact Euclidean distance transform with nearest-seed index recovery
# ---------------------------------------------------------------------------

def _dt_1d(f: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """1-D squared distance transform of samples ``f`` with argmin recovery.

    Returns ``(d, arg)`` where ``d[q] = min_p (q - p)**2 + f[p]`` and
    ``arg[q]`` is the ``p`` achieving that minimum. This is the lower-envelope
    of parabolas method; it runs in O(n) per line.
    """
    n = f.shape[0]
    d = np.empty(n, dtype=np.float64)
    arg = np.empty(n, dtype=np.int64)
    v = np.zeros(n, dtype=np.int64)      # parabola vertices in the envelope
    z = np.empty(n + 1, dtype=np.float64)  # envelope intersection boundaries
    k = 0
    v[0] = 0
    z[0] = -_INF
    z[1] = _INF
    for q in range(1, n):
        # Intersection of parabola from q with the one currently on top.
        s = ((f[q] + q * q) - (f[v[k]] + v[k] * v[k])) / (2.0 * q - 2.0 * v[k])
        while s <= z[k]:
            k -= 1
            s = ((f[q] + q * q) - (f[v[k]] + v[k] * v[k])) / (2.0 * q - 2.0 * v[k])
        k += 1
        v[k] = q
        z[k] = s
        z[k + 1] = _INF
    k = 0
    for q in range(n):
        while z[k + 1] < q:
            k += 1
        vk = v[k]
        d[q] = (q - vk) * (q - vk) + f[vk]
        arg[q] = vk
    return d, arg


def edt_nearest_indices(
    mask: np.ndarray,
    *,
    wrap_x: bool = False,
    wrap_y: bool = False,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Exact squared EDT of ``mask`` plus the nearest occupied texel index.

    Parameters
    ----------
    mask
        2-D boolean array. ``True`` marks *occupied* (seed) texels; distance is
        measured from every texel to the nearest ``True`` texel.
    wrap_x, wrap_y
        Treat the corresponding axis as toroidal (for tileable textures). The
        nearest seed may then be found across the opposite edge. Exact provided
        the true nearest seed is within one period, which always holds for
        gutter-sized radii.

    Returns
    -------
    dist2, nearest_y, nearest_x
        ``dist2`` is the squared Euclidean distance (float64). ``nearest_y`` /
        ``nearest_x`` are the row/column of the nearest occupied texel, folded
        back into ``[0, H)`` / ``[0, W)`` when wrapping. Where ``mask`` is
        empty everywhere the distances are ``+inf`` and indices are 0.
    """
    if mask.ndim != 2:
        raise ValueError("mask must be 2-D")
    mask = np.asarray(mask, dtype=bool)
    if not mask.any():
        h, w = mask.shape
        return (
            np.full((h, w), np.inf, dtype=np.float64),
            np.zeros((h, w), dtype=np.int64),
            np.zeros((h, w), dtype=np.int64),
        )

    # Replicating the mask across a wrapped axis lets the planar transform pick
    # up seeds on the far edge; we transform the widened array then fold indices
    # back into the original range.
    tiles_y = 3 if wrap_y else 1
    tiles_x = 3 if wrap_x else 1
    work = np.tile(mask, (tiles_y, tiles_x))

    h, w = work.shape
    f = np.where(work, 0.0, _INF)

    # Pass 1: transform down each column (axis 0). src_row[y, x] = nearest row.
    src_row = np.empty((h, w), dtype=np.int64)
    col_d = np.empty((h, w), dtype=np.float64)
    for x in range(w):
        d, arg = _dt_1d(f[:, x])
        col_d[:, x] = d
        src_row[:, x] = arg

    # Pass 2: transform along each row (axis 1) using the column distances as
    # the sampled function. arg gives the source column; the source row is then
    # src_row at (y, source_col).
    dist2 = np.empty((h, w), dtype=np.float64)
    near_y = np.empty((h, w), dtype=np.int64)
    near_x = np.empty((h, w), dtype=np.int64)
    for y in range(h):
        d, arg = _dt_1d(col_d[y, :])
        dist2[y, :] = d
        near_x[y, :] = arg
        near_y[y, :] = src_row[y, arg]

    # Crop back to the central (original) tile and fold indices modulo the real
    # dimensions so wrapped neighbours map to valid source texels.
    oh, ow = mask.shape
    y0 = oh if wrap_y else 0
    x0 = ow if wrap_x else 0
    dist2 = dist2[y0:y0 + oh, x0:x0 + ow]
    near_y = near_y[y0:y0 + oh, x0:x0 + ow] % oh
    near_x = near_x[y0:y0 + oh, x0:x0 + ow] % ow
    return dist2, near_y, near_x


# ---------------------------------------------------------------------------
# Island-aware gutter fill
# ---------------------------------------------------------------------------

def dilate_islands(
    image: np.ndarray,
    coverage: np.ndarray,
    island_id: np.ndarray,
    radius: float,
    *,
    wrap_x: bool = False,
    wrap_y: bool = False,
    alpha_gutter: bool = False,
) -> Tuple[np.ndarray, np.ndarray]:
    """Extrude island colours into the surrounding gutter, ownership-aware.

    Every empty texel within ``radius`` of a covered texel is filled with the
    colour of its *single* nearest covered texel and inherits that texel's
    island id. Because the source is one nearest texel, colours from two
    different islands are never blended — the boundary between two islands'
    gutters is the Euclidean midline.

    Parameters
    ----------
    image
        ``(H, W, C)`` array (C = 3 or 4), uint8 or float. Returned dtype
        matches the input.
    coverage
        ``(H, W)`` boolean. ``True`` where a real (island-owned) texel exists.
    island_id
        ``(H, W)`` integer island owner per texel. Only read where ``coverage``
        is ``True``.
    radius
        Maximum dilation distance in texels (Euclidean). Texels farther than
        this from any island are left untouched.
    wrap_x, wrap_y
        Toroidal axes for tileable textures.
    alpha_gutter
        For a 4-channel image: when ``False`` (default) filled gutter texels
        keep alpha 0 — RGB is extruded for filtering but the texel stays
        transparent (decal-safe). When ``True`` the nearest texel's alpha is
        copied too.

    Returns
    -------
    out_image, out_owner
        ``out_image`` is ``image`` with gutter texels filled. ``out_owner`` is
        an integer map: the original ``island_id`` on covered texels, the
        inherited owner on filled gutter texels, and ``-1`` on texels left
        untouched (background beyond ``radius``).
    """
    image = np.asarray(image)
    coverage = np.asarray(coverage, dtype=bool)
    island_id = np.asarray(island_id)
    if image.ndim != 3 or image.shape[2] not in (3, 4):
        raise ValueError("image must be (H, W, 3) or (H, W, 4)")
    if coverage.shape != image.shape[:2] or island_id.shape != image.shape[:2]:
        raise ValueError("coverage and island_id must match image H×W")
    if radius <= 0:
        return image.copy(), np.where(coverage, island_id, -1).astype(np.int64)

    dist2, near_y, near_x = edt_nearest_indices(
        coverage, wrap_x=wrap_x, wrap_y=wrap_y
    )

    out = image.copy()
    owner = np.where(coverage, island_id, -1).astype(np.int64)

    # Gutter texels: currently empty, within radius of some island.
    eligible = (~coverage) & (dist2 <= radius * radius)
    ys, xs = np.nonzero(eligible)
    if ys.size:
        sy = near_y[ys, xs]
        sx = near_x[ys, xs]
        filled = image[sy, sx]
        if image.shape[2] == 4 and not alpha_gutter:
            filled = filled.copy()
            filled[:, 3] = 0
        out[ys, xs] = filled
        owner[ys, xs] = island_id[sy, sx]

    return out, owner
