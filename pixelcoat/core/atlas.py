"""Atlas and trim-sheet packing (TDD §7.15, output §8.3).

Packs compatible pixelcoat packs into one atlas per map — every entry's
albedo lands in ``<atlas>_albedo.png`` at the same rect its normal
occupies in ``<atlas>_normal.png``, so a single UV rect drives every
channel. Maps missing from some entries are filled with that map's
neutral value (flat normal, mid roughness, black emissive) rather than
rejecting the pack.

Packing is a deterministic shelf packer: entries sort by height
descending, then asset id ascending — same inputs, same atlas bytes,
always. Rotation (90°, recorded per entry) is on by default and only
taken when it makes an entry wider than tall, which is what shelf
packing wants. Gutters extrude each entry's edge pixels (mipmap-safe
RGB) while alpha stays ZERO in the gutter, so decal atlases sample
clean at every filter level — same rule the single-decal exporter uses.

The manifest (``<atlas>_atlas.json``, schema pixelcoat-atlas/1) follows
the TDD §7.15 example: rect_px, uv, pivot, alpha_mode per entry, plus
which maps exist and each entry's source pack.
"""

from __future__ import annotations

import json
import os
import time

import numpy as np
from PIL import Image

from ..version import __version__
from . import image_io

_NEUTRAL = {
    "normal": (0.5, 0.5, 1.0),
    "roughness": (0.5, 0.5, 0.5),
    "height": (0.5, 0.5, 0.5),
    "emissive": (0.0, 0.0, 0.0),
    "mask": (0.0, 0.0, 0.0),
}
_DEFAULT_NEUTRAL = (0.0, 0.0, 0.0)


def build_atlas(pack_paths: list[str], name: str, out_dir: str,
                gutter: int = 2, pow2: bool = False,
                allow_rotate: bool = True) -> dict:
    """Pack the given ``.pack.json`` files into one atlas. Returns the
    build report."""
    t0 = time.perf_counter()
    entries = [_load_entry(p) for p in sorted(pack_paths)]
    if not entries:
        raise ValueError("no packs to atlas")
    modes = {e["mode"] for e in entries}
    if len(modes) > 1:
        raise ValueError(
            f"cannot atlas mixed processing modes {sorted(modes)}; "
            "group inputs by mode")

    map_keys = sorted({k for e in entries for k in e["maps"]})
    if "albedo" not in map_keys:
        raise ValueError("entries have no albedo maps")

    rects = _shelf_pack(entries, gutter, allow_rotate)
    aw = max(r["x"] + r["w"] + gutter for r in rects.values())
    ah = max(r["y"] + r["h"] + gutter for r in rects.values())
    if pow2:
        aw = 1 << (aw - 1).bit_length()
        ah = 1 << (ah - 1).bit_length()

    has_alpha = any(e["maps"]["albedo"].shape[2] == 4 for e in entries
                    if "albedo" in e["maps"])

    atlas_dir = os.path.join(out_dir, name)
    os.makedirs(atlas_dir, exist_ok=True)
    map_files: dict[str, str] = {}
    for key in map_keys:
        canvas = _compose(entries, rects, key, aw, ah, gutter,
                          has_alpha and key.endswith("albedo"))
        fname = f"{name}_{key}.png"
        image_io.save_png(canvas, os.path.join(atlas_dir, fname))
        map_files[key] = fname

    manifest = {
        "schema_version": "pixelcoat-atlas/1",
        "tool_version": __version__,
        "atlas": name,
        "width": aw,
        "height": ah,
        "gutter": gutter,
        "maps": map_files,
        "entries": [
            {
                "id": e["asset_id"],
                "rect_px": [r["x"], r["y"], r["w"], r["h"]],
                "uv": [r["x"] / aw, r["y"] / ah,
                       (r["x"] + r["w"]) / aw, (r["y"] + r["h"]) / ah],
                "rotated": r["rot"],
                "pivot": [0.5, 0.5],
                "alpha_mode": "cutout" if has_alpha else "opaque",
                "source_pack": e["pack_file"],
            }
            for e in entries
            for r in [rects[e["asset_id"]]]
        ],
    }
    mpath = os.path.join(atlas_dir, f"{name}_atlas.json")
    with open(mpath, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)

    _preview(entries, rects, atlas_dir, name, map_files, aw, ah)

    return {
        "tool_version": __version__,
        "atlas": name,
        "entries": len(entries),
        "size": [aw, ah],
        "occupancy": round(sum(r["w"] * r["h"] for r in rects.values())
                           / float(aw * ah), 3),
        "maps": map_keys,
        "files": sorted(map_files.values())
        + [f"{name}_atlas.json", f"{name}_preview.png"],
        "duration_seconds": round(time.perf_counter() - t0, 4),
    }


# ---------------------------------------------------------------- load

def _load_entry(pack_path: str) -> dict:
    with open(pack_path, encoding="utf-8") as f:
        pack = json.load(f)
    base = os.path.dirname(os.path.abspath(pack_path))
    maps: dict[str, np.ndarray] = {}
    for key, fname in pack.get("maps", {}).items():
        arr = np.asarray(Image.open(os.path.join(base, fname))
                         .convert("RGBA"), np.float32) / 255.0
        maps[key] = arr
    if not maps:
        raise ValueError(f"{pack_path}: pack has no maps")
    sizes = {a.shape[:2] for a in maps.values()}
    if len(sizes) > 1:
        raise ValueError(f"{pack_path}: maps are not aligned {sizes}")
    return {
        "asset_id": pack.get("asset_id", os.path.basename(base)),
        "pack_file": os.path.basename(pack_path),
        "mode": pack.get("processing_mode", "pixel"),
        "maps": maps,
    }


# ---------------------------------------------------------------- pack

def _shelf_pack(entries: list[dict], gutter: int,
                allow_rotate: bool) -> dict[str, dict]:
    """Deterministic shelf packing. Entries sorted tallest-first (ties by
    asset id) fill left-to-right shelves inside a width chosen from the
    total area."""
    items = []
    for e in entries:
        h, w = next(iter(e["maps"].values())).shape[:2]
        rot = allow_rotate and h > w
        if rot:
            w, h = h, w
        items.append({"id": e["asset_id"], "w": w, "h": h, "rot": rot})
    items.sort(key=lambda i: (-i["h"], i["id"]))

    area = sum((i["w"] + gutter) * (i["h"] + gutter) for i in items)
    target_w = max(max(i["w"] for i in items) + 2 * gutter,
                   int(np.ceil(np.sqrt(area) / 4.0)) * 4)

    rects: dict[str, dict] = {}
    x, y, shelf_h = gutter, gutter, 0
    for i in items:
        if x + i["w"] + gutter > target_w and x > gutter:
            x = gutter
            y += shelf_h + gutter
            shelf_h = 0
        rects[i["id"]] = {"x": x, "y": y, "w": i["w"], "h": i["h"],
                          "rot": i["rot"]}
        x += i["w"] + gutter
        shelf_h = max(shelf_h, i["h"])
    return rects


# ------------------------------------------------------------- compose

def _compose(entries: list[dict], rects: dict, key: str, aw: int, ah: int,
             gutter: int, alpha_gutter_zero: bool) -> np.ndarray:
    neutral = _NEUTRAL.get(key.split("_")[-1], _DEFAULT_NEUTRAL)
    canvas = np.zeros((ah, aw, 4), np.float32)
    canvas[..., :3] = neutral
    canvas[..., 3] = 0.0 if alpha_gutter_zero else 1.0

    for e in entries:
        r = rects[e["asset_id"]]
        arr = e["maps"].get(key)
        if arr is None:
            arr = np.empty((r["h"], r["w"], 4), np.float32)
            arr[..., :3] = neutral
            arr[..., 3] = 1.0
        elif r["rot"]:
            arr = np.rot90(arr, k=-1)          # 90° clockwise
        x, y, w, h = r["x"], r["y"], r["w"], r["h"]
        canvas[y:y + h, x:x + w] = arr
        # Gutter extrusion: edge pixels repeat HALF a gutter outward, so
        # two entries sharing a gutter strip each own their side of it
        # (mipmap-safe RGB). Alpha stays zero in the ring for decal
        # atlases — filter-safe transparency.
        g = (gutter + 1) // 2
        y0, x0 = max(0, y - g), max(0, x - g)
        y1, x1 = min(ah, y + h + g), min(aw, x + w + g)
        ring = canvas[y0:y1, x0:x1]
        top, left = y - y0, x - x0
        ex = np.pad(arr, ((top, ring.shape[0] - top - h),
                          (left, ring.shape[1] - left - w), (0, 0)),
                    mode="edge")
        if alpha_gutter_zero:
            ex[..., 3] = 0.0
            ex[top:top + h, left:left + w, 3] = arr[..., 3]
        ring[:] = ex
    return canvas


def _preview(entries: list[dict], rects: dict, atlas_dir: str, name: str,
             map_files: dict, aw: int, ah: int) -> None:
    """Albedo with entry rects outlined (§8.3 <atlas>_preview.png)."""
    from PIL import ImageDraw
    im = Image.open(os.path.join(atlas_dir, map_files["albedo"])) \
        .convert("RGB")
    d = ImageDraw.Draw(im)
    for e in entries:
        r = rects[e["asset_id"]]
        d.rectangle((r["x"] - 1, r["y"] - 1,
                     r["x"] + r["w"], r["y"] + r["h"]),
                    outline=(255, 64, 255))
    im.save(os.path.join(atlas_dir, f"{name}_preview.png"))
