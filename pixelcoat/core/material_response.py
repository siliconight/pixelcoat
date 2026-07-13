"""Material response (Gen7 roadmap §11) — the legacy authoring model.

Generation 7 environments were authored specular/gloss; modern Godot and
Blender want roughness. Pixelcoat authors in specular/gloss and derives
roughness as exactly ``1 - gloss`` from the same float array, so the pair
always satisfies the acceptance tolerance (one 8-bit value) by
construction.

Presets carry the per-material behavior the roadmap requires: how much
luminance means height, how strong each normal band is, how wear, grime,
and wetness respond. Brightness is NOT assumed to mean physical height —
each preset weights the bands itself (§8 material-aware rules).

Metallic is only ever produced by a preset RULE (painted metal exposes
steel where wear cuts through), an explicit value, or an artist mask —
never guessed from luminance (§11).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class MaterialPreset:
    name: str
    # Response authoring.
    specular_level: float          # base specular reflectance 0..1
    gloss: float                   # base gloss 0..1 (roughness = 1 - gloss)
    roughness_variation: float     # micro/cavity-driven spread
    metallic_rule: str             # "none" | "wear_exposed"
    # Height weighting (§8): luminance-vs-structure contribution.
    macro_weight: float            # broad forms contribution
    micro_weight: float            # fine structure contribution
    suppress_macro_gradients: bool  # concrete: kill broad lighting slopes
    # Normal band strengths (multiplied by recipe strengths).
    base_normal: float
    detail_normal: float
    cavity_gloss_influence: float  # crevices go duller by this much
    # Weathering behavior (§12, §13).
    undercoat: tuple[float, float, float]  # linear RGB exposed by wear
    wear_gloss_shift: float        # + = exposed area smoother (bare metal)
    wear_desaturate: float
    grime_color: tuple[float, float, float]  # linear RGB grime tint
    grime_roughen: float
    # Wetness response (§15).
    wet_darken: float
    wet_gloss_boost: float
    # Default color treatment.
    saturation_scale: float


PRESETS: dict[str, MaterialPreset] = {
    "concrete": MaterialPreset(
        name="concrete", specular_level=0.35, gloss=0.22,
        roughness_variation=0.14, metallic_rule="none",
        macro_weight=0.35, micro_weight=0.95,
        suppress_macro_gradients=True,
        base_normal=0.8, detail_normal=1.1, cavity_gloss_influence=0.30,
        undercoat=(0.62, 0.60, 0.56), wear_gloss_shift=-0.05,
        wear_desaturate=0.5,
        grime_color=(0.06, 0.055, 0.05), grime_roughen=0.20,
        wet_darken=0.45, wet_gloss_boost=0.45, saturation_scale=0.85),
    "brick": MaterialPreset(
        name="brick", specular_level=0.30, gloss=0.18,
        roughness_variation=0.12, metallic_rule="none",
        macro_weight=1.0, micro_weight=0.60,
        suppress_macro_gradients=False,
        base_normal=1.2, detail_normal=0.8, cavity_gloss_influence=0.35,
        undercoat=(0.55, 0.35, 0.26), wear_gloss_shift=-0.03,
        wear_desaturate=0.35,
        grime_color=(0.05, 0.045, 0.04), grime_roughen=0.22,
        wet_darken=0.40, wet_gloss_boost=0.40, saturation_scale=0.95),
    "wood": MaterialPreset(
        name="wood", specular_level=0.40, gloss=0.42,
        roughness_variation=0.18, metallic_rule="none",
        macro_weight=0.65, micro_weight=0.75,
        suppress_macro_gradients=False,
        base_normal=0.9, detail_normal=1.0, cavity_gloss_influence=0.25,
        undercoat=(0.60, 0.47, 0.30), wear_gloss_shift=-0.10,
        wear_desaturate=0.45,
        grime_color=(0.07, 0.055, 0.04), grime_roughen=0.18,
        wet_darken=0.50, wet_gloss_boost=0.35, saturation_scale=1.0),
    "painted_metal": MaterialPreset(
        name="painted_metal", specular_level=0.55, gloss=0.58,
        roughness_variation=0.20, metallic_rule="wear_exposed",
        macro_weight=0.15, micro_weight=0.45,
        suppress_macro_gradients=True,
        base_normal=0.5, detail_normal=0.7, cavity_gloss_influence=0.20,
        undercoat=(0.35, 0.36, 0.38), wear_gloss_shift=+0.22,
        wear_desaturate=0.7,
        grime_color=(0.05, 0.05, 0.05), grime_roughen=0.25,
        wet_darken=0.30, wet_gloss_boost=0.30, saturation_scale=0.90),
}

PRESET_NAMES = tuple(sorted(PRESETS))


def gloss_map(preset: MaterialPreset, micro_detail: np.ndarray,
              cavity_recess: np.ndarray, base_gloss: float,
              variation: float) -> np.ndarray:
    """(H, W) gloss 0..1: base +/- micro structure spread, dulled inside
    cavities (dust and paint sit in crevices)."""
    g = base_gloss + variation * np.clip(micro_detail * 4.0, -0.5, 0.5)
    g = g - cavity_recess * preset.cavity_gloss_influence
    return np.clip(g, 0.0, 1.0).astype(np.float32)


def roughness_from_gloss(gloss: np.ndarray) -> np.ndarray:
    """Exactly 1 - gloss, same float array — the §11 relationship."""
    return (1.0 - gloss).astype(np.float32)


def specular_map(preset: MaterialPreset, level: float,
                 cavity_recess: np.ndarray) -> np.ndarray:
    """(H, W) specular level, pulled down inside crevices."""
    s = level * (1.0 - 0.5 * cavity_recess)
    return np.clip(s, 0.0, 1.0).astype(np.float32)


def metallic_map(preset: MaterialPreset,
                 wear_mask: np.ndarray | None) -> np.ndarray | None:
    """Metallic only from a preset rule (never inferred from luminance).
    Returns None when the preset has no rule or the rule's input is
    missing."""
    if preset.metallic_rule == "wear_exposed" and wear_mask is not None:
        return np.clip(wear_mask * 1.5, 0.0, 1.0).astype(np.float32)
    return None
