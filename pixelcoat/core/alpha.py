"""Alpha extraction and decal controls (TDD §7.11).

Alpha SOURCES run at source resolution, before downsampling, so edge
feathering happens in source space and the box downsample turns the
feathered edge into clean coverage values at working resolution:

source     the image's own alpha channel
color_key  chroma-key removal (key color + tolerance, soft shoulder)
luminance  threshold on luma (invert for dark-on-light subjects)
mask       an authored grayscale mask
flood      background flood select seeded from the four corners
           (PIL's C floodfill; tolerance is per-channel 0..1)

Edge-guided subject extraction and polygon selection are deliberately
absent — the TDD's MVP guidance is manual masks over unreliable
recognition, and polygons belong to the GUI era.

Decal CONTROLS run at working resolution, after quantize + dither:
cutoff, pixel-hard alpha, dilation, and transparent-RGB cleanup
(defringe: transparent pixels take extruded neighbor colors so bilinear
sampling and mipmaps never pull a fringe from stale background RGB —
the §7.11 acceptance criterion).
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from . import frequency


# --------------------------------------------------------- source stage

def extract(arr: np.ndarray, a) -> np.ndarray:
    """RGBA float32 (source res) + Alpha recipe group -> alpha 0..1."""
    rgb = arr[..., :3]
    if a.source == "source":
        out = arr[..., 3].copy()
    elif a.source == "color_key":
        key = _hex_to_rgb(a.color_key)
        dist = np.abs(rgb - key).max(axis=-1)
        # soft shoulder: fully keyed inside tol, opaque past 1.5x tol
        out = np.clip((dist - a.tolerance) / max(a.tolerance * 0.5, 1e-4),
                      0.0, 1.0)
    elif a.source == "luminance":
        luma = rgb @ np.array([0.2126, 0.7152, 0.0722], np.float32)
        out = (luma >= a.luminance_threshold).astype(np.float32)
        if a.invert:
            out = 1.0 - out
    elif a.source == "mask":
        im = Image.open(a.mask_path).convert("L")
        if im.size != (arr.shape[1], arr.shape[0]):
            im = im.resize((arr.shape[1], arr.shape[0]), Image.NEAREST)
        out = np.asarray(im, np.float32) / 255.0
    elif a.source == "flood":
        out = 1.0 - _flood_background(rgb, a.flood_tolerance)
    else:
        raise ValueError(f"unknown alpha source '{a.source}'")

    if a.feather > 0:
        out = frequency.smooth_blur(out.astype(np.float32),
                                    max(1, int(round(a.feather))),
                                    wrap_x=False, wrap_y=False)
    return np.clip(out, 0.0, 1.0).astype(np.float32)


def _hex_to_rgb(code: str) -> np.ndarray:
    code = code.lstrip("#")
    return np.array([int(code[i:i + 2], 16) / 255.0 for i in (0, 2, 4)],
                    np.float32)


def _flood_background(rgb: np.ndarray, tol: float) -> np.ndarray:
    """Corner-seeded background select via PIL floodfill (C speed,
    deterministic). Returns background mask 0/1."""
    h, w = rgb.shape[:2]
    img8 = (np.clip(rgb, 0, 1) * 255).astype(np.uint8)
    sentinel = _free_color(img8)
    im = Image.fromarray(img8, "RGB")
    thresh = int(round(tol * 255)) * 3      # PIL: sum of channel diffs
    for xy in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        if im.getpixel(xy) != sentinel:
            ImageDraw.floodfill(im, xy, sentinel, thresh=thresh)
    out = np.asarray(im, np.uint8)
    return (out == np.array(sentinel, np.uint8)).all(axis=-1) \
        .astype(np.float32)


def _free_color(img8: np.ndarray) -> tuple[int, int, int]:
    used = {tuple(c) for c in
            np.unique(img8.reshape(-1, 3), axis=0)[:4096]}
    for cand in ((255, 0, 255), (0, 255, 0), (255, 255, 0), (0, 0, 255),
                 (1, 2, 3), (254, 1, 254), (3, 252, 3), (7, 7, 7)):
        if cand not in used:
            return cand
    return (255, 0, 254)                     # 4096+ colors: collision-safe
                                             # enough for a flood sentinel


# -------------------------------------------------------- working stage

def finalize(rgb: np.ndarray, alpha: np.ndarray,
             a) -> tuple[np.ndarray, np.ndarray]:
    """Cutoff / pixel-hard / dilate / defringe at working resolution.
    Returns (rgb, alpha) — rgb has transparent regions rewritten with
    extruded opaque colors (border extrusion + transparent RGB cleanup
    in one move)."""
    out_a = np.where(alpha < a.cutoff, 0.0, alpha).astype(np.float32)
    if a.pixel_hard:
        out_a = (out_a > 0).astype(np.float32)

    opaque = out_a > 0
    if a.rgb_cleanup and not opaque.all() and opaque.any():
        rgb = _defringe(rgb, opaque)

    if a.dilate > 0 and opaque.any():
        grown = opaque.copy()
        for _ in range(a.dilate):
            grown = _dilate(grown)
        out_a = np.where(grown & ~opaque, 1.0, out_a)
    return rgb.astype(np.float32), out_a


def _defringe(rgb: np.ndarray, opaque: np.ndarray) -> np.ndarray:
    """Fill transparent RGB by iteratively extruding opaque neighbor
    means; whatever a 64-pass front can't reach takes the mean opaque
    color. Transparent pixels never keep stale background RGB."""
    out = rgb.copy()
    known = opaque.copy()
    for _ in range(64):
        if known.all():
            break
        acc = np.zeros_like(out)
        cnt = np.zeros(known.shape, np.float32)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            s_rgb = np.roll(out, (dy, dx), axis=(0, 1))
            s_known = np.roll(known, (dy, dx), axis=(0, 1))
            if dy:
                s_known[0 if dy == 1 else -1, :] = False
            if dx:
                s_known[:, 0 if dx == 1 else -1] = False
            acc += s_rgb * s_known[..., None]
            cnt += s_known
        newly = ~known & (cnt > 0)
        if not newly.any():
            break
        out[newly] = acc[newly] / cnt[newly][..., None]
        known |= newly
    if not known.all():
        out[~known] = rgb[opaque].reshape(-1, 3).mean(axis=0)
    return out


def _dilate(m: np.ndarray) -> np.ndarray:
    out = m.copy()
    out[1:, :] |= m[:-1, :]
    out[:-1, :] |= m[1:, :]
    out[:, 1:] |= m[:, :-1]
    out[:, :-1] |= m[:, 1:]
    return out
