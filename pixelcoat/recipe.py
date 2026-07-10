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

_DOWNSAMPLE = ("box", "nearest")            # "edge_aware" arrives post-v0.1
_PALETTE_METHODS = ("oklab_kmeans", "fixed")
_DITHER = ("none", "bayer", "floyd_steinberg")
_EXPORT_TYPES = ("surface_texture", "decal", "sign")
_EMISSIVE_MODES = ("none", "indices", "threshold")


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


@dataclass
class Simplification:
    noise_reduction: float = 0.0                     # 0..1 median passes
    value_bands: int = 0                             # 0 = off


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
    emissive_mode: str = "none"                      # none | indices | threshold
    emissive_indices: list[int] = field(default_factory=list)
    emissive_threshold: float = 0.85


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
    transform: Transform = field(default_factory=Transform)
    pixel: Pixel = field(default_factory=Pixel)
    simplification: Simplification = field(default_factory=Simplification)
    palette: Palette = field(default_factory=Palette)
    dither: Dither = field(default_factory=Dither)
    tiling: Tiling = field(default_factory=Tiling)
    maps: Maps = field(default_factory=Maps)
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
        _fill(r.transform, raw.get("transform"))
        _fill(r.pixel, raw.get("pixel"))
        _fill(r.simplification, raw.get("simplification"))
        _fill(r.palette, raw.get("palette"))
        _fill(r.dither, raw.get("dither"))
        _fill(r.tiling, raw.get("tiling"))
        _fill(r.maps, raw.get("maps"))               # absent in 0.1 recipes
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
        return {
            "schema_version": self.schema_version,
            "tool_version": self.tool_version,
            "asset_id": self.asset_id,
            "source": {"path": self.source_path},
            "transform": dataclasses.asdict(self.transform),
            "pixel": dataclasses.asdict(self.pixel),
            "simplification": dataclasses.asdict(self.simplification),
            "palette": dataclasses.asdict(self.palette),
            "dither": dataclasses.asdict(self.dither),
            "tiling": dataclasses.asdict(self.tiling),
            "maps": dataclasses.asdict(self.maps),
            "export": dataclasses.asdict(self.export),
        }

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
        if not 0.0 <= self.maps.emissive_threshold <= 1.0:
            bad("maps emissive_threshold must be within 0..1")
        if self.export.meters_per_tile <= 0.0:
            bad("export meters_per_tile must be > 0")


def _fill(target, raw: dict | None) -> None:
    if not raw:
        return
    for f in dataclasses.fields(target):
        if f.name in raw:
            setattr(target, f.name, raw[f.name])
