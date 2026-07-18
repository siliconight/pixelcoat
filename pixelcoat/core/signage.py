"""Emissive signage / screen / label decals — the FPS "focal layer".

Neon signs, backlit panels (EXIT and friends), CRT/LCD screens, hazard stripes,
and directional arrows — the placed, often-glowing art that makes an
environment read as a *place* rather than a textured greybox. These are decals
(nearest-filtered, EXTEND, never tiled), packaged exactly like the traffic
lenses so Zoo's emissive-face path consumes them.

Text is drawn from a **built-in 5x7 pixel font** (below), so signage is
byte-deterministic and crisp with no system-font dependency — and the blocky
look is era-appropriate. Which sign is powered / how bright it glows is Lux's
call at runtime (emissive_energy); this module only authors the lit (and, where
useful, unpowered) art.
"""

from __future__ import annotations

import json
import os

import numpy as np
from PIL import Image

from . import procedural_surface as ps
from ..version import __version__, DEFAULT_SEED

__all__ = ["neon_sign", "panel_sign", "screen", "hazard_stripes", "arrow",
           "render_text", "build_sign_pack"]

# --------------------------------------------------------------------------- #
# Built-in 5x7 uppercase pixel font
# --------------------------------------------------------------------------- #

_FONT = {
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "C": ["01110", "10001", "10000", "10000", "10000", "10001", "01110"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "G": ["01110", "10001", "10000", "10111", "10001", "10001", "01110"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "I": ["11111", "00100", "00100", "00100", "00100", "00100", "11111"],
    "J": ["11111", "00001", "00001", "00001", "10001", "10001", "01110"],
    "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "N": ["10001", "11001", "10101", "10101", "10011", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "Q": ["01110", "10001", "10001", "10001", "10101", "10010", "01101"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
    "W": ["10001", "10001", "10001", "10101", "10101", "11011", "10001"],
    "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
    "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
    "Z": ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "11111"],
    "2": ["01110", "10001", "00001", "00110", "01000", "10000", "11111"],
    "3": ["11111", "00010", "00100", "00010", "00001", "10001", "01110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "11110", "00001", "00001", "10001", "01110"],
    "6": ["01110", "10000", "10000", "11110", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00001", "01110"],
    " ": ["00000", "00000", "00000", "00000", "00000", "00000", "00000"],
    "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
    "!": ["00100", "00100", "00100", "00100", "00100", "00000", "00100"],
    ".": ["00000", "00000", "00000", "00000", "00000", "00000", "00100"],
    ":": ["00000", "00100", "00100", "00000", "00100", "00100", "00000"],
    "/": ["00001", "00001", "00010", "00100", "01000", "10000", "10000"],
    "+": ["00000", "00100", "00100", "11111", "00100", "00100", "00000"],
    "'": ["00100", "00100", "00000", "00000", "00000", "00000", "00000"],
}
_GW, _GH = 5, 7


def render_text(text: str, *, scale: int = 4, spacing: int = 1) -> np.ndarray:
    """Rasterise ``text`` from the built-in font → a float mask (1 = ink)."""
    text = text.upper()
    glyphs = [_FONT.get(c, _FONT[" "]) for c in text]
    cols = len(glyphs) * (_GW + spacing) - spacing if glyphs else 0
    m = np.zeros((_GH, max(cols, 1)), np.float32)
    x = 0
    for g in glyphs:
        for r in range(_GH):
            row = g[r]
            for c in range(_GW):
                if row[c] == "1":
                    m[r, x + c] = 1.0
        x += _GW + spacing
    if scale > 1:
        m = np.repeat(np.repeat(m, scale, 0), scale, 1)
    return m


def _place_text(canvas_hw, text, scale, *, cx=0.5, cy=0.5):
    """Return a full-canvas mask with the text block centred at (cx, cy)."""
    h, w = canvas_hw
    ink = render_text(text, scale=scale)
    th, tw = ink.shape
    out = np.zeros((h, w), np.float32)
    y0 = int(round(cy * h - th / 2)); x0 = int(round(cx * w - tw / 2))
    ys0, xs0 = max(0, y0), max(0, x0)
    ye, xe = min(h, y0 + th), min(w, x0 + tw)
    if ye > ys0 and xe > xs0:
        out[ys0:ye, xs0:xe] = ink[ys0 - y0:ye - y0, xs0 - x0:xe - x0]
    return out


# --------------------------------------------------------------------------- #
# Effects
# --------------------------------------------------------------------------- #

def _blur(a: np.ndarray, radius: int) -> np.ndarray:
    if radius < 1:
        return a
    out = a.astype(np.float32)
    for _ in range(2):
        pad = np.pad(out, ((radius, radius), (radius, radius)), mode="edge")
        cs = np.cumsum(np.cumsum(pad, 0), 1)
        cs = np.pad(cs, ((1, 0), (1, 0)), mode="constant")
        k = 2 * radius + 1
        h, w = a.shape
        out = (cs[k:k + h, k:k + w] - cs[0:h, k:k + w]
               - cs[k:k + h, 0:w] + cs[0:h, 0:w]) / (k * k)
    return out


def _hw(size):
    return ps._as_hw(size)


# --------------------------------------------------------------------------- #
# Generators
# --------------------------------------------------------------------------- #

def neon_sign(text: str, size=128, *, color: str = "#ff2a6d",
              backer: str = "#0b0b10", scale: int = 5, glow: float = 0.6,
              powered: bool = True) -> dict:
    """Glowing neon tube text on a dark backer."""
    h, w = _hw(size)
    ink = _place_text((h, w), text, scale)
    tube = ps.hex_to_rgb(color)
    back = ps.hex_to_rgb(backer)
    halo = _blur(ink, max(2, scale)) * glow
    if powered:
        emis = tube[None, None] * (ink[..., None] + 0.5 * halo[..., None])
        alb = back[None, None] * (1 - ink[..., None]) + tube[None, None] * ink[..., None]
        alb = alb + tube[None, None] * 0.25 * halo[..., None]
    else:                                   # unpowered: dark grey tube, no glow
        grey = tube * 0.18
        emis = np.zeros((h, w, 3), np.float32)
        alb = back[None, None] * (1 - ink[..., None]) + grey[None, None] * ink[..., None]
    return _pack_arrays(alb, emis, glass=ink)


def panel_sign(text: str, size=128, *, panel: str = "#12351f",
               text_color: str = "#4dff8a", scale: int = 6,
               powered: bool = True, border: str | None = None) -> dict:
    """Backlit panel sign — glowing letters on a lit panel (EXIT, OPEN, ...)."""
    h, w = _hw(size)
    ink = _place_text((h, w), text, scale)
    pan = ps.hex_to_rgb(panel)
    txt = ps.hex_to_rgb(text_color)
    field = pan[None, None] * np.ones((h, w, 1), np.float32)
    if border:
        b = ps.hex_to_rgb(border)
        edge = np.ones((h, w), np.float32)
        m = max(2, h // 16)
        edge[m:-m, m:-m] = 0.0
        field = field * (1 - edge[..., None]) + b[None, None] * edge[..., None]
    alb = field * (1 - ink[..., None]) + txt[None, None] * ink[..., None]
    if powered:
        emis = txt[None, None] * ink[..., None] + pan[None, None] * 0.5 * (1 - ink[..., None])
    else:
        alb = alb * 0.4
        emis = np.zeros((h, w, 3), np.float32)
    return _pack_arrays(alb, emis)


def screen(mode: str = "bars", size=128, *, seed: int = DEFAULT_SEED,
           tint: str = "#39ff88", powered: bool = True,
           scanlines: bool = True) -> dict:
    """CRT/LCD screen content. mode: bars | static | terminal | off."""
    h, w = _hw(size)
    if not powered or mode == "off":
        base = np.tile(ps.hex_to_rgb("#0a0d0a"), (h, w, 1))
        return _pack_arrays(base, base * 0.15)
    if mode == "bars":                      # SMPTE-ish vertical colour bars
        cols = ["#c0c0c0", "#c0c000", "#00c0c0", "#00c000",
                "#c000c0", "#c00000", "#0000c0", "#101010"]
        idx = (np.arange(w) / w * len(cols)).astype(int).clip(0, len(cols) - 1)
        row = np.stack([ps.hex_to_rgb(cols[i]) for i in idx], 0)   # (w,3)
        img = np.broadcast_to(row[None], (h, w, 3)).copy()
    elif mode == "static":                  # RGB snow
        img = ps.rng(seed, "static").random((h, w, 3)).astype(np.float32)
        img = ps.posterize(img, 6)
    elif mode == "terminal":                # dark screen, lines of glyph text
        img = np.tile(ps.hex_to_rgb("#04120a"), (h, w, 1))
        t = ps.hex_to_rgb(tint)
        lines = ["READY.", "RUN", "LOADING", "OK 100%", "> _"]
        sc = max(1, h // 48)
        y = int(h * 0.12)
        for i, ln in enumerate(lines):
            ink = _place_text((h, w), ln, sc, cx=0.30, cy=(y + i * sc * 11) / h)
            img = img * (1 - ink[..., None]) + t[None, None] * ink[..., None]
    else:
        raise ValueError(f"unknown screen mode {mode!r}")
    if scanlines:
        sl = np.ones(h, np.float32)
        sl[::2] = 0.72
        img = img * sl[:, None, None]
    return _pack_arrays(img, img * 0.9)     # a screen is its own light


def hazard_stripes(size=128, *, colors=("#f2c00e", "#141414"), stripes: int = 6,
                   powered: bool = False, tint: str = "#f2c00e") -> dict:
    """Diagonal hazard chevrons (warning border / kick-plate)."""
    h, w = _hw(size)
    a = ps.hex_to_rgb(colors[0]); b = ps.hex_to_rgb(colors[1])
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    band = np.floor(((xx + yy) / (h + w) * stripes * 2) % 2)
    alb = np.where(band[..., None] > 0, a[None, None], b[None, None]).astype(np.float32)
    emis = alb * 0.6 if powered else np.zeros((h, w, 3), np.float32)
    return _pack_arrays(alb, emis)


def arrow(size=128, *, direction: str = "right", color: str = "#f5f5f5",
          backer: str = "#101216", powered: bool = False) -> dict:
    """A directional chevron arrow decal."""
    h, w = _hw(size)
    yy, xx = (np.mgrid[0:h, 0:w].astype(np.float32) + 0.5)
    u, v = xx / w - 0.5, yy / h - 0.5
    if direction in ("left", "right"):
        p = -u if direction == "right" else u    # vertex points toward `direction`
        chev = (np.abs(v) <= (p + 0.25)) & (np.abs(v) >= (p - 0.02)) & (p <= 0.3) & (p >= -0.3)
    elif direction in ("up", "down"):
        p = v if direction == "up" else -v
        chev = (np.abs(u) <= (p + 0.25)) & (np.abs(u) >= (p - 0.02)) & (p <= 0.3) & (p >= -0.3)
    else:
        raise ValueError("direction must be left/right/up/down")
    m = chev.astype(np.float32)
    col = ps.hex_to_rgb(color); back = ps.hex_to_rgb(backer)
    alb = back[None, None] * (1 - m[..., None]) + col[None, None] * m[..., None]
    emis = col[None, None] * m[..., None] if powered else np.zeros((h, w, 3), np.float32)
    return _pack_arrays(alb, emis)


# --------------------------------------------------------------------------- #
# Packaging
# --------------------------------------------------------------------------- #

def _pack_arrays(albedo, emissive, glass=None) -> dict:
    out = {"albedo": _u8(np.clip(albedo, 0, 1)),
           "emissive": _u8(np.clip(emissive, 0, 1))}
    # Emissive faces read smooth; a glass mask (neon tube) is glossier.
    if glass is not None:
        rough = np.where(glass > 0, 0.2, 0.6).astype(np.float32)
    else:
        rough = np.full(albedo.shape[:2], 0.5, np.float32)
    out["roughness"] = _u8(rough)
    return out


def build_sign_pack(pack_dir: str, arrays: dict, asset_id: str,
                    *, meters_per_tile: float = 1.0) -> dict:
    """Write a signage decal pack (albedo + emissive + roughness) for Zoo."""
    os.makedirs(pack_dir, exist_ok=True)
    maps: dict[str, str] = {}
    for key, arr in arrays.items():
        fname = f"{asset_id}_{key}.png"
        _write_png(arr, os.path.join(pack_dir, fname))
        maps[key] = fname
    manifest = {
        "schema": "pixelcoat-pack/2",
        "tool_version": __version__,
        "asset_id": asset_id,
        "processing_mode": "decal",
        "source_kind": "procedural",
        "maps": maps,
        "tileable": None,
        "meters_per_tile": float(meters_per_tile),
        "import_hints": {
            "color_space": {k: ("srgb" if k in ("albedo", "emissive") else "linear")
                            for k in maps},
            "interpolation": "nearest", "extension": "extend", "emissive": True,
        },
    }
    with open(os.path.join(pack_dir, f"{asset_id}.pack.json"), "w",
              encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    return manifest


def _u8(a):
    return np.rint(np.clip(a, 0, 1) * 255).astype(np.uint8)


def _write_png(u8, path):
    mode = "L" if u8.ndim == 2 else ("RGBA" if u8.shape[-1] == 4 else "RGB")
    Image.fromarray(u8, mode).save(path, optimize=False)
