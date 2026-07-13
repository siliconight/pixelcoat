"""Recipe: the reproducibility contract (TDD §9, §3.5).

A recipe is a JSON document containing every setting required to reproduce
an output. Source images are never modified; a recipe plus the source bytes
IS the asset. Hand-rolled dataclass validation for v0.1 — pydantic is TDD
§26 open decision territory and not worth a dependency until the schema
stabilizes.
"""

from __future__ import annotations

import dataclasses
import json
import os
from dataclasses import dataclass, field

from .version import RECIPE_SCHEMA_VERSION, __version__, DEFAULT_SEED

_DOWNSAMPLE = ("box", "nearest", "edge_aware")
_PALETTE_METHODS = ("oklab_kmeans", "fixed")
_DITHER = ("none", "bayer", "floyd_steinberg")
_EXPORT_TYPES = ("surface_texture", "decal", "sign")
_EMISSIVE_MODES = ("none", "indices", "threshold", "mask")
_ALPHA_SOURCES = ("none", "source", "color_key", "luminance", "mask", "flood")
_PROCESSING_MODES = ("pixel", "generation_7")
_G7_RESAMPLE = ("lanczos", "bicubic", "box")
_G7_HEIGHT_SOURCES = ("inferred", "imported", "combined")
_G7_WORKFLOWS = ("specular_gloss",)
_G7_STREAK_DIRECTIONS = ("down", "up", "left", "right")
_G7_VARIATIONS = ("darker", "lighter", "dirtier", "damaged")


@dataclass
class Transform:
    crop: list[int] | None = None                    # [x, y, w, h]
    perspective_quad: list[list[float]] | None = None  # TL,TR,BR,BL
    rotation_degrees: int = 0                        # 0/90/180/270


@dataclass
class Pixel:
    working_width: int = 128
    working_height: int = 128
    display_scale: int = 1                           # nearest-neighbor only
    downsample_method: str = "box"
    edge_preserve: float = 0.5                       # edge_aware only, 0..1


@dataclass
class Simplification:
    noise_reduction: float = 0.0                     # 0..1 median passes
    value_bands: int = 0                             # 0 = off
    island_removal: int = 0          # dissolve palette islands <= N px
    protected_mask: str | None = None                # grayscale mask path


@dataclass
class Palette:
    method: str = "oklab_kmeans"
    max_colors: int = 24
    locked_palette: str | None = None                # JSON hex list path
    seed: int = DEFAULT_SEED


@dataclass
class Dither:
    method: str = "none"
    strength: float = 0.5
    seed: int = DEFAULT_SEED


@dataclass
class Tiling:
    enabled: bool = False
    axes: str = "both"                               # x | y | both


@dataclass
class Alpha:
    """Alpha extraction + decal controls (TDD 7.11). Sources run at
    SOURCE resolution (feather in source space); controls run at working
    resolution after quantize + dither. "none" bypasses everything."""
    source: str = "none"    # none|source|color_key|luminance|mask|flood
    color_key: str = "#ff00ff"
    tolerance: float = 0.12                          # color_key
    luminance_threshold: float = 0.5
    invert: bool = False
    mask_path: str | None = None
    flood_tolerance: float = 0.10
    feather: float = 0.0                             # source-space px
    cutoff: float = 0.5
    pixel_hard: bool = True
    dilate: int = 0                                  # grow opaque, px
    rgb_cleanup: bool = True                         # defringe
    premultiplied: bool = False


@dataclass
class Maps:
    """Material map generation (TDD §7.13): the texture-and-depth stage.
    Normal + roughness ship by default so every pack reads as a material,
    not a flat print; height/emissive are opt-in."""
    normal: bool = True
    normal_strength: float = 2.0
    normal_flip_g: bool = False                      # DirectX-style consumers
    height: bool = False                             # emit the height field
    height_smooth: int = 1                           # 3x3 median passes
    roughness: bool = True
    roughness_base: float = 0.6
    roughness_variation: float = 0.25
    roughness_levels: int = 4                        # stepped PS1 response
    roughness_invert: bool = False
    emissive_mode: str = "none"          # none | indices | threshold | mask
    emissive_mask_path: str | None = None
    emissive_indices: list[int] = field(default_factory=list)
    emissive_threshold: float = 0.85



# ----------------------------------------------------------- generation 7
# Roadmap "Generation 7 Surface Skin": a separate layered-material graph.
# All settings live under this one section so pixel recipes never collide
# with it, and gen7 recipes ignore pixel-specific sections (pixel, palette,
# dither, simplification, maps) without erroring.

@dataclass
class Gen7Resolution:
    working_width: int = 1024
    working_height: int = 1024
    resample_method: str = "lanczos"


@dataclass
class Gen7Color:
    lighting_flatten_strength: float = 0.35
    illumination_radius: int = 48
    shadow_recovery: float = 0.15
    highlight_compression: float = 0.25
    saturation_scale: float = 1.0                 # 1.0 = preset default
    local_contrast: float = 0.15
    maximum_colors: int = 0                       # 0 = off; else 8..256


@dataclass
class Gen7Cleanup:
    strength: float = 0.35                        # edge-preserving smooth
    chroma_strength: float = 0.7                  # chroma smoothed harder


@dataclass
class Gen7Frequency:
    macro_radius: int = 12
    micro_radius: int = 2
    noise_threshold: float = 0.02
    detail_gain: float = 1.0


@dataclass
class Gen7Height:
    source: str = "inferred"                      # inferred|imported|combined
    import_path: str | None = None
    macro_strength: float = 0.8
    micro_strength: float = 0.35
    invert: bool = False


@dataclass
class Gen7Normal:
    base_strength: float = 1.0
    detail_strength: float = 0.45
    flip_green: bool = False


@dataclass
class Gen7Material:
    preset: str = "concrete"
    workflow: str = "specular_gloss"
    specular_level: float | None = None           # None -> preset value
    gloss: float | None = None
    roughness_variation: float | None = None
    emit_roughness: bool = True
    emit_metallic: bool = True                    # only fires on preset rule


@dataclass
class Gen7Weathering:
    edge_wear: float = 0.0
    cavity_grime: float = 0.0
    streaks: float = 0.0
    streak_direction: str = "down"
    streak_decay: float = 0.92
    rust_bleed: float = 0.0
    seed: int = DEFAULT_SEED


@dataclass
class Gen7Wetness:
    enabled: bool = False
    amount: float = 0.5
    cavity_bias: float = 0.65
    bottom_bias: float = 0.25


@dataclass
class Gen7DetailTexture:
    """Repeating close-range detail tile (roadmap SS16). When enabled, the
    pack's detail_normal becomes the small repeating tile, unique micro
    features merge into the base normal (built from combined height), and
    detail_albedo + detail_mask join the pack."""
    enabled: bool = False
    source: str = "extracted"        # extracted | procedural | imported
    import_path: str | None = None
    size: int = 128                  # tile edge, 32..512
    repeats_per_meter: float = 8.0
    blend_mode: str = "overlay"      # overlay | multiply | linear
    strength: float = 0.65


@dataclass
class Gen7Preview:
    """Preview generation (roadmap SS18-19). Never alters canonical maps;
    everything lands under <asset>/previews/."""
    generate_mipmaps: bool = False
    compression_preview: str = "none"             # none | legacy_bc
    preview_distance_meters: float = 5.0


@dataclass
class Generation7:
    resolution: Gen7Resolution = field(default_factory=Gen7Resolution)
    color: Gen7Color = field(default_factory=Gen7Color)
    cleanup: Gen7Cleanup = field(default_factory=Gen7Cleanup)
    frequency: Gen7Frequency = field(default_factory=Gen7Frequency)
    height: Gen7Height = field(default_factory=Gen7Height)
    normal: Gen7Normal = field(default_factory=Gen7Normal)
    material: Gen7Material = field(default_factory=Gen7Material)
    weathering: Gen7Weathering = field(default_factory=Gen7Weathering)
    wetness: Gen7Wetness = field(default_factory=Gen7Wetness)
    variations: list = field(default_factory=list)
    detail_texture: Gen7DetailTexture = field(
        default_factory=Gen7DetailTexture)
    preview: Gen7Preview = field(default_factory=Gen7Preview)

    _GROUPS = ("resolution", "color", "cleanup", "frequency", "height",
               "normal", "material", "weathering", "wetness",
               "detail_texture", "preview")

    def fill(self, raw: dict | None) -> None:
        if not raw:
            return
        for name in self._GROUPS:
            _fill(getattr(self, name), raw.get(name))
        if "variations" in raw:
            self.variations = list(raw["variations"])

    def to_dict(self) -> dict:
        d = {name: dataclasses.asdict(getattr(self, name))
             for name in self._GROUPS}
        if self.variations:
            d["variations"] = list(self.variations)
        return d


@dataclass
class Export:
    type: str = "surface_texture"
    format: str = "png"
    nearest_neighbor_upscale: bool = True
    padding: int = 0
    meters_per_tile: float = 1.0                     # physical repeat size


@dataclass
class Recipe:
    asset_id: str
    source_path: str
    schema_version: str = RECIPE_SCHEMA_VERSION
    tool_version: str = __version__
    processing_mode: str = "pixel"                # pixel | generation_7
    transform: Transform = field(default_factory=Transform)
    pixel: Pixel = field(default_factory=Pixel)
    simplification: Simplification = field(default_factory=Simplification)
    palette: Palette = field(default_factory=Palette)
    dither: Dither = field(default_factory=Dither)
    tiling: Tiling = field(default_factory=Tiling)
    maps: Maps = field(default_factory=Maps)
    alpha: Alpha = field(default_factory=Alpha)
    generation_7: Generation7 = field(default_factory=Generation7)
    export: Export = field(default_factory=Export)

    # ---------------------------------------------------------------- io
    @classmethod
    def from_dict(cls, raw: dict, where: str = "<recipe>") -> "Recipe":
        try:
            src = raw["source"]["path"]
            asset_id = raw["asset_id"]
        except KeyError as e:
            raise ValueError(f"{where}: missing required field {e}") from e
        r = cls(asset_id=asset_id, source_path=src)
        r.processing_mode = raw.get("processing_mode", "pixel")
        _fill(r.transform, raw.get("transform"))
        _fill(r.pixel, raw.get("pixel"))
        _fill(r.simplification, raw.get("simplification"))
        _fill(r.palette, raw.get("palette"))
        _fill(r.dither, raw.get("dither"))
        _fill(r.tiling, raw.get("tiling"))
        _fill(r.maps, raw.get("maps"))               # absent in 0.1 recipes
        _fill(r.alpha, raw.get("alpha"))             # absent pre-0.7
        r.generation_7.fill(raw.get("generation_7"))  # absent pre-0.3
        _fill(r.export, raw.get("export"))
        r.validate(where)
        return r

    @classmethod
    def load(cls, path: str) -> "Recipe":
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        r = cls.from_dict(raw, where=os.path.basename(path))
        # Source paths are relative to the recipe file (TDD §21).
        if not os.path.isabs(r.source_path):
            r.source_path = os.path.join(
                os.path.dirname(os.path.abspath(path)), r.source_path)
        return r

    def to_dict(self) -> dict:
        d = {
            "schema_version": self.schema_version,
            "tool_version": self.tool_version,
            "asset_id": self.asset_id,
            "processing_mode": self.processing_mode,
            "source": {"path": self.source_path},
            "transform": dataclasses.asdict(self.transform),
            "pixel": dataclasses.asdict(self.pixel),
            "simplification": dataclasses.asdict(self.simplification),
            "palette": dataclasses.asdict(self.palette),
            "dither": dataclasses.asdict(self.dither),
            "tiling": dataclasses.asdict(self.tiling),
            "maps": dataclasses.asdict(self.maps),
            "alpha": dataclasses.asdict(self.alpha),
            "export": dataclasses.asdict(self.export),
        }
        if self.processing_mode == "generation_7":
            d["generation_7"] = self.generation_7.to_dict()
        return d

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    # ---------------------------------------------------------- validate
    def validate(self, where: str = "<recipe>") -> None:
        def bad(msg: str):
            raise ValueError(f"{where}: {msg}")
        if self.pixel.working_width < 2 or self.pixel.working_height < 2:
            bad("working resolution must be at least 2x2")
        if self.pixel.downsample_method not in _DOWNSAMPLE:
            bad(f"downsample_method must be one of {_DOWNSAMPLE}")
        if self.pixel.display_scale < 1:
            bad("display_scale must be >= 1")
        if self.palette.method not in _PALETTE_METHODS:
            bad(f"palette method must be one of {_PALETTE_METHODS}")
        if self.palette.method == "fixed" and not self.palette.locked_palette:
            bad("palette method 'fixed' requires locked_palette")
        if not 2 <= self.palette.max_colors <= 256:
            bad("palette max_colors must be within 2..256")
        if self.dither.method not in _DITHER:
            bad(f"dither method must be one of {_DITHER}")
        if not 0.0 <= self.dither.strength <= 1.0:
            bad("dither strength must be within 0..1")
        if self.export.type not in _EXPORT_TYPES:
            bad(f"export type must be one of {_EXPORT_TYPES}")
        al = self.alpha
        if al.source not in _ALPHA_SOURCES:
            bad(f"alpha source must be one of {_ALPHA_SOURCES}")
        if al.source == "mask" and not al.mask_path:
            bad("alpha source 'mask' requires alpha mask_path")
        if al.source == "color_key":
            code = al.color_key.lstrip("#")
            if len(code) != 6 or any(c not in "0123456789abcdefABCDEF"
                                     for c in code):
                bad(f"alpha color_key '{al.color_key}' is not #rrggbb")
        for name, v in (("tolerance", al.tolerance),
                        ("flood_tolerance", al.flood_tolerance),
                        ("luminance_threshold", al.luminance_threshold),
                        ("cutoff", al.cutoff)):
            if not 0.0 <= v <= 1.0:
                bad(f"alpha {name} must be within 0..1")
        if al.feather < 0 or al.dilate < 0:
            bad("alpha feather and dilate must be >= 0")
        if self.export.type == "decal" and al.source == "none":
            bad("export type 'decal' requires an alpha source")
        if self.transform.rotation_degrees % 90 != 0:
            bad("rotation_degrees must be a multiple of 90 in v0.1")
        q = self.transform.perspective_quad
        if q is not None and (len(q) != 4 or any(len(c) != 2 for c in q)):
            bad("perspective_quad must be four [x, y] pairs (TL,TR,BR,BL)")
        if self.tiling.axes not in ("x", "y", "both"):
            bad("tiling axes must be x, y, or both")
        if not 0.0 <= self.maps.normal_strength <= 8.0:
            bad("maps normal_strength must be within 0..8")
        if not 0 <= self.maps.height_smooth <= 8:
            bad("maps height_smooth must be within 0..8")
        if not 0.0 <= self.maps.roughness_base <= 1.0:
            bad("maps roughness_base must be within 0..1")
        if not 0.0 <= self.maps.roughness_variation <= 1.0:
            bad("maps roughness_variation must be within 0..1")
        if not 2 <= self.maps.roughness_levels <= 32:
            bad("maps roughness_levels must be within 2..32")
        if self.maps.emissive_mode not in _EMISSIVE_MODES:
            bad(f"maps emissive_mode must be one of {_EMISSIVE_MODES}")
        if self.maps.emissive_mode == "indices" and not self.maps.emissive_indices:
            bad("maps emissive_mode 'indices' requires emissive_indices")
        if self.maps.emissive_mode == "mask" and not self.maps.emissive_mask_path:
            bad("maps emissive_mode 'mask' requires emissive_mask_path")
        if not 0.0 <= self.pixel.edge_preserve <= 1.0:
            bad("pixel edge_preserve must be within 0..1")
        if self.simplification.island_removal < 0:
            bad("simplification island_removal must be >= 0")
        if not 0.0 <= self.maps.emissive_threshold <= 1.0:
            bad("maps emissive_threshold must be within 0..1")
        if self.export.meters_per_tile <= 0.0:
            bad("export meters_per_tile must be > 0")
        if self.processing_mode not in _PROCESSING_MODES:
            bad(f"processing_mode must be one of {_PROCESSING_MODES}")
        if self.processing_mode == "generation_7":
            self._validate_generation_7(bad)

    def _validate_generation_7(self, bad) -> None:
        from .core.material_response import PRESET_NAMES
        g = self.generation_7
        if g.resolution.working_width < 16 or g.resolution.working_height < 16:
            bad("generation_7 working resolution must be at least 16x16")
        if g.resolution.resample_method not in _G7_RESAMPLE:
            bad(f"generation_7 resample_method must be one of {_G7_RESAMPLE}")
        for name, v in (("lighting_flatten_strength",
                         g.color.lighting_flatten_strength),
                        ("shadow_recovery", g.color.shadow_recovery),
                        ("highlight_compression",
                         g.color.highlight_compression),
                        ("local_contrast", g.color.local_contrast)):
            if not 0.0 <= v <= 1.0:
                bad(f"generation_7 color {name} must be within 0..1")
        if g.color.illumination_radius < 2:
            bad("generation_7 illumination_radius must be >= 2")
        if g.color.maximum_colors != 0 and not 8 <= g.color.maximum_colors <= 256:
            bad("generation_7 maximum_colors must be 0 (off) or 8..256")
        if not 0.0 <= g.cleanup.strength <= 1.0 \
                or not 0.0 <= g.cleanup.chroma_strength <= 1.0:
            bad("generation_7 cleanup strengths must be within 0..1")
        if g.frequency.macro_radius < 1 or g.frequency.micro_radius < 1:
            bad("generation_7 frequency radii must be >= 1")
        if g.frequency.micro_radius >= g.frequency.macro_radius:
            bad("generation_7 micro_radius must be smaller than macro_radius")
        if g.height.source not in _G7_HEIGHT_SOURCES:
            bad(f"generation_7 height source must be one of "
                f"{_G7_HEIGHT_SOURCES}")
        if g.height.source in ("imported", "combined") \
                and not g.height.import_path:
            bad(f"generation_7 height source '{g.height.source}' requires "
                f"import_path")
        if not 0.0 <= g.height.macro_strength <= 2.0 \
                or not 0.0 <= g.height.micro_strength <= 2.0:
            bad("generation_7 height strengths must be within 0..2")
        if not 0.0 <= g.normal.base_strength <= 8.0 \
                or not 0.0 <= g.normal.detail_strength <= 8.0:
            bad("generation_7 normal strengths must be within 0..8")
        if g.material.preset not in PRESET_NAMES:
            bad(f"generation_7 material preset must be one of {PRESET_NAMES}")
        if g.material.workflow not in _G7_WORKFLOWS:
            bad(f"generation_7 material workflow must be one of "
                f"{_G7_WORKFLOWS}")
        for name, v in (("specular_level", g.material.specular_level),
                        ("gloss", g.material.gloss),
                        ("roughness_variation",
                         g.material.roughness_variation)):
            if v is not None and not 0.0 <= v <= 1.0:
                bad(f"generation_7 material {name} must be within 0..1")
        w = g.weathering
        for name, v in (("edge_wear", w.edge_wear),
                        ("cavity_grime", w.cavity_grime),
                        ("streaks", w.streaks),
                        ("rust_bleed", w.rust_bleed)):
            if not 0.0 <= v <= 1.0:
                bad(f"generation_7 weathering {name} must be within 0..1")
        if w.streak_direction not in _G7_STREAK_DIRECTIONS:
            bad(f"generation_7 streak_direction must be one of "
                f"{_G7_STREAK_DIRECTIONS}")
        if not 0.0 <= w.streak_decay < 1.0:
            bad("generation_7 streak_decay must be within 0..1 (exclusive)")
        if not 0.0 <= g.wetness.amount <= 1.0:
            bad("generation_7 wetness amount must be within 0..1")
        dt = g.detail_texture
        if dt.enabled:
            if dt.source not in ("extracted", "procedural", "imported"):
                bad(f"detail_texture.source '{dt.source}' is not one of "
                    "extracted, procedural, imported")
            if dt.source == "imported" and not dt.import_path:
                bad("detail_texture.source 'imported' requires "
                    "detail_texture.import_path")
            if not 32 <= dt.size <= 512:
                bad(f"detail_texture.size {dt.size} outside 32..512")
            if dt.blend_mode not in ("overlay", "multiply", "linear"):
                bad(f"detail_texture.blend_mode '{dt.blend_mode}' is not "
                    "one of overlay, multiply, linear")
            if not 0.5 <= dt.repeats_per_meter <= 64.0:
                bad(f"detail_texture.repeats_per_meter "
                    f"{dt.repeats_per_meter} outside 0.5..64")
            if not 0.0 <= dt.strength <= 1.0:
                bad(f"detail_texture.strength {dt.strength} outside 0..1")
        for v in g.variations:
            if v not in _G7_VARIATIONS:
                bad(f"generation_7 variation '{v}' is not one of "
                    f"{_G7_VARIATIONS}")
        pv = g.preview
        if pv.compression_preview not in ("none", "legacy_bc"):
            bad(f"preview.compression_preview '{pv.compression_preview}' "
                "is not one of none, legacy_bc")
        if not 0.5 <= pv.preview_distance_meters <= 100.0:
            bad(f"preview.preview_distance_meters "
                f"{pv.preview_distance_meters} outside 0.5..100")


def _fill(target, raw: dict | None) -> None:
    if not raw:
        return
    for f in dataclasses.fields(target):
        if f.name in raw:
            setattr(target, f.name, raw[f.name])
