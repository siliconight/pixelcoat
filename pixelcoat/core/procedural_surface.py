"""Deterministic, tileable procedural primitives (roadmap Technique T03).

The building blocks for source-free material synthesis. Every primitive is:

- **Tileable** (wrap-exact on both axes) — Zoo imports Pixelcoat packs with
  ``extension = REPEAT`` and world-meter cube UVs, so a pack that is not
  perfectly wrap-continuous shows a visible grid seam on every surface. This is
  a *breakage* constraint, not a stylistic one, so tileability is enforced by
  construction (lattice wrapping) and checked by the tests.
- **Deterministic** — no global RNG. Each primitive draws from a SHA256-derived
  stream keyed by the asset seed plus a stable label, matching the factory's
  determinism story (Zoo/Patina/Deli Counter all use seed 1999 + named
  streams). Adding a new generator never reshuffles an existing one's noise.
- **Pure numpy** — no SciPy, no bpy; the package's dependency floor.

All generators return ``float32`` arrays. Unsigned fields are in ``[0, 1]``;
signed fields (used for height/detail) are centred on 0.
"""

from __future__ import annotations

import hashlib

import numpy as np

__all__ = [
    "stream_seed",
    "rng",
    "value_noise",
    "fbm",
    "directional_grain",
    "worley_f1",
    "worley_edges",
    "voronoi_cells",
    "hash_grain",
    "scratches",
    "streaks",
    "stripes",
    "weave",
    "veins",
    "masonry",
    "ribs",
    "wave",
    "posterize",
    "hex_to_rgb",
]


# --------------------------------------------------------------------------- #
# Seed discipline — independent streams from stable names
# --------------------------------------------------------------------------- #

def stream_seed(asset_seed: int, *labels: str) -> int:
    """A stable 32-bit seed derived from the asset seed and a label chain.

    ``stream_seed(1999, "macro")`` and ``stream_seed(1999, "chips")`` are
    independent, so introducing a new feature stream leaves every existing
    feature's placement byte-identical.
    """
    h = hashlib.sha256()
    h.update(str(int(asset_seed)).encode("utf-8"))
    for label in labels:
        h.update(b"\x00")
        h.update(str(label).encode("utf-8"))
    return int.from_bytes(h.digest()[:4], "big")


def rng(asset_seed: int, *labels: str) -> np.random.Generator:
    """A NumPy generator bound to a named, derived stream."""
    return np.random.default_rng(stream_seed(asset_seed, *labels))


# --------------------------------------------------------------------------- #
# Interpolation helper
# --------------------------------------------------------------------------- #

def _smoothstep(t: np.ndarray) -> np.ndarray:
    return t * t * (3.0 - 2.0 * t)


def _lattice_sample(lattice: np.ndarray, h: int, w: int) -> np.ndarray:
    """Bilinearly sample a periodic ``cells_y × cells_x`` lattice to ``h × w``.

    The lattice is treated as toroidal — cell index ``i+1`` wraps to ``0`` — so
    the resulting field is exactly tileable.
    """
    cy, cx = lattice.shape
    ys = (np.arange(h, dtype=np.float64) / h) * cy
    xs = (np.arange(w, dtype=np.float64) / w) * cx
    y0 = np.floor(ys).astype(np.int64)
    x0 = np.floor(xs).astype(np.int64)
    fy = _smoothstep(ys - y0)
    fx = _smoothstep(xs - x0)
    y0m, x0m = y0 % cy, x0 % cx
    y1m, x1m = (y0 + 1) % cy, (x0 + 1) % cx

    top = (lattice[np.ix_(y0m, x0m)] * (1 - fx)[None, :]
           + lattice[np.ix_(y0m, x1m)] * fx[None, :])
    bot = (lattice[np.ix_(y1m, x0m)] * (1 - fx)[None, :]
           + lattice[np.ix_(y1m, x1m)] * fx[None, :])
    return (top * (1 - fy)[:, None] + bot * fy[:, None]).astype(np.float32)


# --------------------------------------------------------------------------- #
# Primitives
# --------------------------------------------------------------------------- #

def value_noise(size, cells: int, seed: int, *, label: str = "value") -> np.ndarray:
    """Tileable value noise in ``[0, 1]`` at ``cells`` lattice resolution."""
    h, w = _as_hw(size)
    cells = max(1, int(cells))
    lat = rng(seed, label, cells).random((cells, cells)).astype(np.float64)
    return np.clip(_lattice_sample(lat, h, w), 0.0, 1.0)


def fbm(size, base_cells: int, octaves: int, seed: int, *,
        lacunarity: float = 2.0, gain: float = 0.5,
        label: str = "fbm") -> np.ndarray:
    """Tileable fractal (multi-octave) value noise, normalised to ``[0, 1]``."""
    h, w = _as_hw(size)
    octaves = max(1, int(octaves))
    acc = np.zeros((h, w), np.float32)
    amp, total = 1.0, 0.0
    cells = max(1, int(base_cells))
    for o in range(octaves):
        acc += amp * value_noise((h, w), cells, seed, label=f"{label}:{o}")
        total += amp
        amp *= gain
        cells = max(1, int(round(cells * lacunarity)))
    return (acc / max(total, 1e-6)).astype(np.float32)


def directional_grain(size, cells_along: int, cells_across: int, seed: int, *,
                      axis: str = "x", label: str = "grain") -> np.ndarray:
    """Axis-aligned anisotropic grain (brushed/rolled metal, wood, machining).

    ``axis="x"`` stretches the pattern along X (few cells across X, many across
    Y). Kept axis-aligned so it stays wrap-exact; arbitrary-angle grain would
    break tileability and is intentionally not offered here.
    """
    h, w = _as_hw(size)
    if axis == "x":
        cy, cx = max(1, int(cells_across)), max(1, int(cells_along))
    elif axis == "y":
        cy, cx = max(1, int(cells_along)), max(1, int(cells_across))
    else:
        raise ValueError("axis must be 'x' or 'y'")
    lat = rng(seed, label, axis, cy, cx).random((cy, cx)).astype(np.float64)
    return np.clip(_lattice_sample(lat, h, w), 0.0, 1.0)


def worley_f1(size, cells: int, seed: int, *, label: str = "worley") -> np.ndarray:
    """Tileable Worley/Voronoi F1 distance field in ``[0, 1]``.

    One jittered feature point per cell; nearest-point distance searched over
    the 3×3 neighbourhood with wrap, so the field tiles. Good for hammered
    metal, aggregate, blistered paint, cell damage.
    """
    h, w = _as_hw(size)
    cells = max(1, int(cells))
    pts = rng(seed, label, cells).random((cells, cells, 2)).astype(np.float64)

    ys = (np.arange(h, dtype=np.float64) / h) * cells
    xs = (np.arange(w, dtype=np.float64) / w) * cells
    gy, gx = np.meshgrid(ys, xs, indexing="ij")
    cell_y = np.floor(gy).astype(np.int64)
    cell_x = np.floor(gx).astype(np.int64)

    best = np.full((h, w), np.inf)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            ny = (cell_y + dy) % cells
            nx = (cell_x + dx) % cells
            fpy = (np.floor(cell_y + dy) + pts[ny, nx, 0])
            fpx = (np.floor(cell_x + dx) + pts[ny, nx, 1])
            d = (gy - fpy) ** 2 + (gx - fpx) ** 2
            best = np.minimum(best, d)
    best = np.sqrt(best)
    m = best.max()
    return (best / m if m > 1e-9 else best).astype(np.float32)


def worley_edges(size, cells: int, seed: int, *, label: str = "worley_edge") -> np.ndarray:
    """Tileable crisp cell-boundary field (F2−F1) in ``[0, 1]``.

    Near 0 in cell interiors, spiking toward the *ridge* between cells. Unlike
    the smooth F1 gradient, F2−F1 makes a sharp line exactly at cell walls —
    concrete cracks, aggregate/tile seams, cracked paint. Crisp, not blobby.
    """
    h, w = _as_hw(size)
    cells = max(1, int(cells))
    pts = rng(seed, label, cells).random((cells, cells, 2)).astype(np.float64)
    ys = (np.arange(h, dtype=np.float64) / h) * cells
    xs = (np.arange(w, dtype=np.float64) / w) * cells
    gy, gx = np.meshgrid(ys, xs, indexing="ij")
    cy = np.floor(gy).astype(np.int64)
    cx = np.floor(gx).astype(np.int64)
    f1 = np.full((h, w), np.inf)
    f2 = np.full((h, w), np.inf)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            ny = (cy + dy) % cells
            nx = (cx + dx) % cells
            fpy = np.floor(cy + dy) + pts[ny, nx, 0]
            fpx = np.floor(cx + dx) + pts[ny, nx, 1]
            d = (gy - fpy) ** 2 + (gx - fpx) ** 2
            closer = d < f1
            f2 = np.where(closer, f1, np.minimum(f2, d))
            f1 = np.where(closer, d, f1)
    edge = np.sqrt(f2) - np.sqrt(f1)
    m = edge.max()
    # Invert so ridges are bright (1 = on the wall), and it's a crisp line.
    return (1.0 - edge / m if m > 1e-9 else edge).astype(np.float32)


def voronoi_cells(size, cells: int, seed: int, *, gap: float = 0.04,
                  label: str = "cells"):
    """Tileable filled-Voronoi → ``(gap_mask, cell_id)``, both float32 in [0,1].

    Unlike ``masonry`` (a regular grid) or ``worley_f1`` (a smooth distance
    blob), this floods each irregular Voronoi cell as a solid region and hands
    back a *stable per-cell random value* (``cell_id``) — so a grammar can pour
    a palette colour into each cell (cobblestone, flagstone, terrazzo chips,
    pebble/gravel, crazy-paving, irregular mosaic). ``gap_mask`` is 1 on the
    thin boundary between cells (the mortar/matrix line); ``gap`` is its width
    in cell units. Tileable by wrapped 3x3 feature-point search.
    """
    h, w = _as_hw(size)
    cells = max(1, int(cells))
    pts = rng(seed, label, cells).random((cells, cells, 2)).astype(np.float64)
    ys = (np.arange(h, dtype=np.float64) / h) * cells
    xs = (np.arange(w, dtype=np.float64) / w) * cells
    gy, gx = np.meshgrid(ys, xs, indexing="ij")
    cy = np.floor(gy).astype(np.int64)
    cx = np.floor(gx).astype(np.int64)
    f1 = np.full((h, w), np.inf)
    f2 = np.full((h, w), np.inf)
    win_y = np.zeros((h, w), np.int64)
    win_x = np.zeros((h, w), np.int64)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            ny = (cy + dy) % cells
            nx = (cx + dx) % cells
            fpy = np.floor(cy + dy) + pts[ny, nx, 0]
            fpx = np.floor(cx + dx) + pts[ny, nx, 1]
            d = (gy - fpy) ** 2 + (gx - fpx) ** 2
            closer = d < f1
            f2 = np.where(closer, f1, np.minimum(f2, d))
            win_y = np.where(closer, ny, win_y)
            win_x = np.where(closer, nx, win_x)
            f1 = np.where(closer, d, f1)
    edge = np.sqrt(f2) - np.sqrt(f1)
    gap_mask = (edge < float(gap)).astype(np.float32)
    key = np.sin(win_y * 127.1 + win_x * 311.7 + float(seed % 997)) * 43758.5453
    cell_id = (key - np.floor(key)).astype(np.float32)
    return gap_mask, cell_id


def hash_grain(size, seed: int, *, label: str = "grain") -> np.ndarray:
    """Per-texel high-frequency value noise in ``[0, 1]`` — crisp, not smoothed.

    The anti-smear primitive: full-resolution white-ish grain (no lattice
    interpolation), so under Zoo's nearest-filter import it reads as sharp
    stipple — the Quake-2 hand-noise / Half-Life-2 detail-grain character.
    High-frequency, so it tiles seamlessly by repetition.
    """
    h, w = _as_hw(size)
    return rng(seed, label, h, w).random((h, w)).astype(np.float32)


def scratches(size, seed: int, *, axis: str = "x", density: float = 0.06,
              length_cells: int = 3, label: str = "scratch") -> np.ndarray:
    """Sparse, crisp, hard-edged directional scratches in ``[0, 1]`` (1 = scratch).

    Thin lines running along ``axis`` (wear on metal/plastic edges). Built by
    hard-thresholding an anisotropic field, so edges stay sharp rather than
    fading to a smear.
    """
    h, w = _as_hw(size)
    # Many short segments along the axis; sparse across it.
    if axis == "x":
        field = directional_grain((h, w), max(2, length_cells), max(8, h // 3),
                                  seed, axis="x", label=label + "_f")
    else:
        field = directional_grain((h, w), max(2, length_cells), max(8, w // 3),
                                  seed, axis="y", label=label + "_f")
    thr = np.quantile(field, 1.0 - float(np.clip(density, 0.0, 0.5)))
    return (field >= thr).astype(np.float32)


def streaks(size, seed: int, *, density: float = 0.25, decay: float = 0.95,
            label: str = "streaks") -> np.ndarray:
    """Vertical gravity streaks in ``[0, 1]`` — water/grime running down a wall.

    Sparse drip sources near the top of each column bleed downward with an
    exponential ``decay``, so the tile carries baked stain trails (the interior-
    concrete character). This is *tile-level* stain, distinct from Patina's
    mesh-aware ledge streaks — keep it subtle and let Patina own placement.
    Tileable top-to-bottom via a wrap pass that carries the tail across the seam.
    """
    h, w = _as_hw(size)
    r = rng(seed, label, h, w).random((h, w)).astype(np.float32)
    amp = rng(seed, label, "amp", h, w).random((h, w)).astype(np.float32)
    out = np.where(r < np.clip(density, 0.0, 1.0) * 0.04, amp, 0.0).astype(np.float32)
    for _ in range(2):                       # 2 passes → tail wraps the seam
        for y in range(1, h):
            out[y] = np.maximum(out[y], out[y - 1] * decay)
        out[0] = np.maximum(out[0], out[-1] * decay)
    m = out.max()
    return (out / m if m > 1e-6 else out).astype(np.float32)


def stripes(size, count: int, seed: int, *, axis: str = "x", seam: float = 0.35,
            jitter: float = 0.12, seam_width: float = 0.06,
            label: str = "stripes") -> np.ndarray:
    """Regular hard-seamed bands in ``[0, 1]`` — planks, siding, panels.

    ``count`` bands stacked along ``axis`` (``"x"`` = vertical bands). Each band
    gets its own seeded tone (``jitter``) and a crisp dark seam line of
    ``seam_width`` between bands. Tileable: the band pattern repeats with the
    tile, and the wrap edge is itself a seam.
    """
    h, w = _as_hw(size)
    count = max(1, int(count))
    dim = w if axis == "x" else h
    t = (np.arange(dim, dtype=np.float64) / dim) * count
    b = (np.floor(t).astype(np.int64)) % count
    frac = t - np.floor(t)
    tones = rng(seed, label, axis, count).random(count)
    line = 0.5 + (tones[b] - 0.5) * (2.0 * jitter)
    seam_mask = (frac < seam_width) | (frac > 1.0 - seam_width)
    line = line - seam * seam_mask
    line = np.clip(line, 0.0, 1.0).astype(np.float32)
    return np.broadcast_to(line[None, :] if axis == "x" else line[:, None],
                           (h, w)).astype(np.float32)


def weave(size, count: int, seed: int, *, label: str = "weave") -> np.ndarray:
    """Over/under woven thread pattern in ``[0, 1]`` — canvas, cloth, mesh.

    A ``count × count`` grid alternating warp/weft cells; each cell carries a
    thread highlight ridge across its short axis. Tileable by construction.
    """
    h, w = _as_hw(size)
    count = max(1, int(count))
    cx = (np.arange(w, dtype=np.float64) / w) * count
    cy = (np.arange(h, dtype=np.float64) / h) * count
    fx = (cx - np.floor(cx))[None, :]
    fy = (cy - np.floor(cy))[:, None]
    i = (np.floor(cx).astype(np.int64) % count)[None, :]
    j = (np.floor(cy).astype(np.int64) % count)[:, None]
    parity = (i + j) % 2
    ridge_h = 1.0 - np.abs(2.0 * fy - 1.0)      # bright mid-cell along Y
    ridge_v = 1.0 - np.abs(2.0 * fx - 1.0)      # bright mid-cell along X
    out = np.where(parity == 0, ridge_h + 0.0 * fx, ridge_v + 0.0 * fy)
    return (0.35 + 0.65 * out).astype(np.float32)


def veins(size, seed: int, *, base_cells: int = 4, octaves: int = 4,
          sharpness: float = 3.0, label: str = "veins") -> np.ndarray:
    """Tileable flowing vein network in ``[0, 1]`` (1 = on a vein).

    Ridged fractal noise (``1 − |2·fbm − 1|``) raised to ``sharpness`` gives
    thin branching ridge lines — marble/stone veining, cracked-glaze figure.
    Tileable because the underlying fbm is.
    """
    r = fbm(size, base_cells, octaves, seed, label=label)
    ridge = np.clip(1.0 - np.abs(2.0 * r - 1.0), 0.0, 1.0) ** max(1.0, sharpness)
    m = ridge.max()
    return (ridge / m if m > 1e-6 else ridge).astype(np.float32)


def masonry(size, rows: int, cols: int, seed: int, *, offset: float = 0.5,
            mortar: float = 0.05, label: str = "masonry"):
    """Brick/tile bond → ``(mortar_mask, unit_id)``, both ``float32`` in [0,1].

    ``offset=0.5`` is running bond (brick); ``offset=0`` with ``rows==cols`` is a
    square grid (tile). ``mortar_mask`` is 1 on the mortar/grout lines;
    ``unit_id`` is a stable per-unit random value for tone variation. Tileable
    for integer ``rows``/``cols`` (and even ``rows`` when offset).
    """
    h, w = _as_hw(size)
    rows, cols = max(1, int(rows)), max(1, int(cols))
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float64)
    ry = ys / h * rows
    row = np.floor(ry).astype(np.int64)
    fy = ry - np.floor(ry)
    rx = xs / w * cols + (row % 2) * offset
    col = np.floor(rx).astype(np.int64)
    fx = rx - np.floor(rx)
    mort = ((fy < mortar) | (fy > 1 - mortar)
            | (fx < mortar) | (fx > 1 - mortar)).astype(np.float32)
    key = np.sin(row * 127.1 + col * 311.7 + float(seed % 997)) * 43758.5453
    unit = (key - np.floor(key)).astype(np.float32)
    return mort, unit


def ribs(size, count: int, seed: int = 0, *, axis: str = "x",
         label: str = "ribs") -> np.ndarray:
    """Smooth sinusoidal ribs in ``[0, 1]`` — corrugated metal, fluting.

    ``count`` rounded ribs across ``axis``; tileable for integer ``count``.
    Posterize downstream for crisp stepped shading.
    """
    h, w = _as_hw(size)
    dim = w if axis == "x" else h
    t = np.arange(dim, dtype=np.float64) / dim * max(1, int(count))
    prof = (0.5 + 0.5 * np.cos(t * 2.0 * np.pi)).astype(np.float32)
    return np.broadcast_to(prof[None, :] if axis == "x" else prof[:, None],
                           (h, w)).astype(np.float32)


def wave(size, count: int, seed: int = 0, *, axis: str = "x", warp: float = 0.15,
         warp_cells: int = 4, label: str = "wave") -> np.ndarray:
    """Undulating sinusoidal bands in ``[0, 1]`` — reeded/fluted/wavy glass.

    ``count`` bands across ``axis`` (``"x"`` = vertical flutes), each phase-
    warped by low-frequency tileable noise so the ribs gently wander instead of
    ruling dead-straight (``warp=0`` gives perfectly straight reeded glass).
    Tileable for integer ``count`` (the warp noise wraps; the base cosine wraps
    when ``count`` is integer).
    """
    h, w = _as_hw(size)
    count = max(1, int(count))
    if axis == "x":
        base = np.broadcast_to((np.arange(w, dtype=np.float64) / w * count)[None, :],
                               (h, w)).copy()
    elif axis == "y":
        base = np.broadcast_to((np.arange(h, dtype=np.float64) / h * count)[:, None],
                               (h, w)).copy()
    else:
        raise ValueError("axis must be 'x' or 'y'")
    warpf = value_noise((h, w), max(1, int(warp_cells)), seed, label=label + "_warp")
    phase = base + warp * count * (warpf.astype(np.float64) - 0.5) * 2.0
    return (0.5 + 0.5 * np.cos(phase * 2.0 * np.pi)).astype(np.float32)


def posterize(arr: np.ndarray, levels: int) -> np.ndarray:
    """Quantise a ``[0, 1]`` field/array to ``levels`` hard steps (Q2 palette
    crispness). ``levels <= 1`` is a no-op."""
    levels = int(levels)
    if levels <= 1:
        return arr
    return np.round(np.clip(arr, 0.0, 1.0) * (levels - 1)) / (levels - 1)


# --------------------------------------------------------------------------- #
# Colour helpers
# --------------------------------------------------------------------------- #

def hex_to_rgb(value: str) -> np.ndarray:
    """'#rrggbb' → float32 RGB in [0, 1]."""
    s = value.lstrip("#")
    if len(s) != 6:
        raise ValueError(f"expected #rrggbb, got {value!r}")
    return np.array([int(s[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], np.float32)


def _as_hw(size):
    if isinstance(size, (tuple, list)):
        return int(size[0]), int(size[1])
    return int(size), int(size)
