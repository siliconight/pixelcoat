"""Procedural emissive decals — small, crisp, glowing faces (not tiling).

Where ``material_grammar`` authors *tiling* surfaces, this authors *placed*
emissive art: a traffic-signal lens, and the pack that Zoo's emissive-face path
(`make_emissive_textured_material`, albedo → emission) consumes. These are
decals — nearest-filtered, EXTEND (never tiled), one per authored face.

Design notes tied to the verified runtime:
- The lens glow lives in the **albedo brightness** (Zoo's sign path drives
  emission from albedo). A separate ``emissive`` map is also written so the
  tiling import path picks it up too. Either way the *lit vs off* difference is
  baked as two albedo variants — which lens is glowing at runtime is Lux's /
  gameplay's call via ``emissive_energy`` per material, never baked switching.
- Crisp by construction: posterized, nearest-friendly, so it reads sharp under
  Zoo's Closest import rather than as a soft blob.
"""

from __future__ import annotations

import json
import os

import numpy as np
from PIL import Image

from . import procedural_surface as ps
from ..version import __version__, DEFAULT_SEED

__all__ = ["traffic_lens", "build_lens_pack", "LENS_COLORS"]

# Lit lens colours (bright, so they push past Lux's glow threshold) and their
# dark "off" glass counterparts.
LENS_COLORS = {
    "red":    {"lit": "#ec2b18", "off": "#3a120c"},
    "yellow": {"lit": "#f4b021", "off": "#3f2f0a"},
    "green":  {"lit": "#37c04e", "off": "#123f1e"},
}


def traffic_lens(size: int = 128, *, color: str = "red", state: str = "lit",
                 housing: str = "#14161a", rings: int = 7, visor: bool = True,
                 posterize_levels: int = 8) -> dict:
    """Draw one signal lens as ``{albedo (H,W,3 u8), emissive (H,W,3 u8),
    roughness (H,W u8)}``. Deterministic; no RNG.

    A dark housing square with a centred glass disc: concentric fresnel rings,
    a hot centre when lit, and a hood/visor shadow across the top.
    """
    if state not in ("lit", "off"):
        raise ValueError("state must be 'lit' or 'off'")
    n = int(size)
    ys, xs = np.mgrid[0:n, 0:n].astype(np.float32)
    c = (n - 1) / 2.0
    r = np.sqrt((xs - c) ** 2 + (ys - c) ** 2) / (n * 0.5)      # 0 centre → ~1 edge
    R = 0.86                                                    # lens radius
    disc = (r <= R).astype(np.float32)

    lit_rgb = ps.hex_to_rgb(LENS_COLORS.get(color, {}).get("lit", color)) \
        if color in LENS_COLORS else ps.hex_to_rgb(color)
    off_rgb = ps.hex_to_rgb(LENS_COLORS.get(color, {}).get("off", "#301010")) \
        if color in LENS_COLORS else lit_rgb * 0.25
    house = ps.hex_to_rgb(housing)

    ring = 0.62 + 0.38 * (0.5 + 0.5 * np.cos(np.clip(r / R, 0, 1) * rings * np.pi))

    if state == "lit":
        lens = lit_rgb[None, None] * ring[..., None]
        center = np.clip(1.0 - r / (R * 0.55), 0.0, 1.0) ** 2      # hot core
        lens = np.clip(lens + lit_rgb[None, None] * 0.7 * center[..., None], 0, 1)
        glow = lens.copy()
    else:
        lens = np.clip(off_rgb[None, None] * ring[..., None], 0, 1)
        glow = lens * 0.08

    # Hood/visor shadow across the top of the lens.
    if visor:
        top = np.clip(-(ys - c) / (n * 0.5), 0.0, 1.0) * disc     # 1 at top edge
        shade = 1.0 - 0.4 * top
        lens = lens * shade[..., None]
        glow = glow * (1.0 - 0.3 * top)[..., None]

    # Thin dark rim at the lens edge (the bezel).
    rim = np.clip((r - (R - 0.06)) / 0.06, 0.0, 1.0) * disc
    lens = lens * (1.0 - 0.6 * rim)[..., None]

    albedo = house[None, None] * (1 - disc[..., None]) + lens * disc[..., None]
    emissive = glow * disc[..., None]

    albedo = ps.posterize(np.clip(albedo, 0, 1), posterize_levels)
    emissive = ps.posterize(np.clip(emissive, 0, 1), posterize_levels)
    # Glass is smooth; roughness is low over the lens, higher on the housing.
    rough = np.where(disc > 0, 0.15, 0.7).astype(np.float32)

    return {"albedo": _u8(albedo), "emissive": _u8(emissive), "roughness": _u8(rough)}


def build_lens_pack(pack_dir: str, *, color: str = "red", state: str = "lit",
                    size: int = 128, asset_id: str | None = None) -> dict:
    """Draw a lens and write a Zoo-consumable emissive decal pack into ``pack_dir``."""
    asset_id = asset_id or f"signal_lens_{color}_{state}"
    arrays = traffic_lens(size, color=color, state=state)
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
        "tileable": None,                       # a lens face never tiles
        "meters_per_tile": 1.0,
        "import_hints": {
            "color_space": {k: ("srgb" if k in ("albedo", "emissive") else "linear")
                            for k in maps},
            "interpolation": "nearest",
            "extension": "extend",
            "emissive": True,
        },
    }
    with open(os.path.join(pack_dir, f"{asset_id}.pack.json"), "w",
              encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    return manifest


def _u8(arr: np.ndarray) -> np.ndarray:
    return np.rint(np.clip(arr, 0.0, 1.0) * 255.0).astype(np.uint8)


def _write_png(u8: np.ndarray, path: str) -> None:
    mode = "L" if u8.ndim == 2 else ("RGBA" if u8.shape[-1] == 4 else "RGB")
    Image.fromarray(u8, mode).save(path, optimize=False)
