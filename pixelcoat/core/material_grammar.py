"""Source-free material synthesis from a grammar (roadmap Technique T03).

A *material grammar* is structured data (JSON) describing how to build a
complete tiling material — base colour family, a macro/meso/micro frequency
budget, named procedural generators, and a response (roughness) rule — with no
reference photograph. :func:`synthesize` composes the primitives in
``procedural_surface`` into aligned map arrays; :func:`build_material_pack`
writes them to disk as a Pixelcoat pack that Zoo's ``core.skins.load_pack``
resolves directly.

Scope decisions (grounded in the factory's verified runtime, not guessed):

- **Albedo-first.** Zoo applies packs to per-vertex-lit StandardMaterial3D and
  the Lux stylized shader samples only albedo/emissive, so albedo carries the
  look. Roughness is emitted as a light response; a normal map is emitted only
  when the grammar asks (it pays off on Lux's pc2000 lightmapped path, and is
  inert on the default per-vertex path — emitting it is optional, never load-
  bearing).
- **Tiling by contract.** Every map is wrap-exact (the primitives guarantee it);
  the normal map is derived with wrapped derivatives so it tiles too.
- **Deterministic.** Same grammar + seed + size ⇒ byte-identical PNGs.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from PIL import Image

from . import maps, procedural_surface as ps
from ..version import __version__, DEFAULT_SEED

__all__ = ["MaterialGrammar", "synthesize", "build_material_pack",
           "build_theme_library"]

_DEFAULT_BANDS = {"macro": 0.4, "meso": 0.4, "micro": 0.2}


@dataclass
class MaterialGrammar:
    id: str
    kind: str = "concrete"                      # Zoo material-kind for resolution
    base_colors: list = field(default_factory=lambda: ["#808080"])
    undercoat: str | None = None                # exposed by chips (painted kinds)
    cavity: str | None = None                   # darkest recess colour
    meters_per_tile: float = 1.0
    bands: dict = field(default_factory=lambda: dict(_DEFAULT_BANDS))
    macro: dict = field(default_factory=dict)   # low-freq colour/condition drift
    meso: dict = field(default_factory=dict)    # material identity / structure
    micro: dict = field(default_factory=dict)   # close-range surface response
    chips: dict = field(default_factory=dict)   # optional damage (expose under/cavity)
    edges: dict = field(default_factory=dict)   # crisp cracks / seams (worley F2-F1)
    scratches: dict = field(default_factory=dict)  # crisp directional wear lines
    streaks: dict = field(default_factory=dict)  # vertical gravity grime/water stains
    form_lines: dict = field(default_factory=dict)  # horizontal form-board seams
    veins: dict = field(default_factory=dict)   # flowing veins (marble/stone)
    masonry: dict = field(default_factory=dict)  # brick/tile bond + mortar/grout
    aggregate: dict = field(default_factory=dict)  # filled Voronoi stones/chips
    detail_strength: float = 0.15               # crisp per-texel grain (anti-smear)
    albedo_pattern: float = 1.0                 # how much meso/micro/grain tint albedo
    posterize: int = 0                          # albedo value steps (Q2 crispness); 0 = off
    roughness: dict = field(default_factory=lambda: {"base": 0.7, "variation": 0.2})
    height_strength: float = 0.6
    emissive: dict = field(default_factory=dict)  # backlit glow (stained glass, screens)
    transparency: dict = field(default_factory=dict)  # see-through glass: {opacity, ior}
    emit: dict = field(default_factory=lambda: {"roughness": True, "normal": False})

    @classmethod
    def from_dict(cls, raw: dict) -> "MaterialGrammar":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in raw.items() if k in known})

    @classmethod
    def load(cls, path: str) -> "MaterialGrammar":
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))


# --------------------------------------------------------------------------- #
# Generator dispatch
# --------------------------------------------------------------------------- #

def _generator(spec: dict, size, seed: int, label: str) -> np.ndarray:
    """Evaluate a named generator spec → field in [0, 1]. Empty spec → flat 0.5."""
    if not spec:
        return np.full(_hw(size), 0.5, np.float32)
    gen = spec.get("generator", "fbm")
    if gen == "fbm":
        return ps.fbm(size, spec.get("cells", 32), spec.get("octaves", 3), seed,
                      label=label)
    if gen == "value_noise":
        return ps.value_noise(size, spec.get("cells", 16), seed, label=label)
    if gen == "directional_grain":
        return ps.directional_grain(
            size, spec.get("cells_along", 4), spec.get("cells_across", 48),
            seed, axis=spec.get("axis", "x"), label=label)
    if gen == "worley_f1":
        return ps.worley_f1(size, spec.get("cells", 12), seed, label=label)
    if gen == "worley_edges":
        return ps.worley_edges(size, spec.get("cells", 12), seed, label=label)
    if gen in ("hash_grain", "grain"):
        return ps.hash_grain(size, seed, label=label)
    if gen == "stripes":
        return ps.stripes(size, spec.get("count", 5), seed,
                          axis=spec.get("axis", "x"),
                          seam=spec.get("seam", 0.35),
                          jitter=spec.get("jitter", 0.12), label=label)
    if gen == "weave":
        return ps.weave(size, spec.get("count", 40), seed, label=label)
    if gen == "veins":
        return ps.veins(size, seed, base_cells=spec.get("cells", 4),
                        octaves=spec.get("octaves", 4),
                        sharpness=spec.get("sharpness", 3.0), label=label)
    if gen == "ribs":
        return ps.ribs(size, spec.get("count", 12), seed,
                       axis=spec.get("axis", "x"), label=label)
    if gen == "wave":
        return ps.wave(size, spec.get("count", 12), seed,
                       axis=spec.get("axis", "x"),
                       warp=spec.get("warp", 0.15),
                       warp_cells=spec.get("warp_cells", 4), label=label)
    raise ValueError(f"unknown generator {gen!r}")


def _centered(field01: np.ndarray) -> np.ndarray:
    """Map [0,1] → [-1,1] around the field's own mean (structure, not bias)."""
    return np.clip((field01 - float(field01.mean())) * 2.0, -1.0, 1.0)


def _hw(size):
    return ps._as_hw(size)


# --------------------------------------------------------------------------- #
# Synthesis
# --------------------------------------------------------------------------- #

def synthesize(grammar: MaterialGrammar, size=512, seed: int = DEFAULT_SEED) -> dict:
    """Compose a grammar into aligned map arrays.

    Returns a dict with ``albedo`` (H,W,3 uint8) and, per the grammar's ``emit``,
    ``roughness`` (H,W uint8) and ``normal`` (H,W,3 uint8). All tileable.
    """
    h, w = _hw(size)
    bands = {**_DEFAULT_BANDS, **(grammar.bands or {})}
    base_cols = [ps.hex_to_rgb(c) for c in grammar.base_colors] or [ps.hex_to_rgb("#808080")]

    # Macro: which base colour, plus a gentle value drift across the tile.
    macro = _generator(grammar.macro or {"generator": "fbm", "cells": 3, "octaves": 2},
                       (h, w), ps.stream_seed(seed, "macro"), "macro")
    if len(base_cols) > 1:
        sel = np.clip(macro * (len(base_cols) - 1), 0, len(base_cols) - 1 - 1e-6)
        lo = np.floor(sel).astype(int)
        fr = (sel - lo)[..., None]
        palette = np.stack(base_cols, 0)
        base = palette[lo] * (1 - fr) + palette[np.minimum(lo + 1, len(base_cols) - 1)] * fr
    else:
        base = np.broadcast_to(base_cols[0], (h, w, 3)).copy()
    base = base * (1.0 + bands["macro"] * 0.25 * _centered(macro)[..., None])

    # Meso: material identity / structure.
    meso = _generator(grammar.meso, (h, w), ps.stream_seed(seed, "meso"), "meso")
    meso_s = _centered(meso)

    # Micro: close-range breakup.
    micro = _generator(grammar.micro or {"generator": "fbm", "cells": 96, "octaves": 3},
                       (h, w), ps.stream_seed(seed, "micro"), "micro")
    micro_s = _centered(micro)

    # Crisp per-texel grain — the anti-smear layer. Full-res white-ish noise
    # (no lattice smoothing), so it survives Zoo's nearest-filter import as
    # sharp stipple rather than a soft blur.
    grain_s = _centered(ps.hash_grain((h, w), ps.stream_seed(seed, "grain"),
                                      label="grain"))

    # ``albedo_pattern`` scales how much the meso/micro/grain pattern tints the
    # albedo, independent of the height field (which keeps the full pattern for
    # the normal map). Glass wants a near-clear albedo (~0.1) with a strong
    # normal — set it low without flattening the bump.
    ap = grammar.albedo_pattern
    value_mod = (1.0
                 + ap * bands["meso"] * 0.30 * meso_s
                 + ap * bands["micro"] * 0.12 * micro_s
                 + ap * grammar.detail_strength * grain_s)
    albedo = base * value_mod[..., None]
    height = (bands["meso"] * meso_s + bands["micro"] * 0.4 * micro_s
              + grammar.detail_strength * 0.3 * grain_s)

    # Crisp cracks / panel seams (hard-thresholded F2-F1 ridges).
    if grammar.edges:
        e = ps.worley_edges((h, w), grammar.edges.get("cells", 16),
                            ps.stream_seed(seed, "edges"), label="edges")
        crack = (e >= grammar.edges.get("thr", 0.72)).astype(np.float32)
        st = grammar.edges.get("strength", 0.5)
        albedo = albedo * (1.0 - st * crack)[..., None]
        height = height - crack * 0.6

    # Crisp directional scratches (metal/plastic edge wear).
    if grammar.scratches:
        sc = ps.scratches((h, w), ps.stream_seed(seed, "scratch"),
                          axis=grammar.scratches.get("axis", "x"),
                          density=grammar.scratches.get("density", 0.05),
                          length_cells=grammar.scratches.get("length_cells", 3))
        st = grammar.scratches.get("strength", 0.4)
        col = ps.hex_to_rgb(grammar.scratches.get("color",
                                                  grammar.undercoat or "#c8c8c8"))
        m = (st * sc)[..., None]
        albedo = albedo * (1.0 - m) + col * m
        height = height + sc * 0.15

    # Flowing veins (marble / figured stone) — one or more coloured vein
    # networks. ``veins`` may be a single spec (one network) or a list of specs
    # (multi-scale: broad structural veins + fine hairline threading). Pass 0
    # keeps the "veins" stream label so single-network grammars stay
    # byte-identical; later passes draw independent streams.
    if grammar.veins:
        passes = grammar.veins if isinstance(grammar.veins, list) else [grammar.veins]
        for i, vp in enumerate(passes):
            label = "veins" if i == 0 else f"veins:{i}"
            vn = ps.veins((h, w), ps.stream_seed(seed, label),
                          base_cells=vp.get("cells", 4),
                          octaves=vp.get("octaves", 4),
                          sharpness=vp.get("sharpness", 3.0))
            st = vp.get("strength", 0.5)
            col = ps.hex_to_rgb(vp.get("color", "#6a635a"))
            m = (st * vn)[..., None]
            albedo = albedo * (1.0 - m) + col * m
            height = height - vn * 0.1

    # Masonry bond — per-unit tone variation + mortar/grout lines (brick/tile).
    if grammar.masonry:
        mm = grammar.masonry
        mort, unit = ps.masonry((h, w), mm.get("rows", 8), mm.get("cols", 4),
                                ps.stream_seed(seed, "masonry"),
                                offset=mm.get("offset", 0.5),
                                mortar=mm.get("mortar", 0.05))
        var = mm.get("brick_variation", 0.18)
        albedo = albedo * (1.0 + var * (unit - 0.5))[..., None]
        mcol = ps.hex_to_rgb(mm.get("mortar_color", "#9a958c"))
        m = (mort * mm.get("mortar_strength", 1.0))[..., None]
        albedo = albedo * (1.0 - m) + mcol * m
        height = height - mort * 0.5

    # Aggregate — filled irregular Voronoi cells, each poured a palette colour,
    # with a mortar/matrix line between (cobblestone, flagstone, terrazzo chips,
    # pebble/gravel, crazy-paving). ``colors`` is the per-cell palette (defaults
    # to base_colors); ``fill`` how strongly the chip colour replaces the base;
    # ``variation`` a per-cell tone jitter; ``gap``/``gap_color``/``gap_strength``
    # the matrix line.
    if grammar.aggregate:
        ag = grammar.aggregate
        gapm, cid = ps.voronoi_cells((h, w), ag.get("cells", 10),
                                     ps.stream_seed(seed, "aggregate"),
                                     gap=ag.get("gap", 0.04))
        chip_cols = [ps.hex_to_rgb(c) for c in (ag.get("colors") or grammar.base_colors)]
        if chip_cols:
            sel = np.clip(cid * len(chip_cols), 0, len(chip_cols) - 1e-6).astype(int)
            chip = np.stack(chip_cols, 0)[sel]
            fill = ag.get("fill", 1.0)
            albedo = albedo * (1.0 - fill) + chip * fill
        var = ag.get("variation", 0.0)
        if var:
            albedo = albedo * (1.0 + var * (cid - 0.5))[..., None]
        mcol = ps.hex_to_rgb(ag.get("gap_color", "#3a3a3a"))
        gm = (gapm * ag.get("gap_strength", 1.0))[..., None]
        albedo = albedo * (1.0 - gm) + mcol * gm
        height = height - gapm * 0.5

    # Horizontal form-board seams (concrete formwork lines) — subtle dark bands.
    if grammar.form_lines:
        fl = ps.stripes((h, w), grammar.form_lines.get("count", 6),
                        ps.stream_seed(seed, "form"), axis="y",
                        seam=grammar.form_lines.get("seam", 0.5),
                        jitter=grammar.form_lines.get("jitter", 0.05))
        # stripes() is bright bands with dark seams; pull out the seam darkening.
        dark = np.clip(0.5 - fl, 0.0, 0.5) * 2.0
        st = grammar.form_lines.get("strength", 0.25)
        albedo = albedo * (1.0 - st * dark)[..., None]
        height = height - dark * 0.3

    # Vertical grime/water streaks (interior-concrete stain character).
    if grammar.streaks:
        sv = ps.streaks((h, w), ps.stream_seed(seed, "streaks"),
                        density=grammar.streaks.get("density", 0.25),
                        decay=grammar.streaks.get("decay", 0.95))
        st = grammar.streaks.get("strength", 0.35)
        albedo = albedo * (1.0 - st * sv)[..., None]
        height = height - sv * 0.15

    # Crisp chips: hard-edged clustered damage exposing undercoat then cavity.
    if grammar.chips:
        damage = ps.worley_f1((h, w), grammar.chips.get("cells", 10),
                              ps.stream_seed(seed, "chips"), label="chips")
        thr = grammar.chips.get("amount", 0.2)
        chip_mask = (damage < thr).astype(np.float32)            # hard edge
        if grammar.undercoat:
            under = ps.hex_to_rgb(grammar.undercoat)
            albedo = albedo * (1 - chip_mask[..., None]) + under * chip_mask[..., None]
        if grammar.cavity:
            deep = (damage < thr * 0.4).astype(np.float32)
            cav = ps.hex_to_rgb(grammar.cavity)
            albedo = albedo * (1 - deep[..., None]) + cav * deep[..., None]
        height = height - chip_mask * 0.5
    else:
        chip_mask = None

    albedo = np.clip(albedo, 0.0, 1.0)
    if grammar.posterize:
        albedo = ps.posterize(albedo, grammar.posterize)   # hard value steps (Q2)

    out: dict[str, Any] = {"albedo": _to_u8(albedo)}

    if grammar.emit.get("roughness", True):
        r = grammar.roughness or {}
        rough = (r.get("base", 0.7) + r.get("variation", 0.2) * meso_s)
        if chip_mask is not None:
            rough = rough + chip_mask * 0.2                  # bare/worn is rougher
        rough = np.clip(rough, 0.0, 1.0)
        if grammar.posterize:
            rough = ps.posterize(rough, max(4, grammar.posterize // 2))  # stepped
        out["roughness"] = _to_u8(rough)

    if grammar.emit.get("normal", False):
        hf = height - height.min()
        hf = hf / max(hf.max(), 1e-6)
        nrm = maps.normal_from_height(hf.astype(np.float32),
                                      strength=grammar.height_strength * 3.0,
                                      wrap_x=True, wrap_y=True)   # tileable normals
        out["normal"] = _to_u8(np.clip(nrm, 0.0, 1.0))

    # Emissive (backlit glow): stained-glass cells and lit panels. By default
    # the coloured albedo itself glows (so dark lead cames / grout stay dark);
    # ``from: "tint"`` glows a flat colour instead. ``gamma`` punches the
    # saturated cells; ``strength`` scales the whole map.
    if grammar.emissive:
        em = grammar.emissive
        if em.get("from") == "tint":
            glow = np.broadcast_to(ps.hex_to_rgb(em.get("color", "#ffffff")),
                                   (h, w, 3)).astype(np.float32).copy()
        else:
            glow = np.clip(albedo, 0.0, 1.0).astype(np.float32)
        g = em.get("gamma")
        if g:
            glow = np.clip(glow, 0.0, 1.0) ** float(g)
        out["emissive"] = _to_u8(np.clip(glow * em.get("strength", 1.0), 0.0, 1.0))

    return out


# --------------------------------------------------------------------------- #
# Pack writer — the Zoo-consumable contract
# --------------------------------------------------------------------------- #

def build_material_pack(grammar, pack_dir: str, *, asset_id: str | None = None,
                        size=512, seed: int = DEFAULT_SEED) -> dict:
    """Synthesize + write a Pixelcoat pack into ``pack_dir``. Returns the manifest.

    Writes ``<pack_dir>/{<asset_id>_albedo.png, ..., <asset_id>.pack.json}``.
    The caller owns the directory name — for Zoo's tiling library, name it
    ``<kind>_<theme>`` (e.g. ``metal_delco``) so ``skins.find_pack`` resolves it;
    the map filenames inside are independent of that name.
    """
    if isinstance(grammar, str):
        grammar = MaterialGrammar.load(grammar)
    elif isinstance(grammar, dict):
        grammar = MaterialGrammar.from_dict(grammar)
    asset_id = asset_id or grammar.id

    arrays = synthesize(grammar, size=size, seed=seed)
    os.makedirs(pack_dir, exist_ok=True)

    map_files: dict[str, str] = {}
    for key, arr in arrays.items():
        fname = f"{asset_id}_{key}.png"
        _write_png(arr, os.path.join(pack_dir, fname))
        map_files[key] = fname

    manifest = {
        "schema": "pixelcoat-pack/2",
        "tool_version": __version__,
        "asset_id": asset_id,
        "processing_mode": "procedural",
        "source_kind": "procedural",
        "material_kind": grammar.kind,
        "material_profile": grammar.id,
        "maps": map_files,
        "tileable": ["x", "y"],
        "meters_per_tile": float(grammar.meters_per_tile),
        "seed": int(seed),
        "import_hints": {
            "color_space": {k: ("srgb" if k in ("albedo", "emissive") else "linear")
                            for k in map_files},
            "normal_format": "opengl",
            "generate_mipmaps": True,
            "interpolation": "nearest",
        },
    }
    # See-through glass: the pack asks the consumer (Zoo -> Godot) for a
    # transparent material. opacity 1.0 = opaque (facade glass you can't see
    # into); < 1.0 = see-through window glass. ior is advisory for refraction.
    if grammar.transparency:
        t = grammar.transparency
        manifest["import_hints"]["transparency"] = {
            "opacity": float(t.get("opacity", 0.6)),
            "ior": float(t.get("ior", 1.45)),
            "alpha_mode": t.get("alpha_mode", "blend"),
        }
    with open(os.path.join(pack_dir, f"{asset_id}.pack.json"), "w",
              encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    return manifest


def build_theme_library(profile, grammars_dir: str, out_dir: str, *,
                        size=512, seed: int = DEFAULT_SEED) -> dict:
    """Build a Zoo ``--skins`` library from a *theme profile* — the reproducible
    curation the Level Factory orchestrator needs.

    A theme is a declarative map of one grammar per material kind
    (``profiles/themes/<theme>.json``: ``{"theme": ..., "materials": {kind:
    grammar_id}}``). This writes one ``<kind>_<theme>/`` pack per curated
    material into ``out_dir`` — exactly the layout ``core.skins.find_pack``
    resolves for ``(kind, theme)``. So a building's art pass just needs
    ``build_theme_library(<its theme>)`` then Zoo ``--skins out_dir --theme
    <theme>``; the vocabulary a building wears is entirely the theme profile.

    Raises if a curated grammar's ``kind`` doesn't match the slot it's mapped to
    (a theme can't put a brick grammar in the ``glass`` slot).
    """
    if isinstance(profile, str):
        with open(profile, encoding="utf-8") as f:
            profile = json.load(f)
    theme = profile["theme"]
    packs: dict[str, str] = {}
    for kind, gram_id in profile.get("materials", {}).items():
        g = MaterialGrammar.load(os.path.join(grammars_dir, f"{gram_id}.json"))
        if g.kind != kind:
            raise ValueError(
                f"theme '{theme}': grammar '{gram_id}' is kind '{g.kind}', "
                f"but the profile maps it to the '{kind}' slot")
        pack_dir = os.path.join(out_dir, f"{kind}_{theme}")
        build_material_pack(g, pack_dir, size=size, seed=seed)
        packs[kind] = f"{kind}_{theme}"
    return {"theme": theme, "out_dir": os.path.abspath(out_dir),
            "packs": packs, "kind_count": len(packs)}


def _to_u8(arr: np.ndarray) -> np.ndarray:
    return np.rint(np.clip(arr, 0.0, 1.0) * 255.0).astype(np.uint8)


def _write_png(u8: np.ndarray, path: str) -> None:
    """Deterministic PNG write for uint8 L / RGB / RGBA arrays."""
    if u8.ndim == 2:
        mode = "L"
    elif u8.shape[-1] == 3:
        mode = "RGB"
    elif u8.shape[-1] == 4:
        mode = "RGBA"
    else:
        raise ValueError(f"cannot write array of shape {u8.shape}")
    Image.fromarray(u8, mode).save(path, optimize=False)
