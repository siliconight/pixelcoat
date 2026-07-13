"""Mipmap and legacy block-compression previews (roadmap §18–19).

Everything here is PREVIEW-ONLY: nothing in this module may alter a
canonical PNG export. Outputs land under ``<asset>/previews/``.

Mip chains downsample color in linear working space and renormalize
normal vectors at every level; the mean pre-renormalization vector
length is the shimmer metric — noisy normals average toward zero, and a
short mean vector at distance is exactly what reads as sparkle/shimmer
on Gen7 hardware (and why Godot's roughness filtering wants the source
normal, which the pack's import_hints already name).

The block compressors are deterministic pure-NumPy approximations of the
4×4 BC/DXT families — endpoint range fits, not a production encoder.
They exist so an artist can see whether a surface survives 2006-era
compression before committing art direction, and they are close enough
to real BC1/BC4/BC5 output for that judgment.
"""

from __future__ import annotations

import numpy as np

from . import color_space as cs

_FAMILIES = {"color_block", "color_alpha", "two_channel", "single_channel"}


def suggest_family(map_name: str, has_varying_alpha: bool = False) -> str:
    """Suggested legacy compression family for a canonical map (§19)."""
    if map_name.endswith("albedo"):
        return "color_alpha" if has_varying_alpha else "color_block"
    if map_name.endswith("normal"):
        return "two_channel"
    return "single_channel"


# ------------------------------------------------------------- mipmaps

def mip_chain(arr: np.ndarray, is_normal: bool,
              min_size: int = 8) -> tuple[list[np.ndarray], list[float]]:
    """Linear-space 2× box mip chain. Returns (levels, mean vector length
    per level BEFORE renormalization — 1.0 for non-normal maps)."""
    levels = [arr.astype(np.float32)]
    lengths = [1.0]
    cur = levels[0]
    while min(cur.shape[0], cur.shape[1]) >= min_size * 2:
        h, w = cur.shape[0] // 2 * 2, cur.shape[1] // 2 * 2
        c = cur[:h, :w]
        down = (c[0::2, 0::2] + c[1::2, 0::2] +
                c[0::2, 1::2] + c[1::2, 1::2]) * 0.25
        if is_normal:
            vec = down[..., :3] * 2.0 - 1.0
            ln = np.linalg.norm(vec, axis=-1, keepdims=True)
            lengths.append(float(ln.mean()))
            vec = vec / np.maximum(ln, 1e-6)
            down = down.copy()
            down[..., :3] = vec * 0.5 + 0.5
        else:
            lengths.append(1.0)
        levels.append(down.astype(np.float32))
        cur = down
    return levels, lengths


def mip_strip(levels: list[np.ndarray], gap: int = 4) -> np.ndarray:
    """Horizontal strip of all mip levels on mid-gray, largest first."""
    h = levels[0].shape[0]
    w = sum(lv.shape[1] for lv in levels) + gap * (len(levels) - 1)
    ch = levels[0].shape[2] if levels[0].ndim == 3 else 1
    canvas = np.full((h, w, ch), 0.5, np.float32)
    x = 0
    for lv in levels:
        if lv.ndim == 2:
            lv = lv[..., None]
        canvas[:lv.shape[0], x:x + lv.shape[1]] = lv
        x += lv.shape[1] + gap
    return canvas


def recommended_mip(distance_meters: float, meters_per_tile: float,
                    width: int, n_levels: int) -> int:
    """Which mip level roughly matches a viewing distance, assuming
    ~1 texel per screen pixel at 1 m for a 1024-wide, 1 m tile."""
    texels_per_meter = width / max(meters_per_tile, 1e-6)
    level = int(round(np.log2(max(distance_meters, 1.0)
                              * texels_per_meter / 1024.0) + 0.5))
    return int(np.clip(level, 0, n_levels - 1))


# ------------------------------------------- legacy block compression

def preview_block_compression(arr: np.ndarray,
                              family: str) -> np.ndarray:
    """Deterministic 4×4 block-compression preview. ``arr`` is float32
    0..1, (H, W, C). Dimensions are edge-padded to multiples of four for
    the preview only, then cropped back."""
    if family not in _FAMILIES:
        raise ValueError(f"unknown compression family '{family}'")
    h, w = arr.shape[:2]
    ph, pw = (-h) % 4, (-w) % 4
    if ph or pw:
        arr = np.pad(arr, ((0, ph), (0, pw), (0, 0)), mode="edge")

    if family == "single_channel":
        out = _bc4(arr[..., 0])[..., None].repeat(arr.shape[2], axis=-1)
    elif family == "two_channel":
        out = _bc5_normal(arr)
    elif family == "color_alpha":
        rgb = _bc1(arr[..., :3])
        a = _bc4(arr[..., 3]) if arr.shape[2] > 3 else None
        out = np.concatenate([rgb, a[..., None]], axis=-1) \
            if a is not None else rgb
    else:
        out = _bc1(arr[..., :3])
        if arr.shape[2] > 3:                     # carry alpha through
            out = np.concatenate([out, arr[..., 3:]], axis=-1)
    return out[:h, :w].astype(np.float32)


def _blocks(a: np.ndarray) -> np.ndarray:
    """(H, W, C) -> (N, 16, C) 4×4 blocks."""
    h, w = a.shape[:2]
    c = a.shape[2] if a.ndim == 3 else 1
    b = a.reshape(h // 4, 4, w // 4, 4, c).swapaxes(1, 2)
    return b.reshape(-1, 16, c)


def _unblocks(b: np.ndarray, h: int, w: int) -> np.ndarray:
    c = b.shape[-1]
    return b.reshape(h // 4, w // 4, 4, 4, c).swapaxes(1, 2) \
            .reshape(h, w, c)


def _bc1(rgb: np.ndarray) -> np.ndarray:
    """BC1-style: two RGB565 endpoints per block (luminance range fit),
    a 4-entry interpolated palette, nearest assignment."""
    h, w = rgb.shape[:2]
    blocks = _blocks(rgb)                                   # (N, 16, 3)
    luma = blocks @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    lo = blocks[np.arange(len(blocks)), luma.argmin(axis=1)]
    hi = blocks[np.arange(len(blocks)), luma.argmax(axis=1)]
    lo, hi = _quant565(lo), _quant565(hi)
    pal = np.stack([lo, hi,
                    (2 * lo + hi) / 3.0,
                    (lo + 2 * hi) / 3.0], axis=1)           # (N, 4, 3)
    d = ((blocks[:, :, None, :] - pal[:, None, :, :]) ** 2).sum(-1)
    idx = d.argmin(axis=2)                                  # (N, 16)
    out = pal[np.arange(len(pal))[:, None], idx]
    return _unblocks(out, h, w)


def _quant565(c: np.ndarray) -> np.ndarray:
    bits = np.array([31.0, 63.0, 31.0], np.float32)
    return np.round(np.clip(c, 0, 1) * bits) / bits


def _bc4(gray: np.ndarray) -> np.ndarray:
    """BC4-style: per-block min/max endpoints (8-bit), 8-level ramp."""
    h, w = gray.shape[:2]
    blocks = _blocks(gray[..., None])[..., 0]               # (N, 16)
    lo = np.round(blocks.min(axis=1) * 255) / 255.0
    hi = np.round(blocks.max(axis=1) * 255) / 255.0
    t = np.linspace(0.0, 1.0, 8, dtype=np.float32)
    pal = lo[:, None] + (hi - lo)[:, None] * t[None, :]     # (N, 8)
    idx = np.abs(blocks[:, :, None] - pal[:, None, :]).argmin(axis=2)
    out = pal[np.arange(len(pal))[:, None], idx]
    return _unblocks(out[..., None], h, w)[..., 0]


def _bc5_normal(normal: np.ndarray) -> np.ndarray:
    """BC5-style: X and Y compressed independently, Z reconstructed and
    the vector renormalized (§19 required behavior)."""
    x = _bc4(normal[..., 0])
    y = _bc4(normal[..., 1])
    vx = x * 2.0 - 1.0
    vy = y * 2.0 - 1.0                     # sign convention passes through
    vz = np.sqrt(np.clip(1.0 - vx * vx - vy * vy, 0.0, 1.0))
    vec = np.stack([vx, vy, vz], axis=-1)
    vec = vec / np.maximum(np.linalg.norm(vec, axis=-1, keepdims=True),
                           1e-6)
    out = vec * 0.5 + 0.5
    if normal.shape[2] > 3:
        out = np.concatenate([out, normal[..., 3:]], axis=-1)
    return out


# ------------------------------------------------------------ tiling QA

def tile_grid(arr: np.ndarray, n: int = 3, max_px: int = 768) -> np.ndarray:
    """n×n repetition preview (§17), downscaled by integer stride."""
    tiled = np.tile(arr, (n, n, 1))
    stride = max(1, tiled.shape[0] // max_px)
    return tiled[::stride, ::stride]


def landmark_warnings(luma: np.ndarray, warnings: list[str],
                      block: int = 32, z: float = 8.0) -> None:
    """Flag unique landmarks that will read as obvious repeats (§17):
    coarse blocks whose mean luminance is a strong outlier against
    ROBUST background statistics (median/MAD, so the landmark itself
    can't inflate the yardstick the way it inflates a plain std)."""
    h, w = luma.shape
    bh, bw = h // block, w // block
    if bh < 3 or bw < 3:
        return
    m = luma[:bh * block, :bw * block] \
        .reshape(bh, block, bw, block).mean(axis=(1, 3))
    med = float(np.median(m))
    mad = float(np.median(np.abs(m - med)))
    if mad < 1e-5:
        return
    score = np.abs(m - med) / (1.4826 * mad)
    if float(score.max()) > z:
        by, bx = np.unravel_index(score.argmax(), score.shape)
        warnings.append(
            f"unique landmark near ({bx * block + block // 2}, "
            f"{by * block + block // 2}) will repeat visibly when tiled")
