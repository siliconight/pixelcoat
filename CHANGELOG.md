# Changelog

All notable changes to Pixelcoat. Format follows
[Keep a Changelog](https://keepachangelog.com/); versioning follows
[SemVer](https://semver.org/).

## [0.2.0] - 2026-07-10

### Added
- **Material maps** (TDD §7.13) — the texture-and-depth stage. New
  `core/maps.py` derives, from the post-dither albedo at working
  resolution (so everything stays pixel-aligned through upscale + pad):
  - **height** — luminance field, median-smoothed (`height_smooth`) so
    dither speckle doesn't read as bumps; opt-in export.
  - **normal** — central-difference tangent-space map, OpenGL Y+ (the
    Godot 4 / Blender convention; `normal_flip_g` for DirectX). Gradients
    wrap on tiled axes, so the normal map is seamless exactly where the
    albedo is. On by default, `normal_strength` 0..8.
  - **roughness** — recesses rougher / raised smoother (`roughness_invert`
    flips), quantized to `roughness_levels` steps for a chunky PS1-era
    specular response. On by default.
  - **emissive** — opt-in: `indices` mode (chosen palette entries glow —
    neon/signage workflow) or `threshold` (luma cutoff).
- **Pack manifest** `<asset_id>.pack.json` (`pixelcoat-pack/1`): the
  cross-tool contract — map filenames, `tileable` axes, `meters_per_tile`
  (new `export.meters_per_tile`, physical repeat size consumers use to set
  texture density), tool version, source sha256. Zoo v0.27.0 consumes this
  to skin compiled assets.
- Recipe `maps` section; schema_version 0.2. **0.1 recipes load unchanged**
  (maps defaults apply) — covered by test.
- 9 new tests (18 total): map/pack emission, albedo alignment, neutral
  flat-field normal, wrap continuity by roll-invariance, OpenGL green
  convention (+flip), roughness step count, emissive index selection,
  byte-identical map determinism, 0.1-recipe compatibility.

## [0.1.0] - 2026-07-10

### Added
- Repo scaffold per TDD v0.1 §10: `core/` (image_io, transforms,
  simplification, quantization, dithering, tiling, pipeline), `cli/`,
  recipe schema, tests, example fixed palette. TDD checked in at
  `docs/TDD_v0_1.md`.
- **Recipe system** (§9): dataclass schema + JSON round-trip + validation.
  `schema_version` 0.1, tool version and source sha256 recorded in every
  build report. Seed default 1999 (pipeline convention).
- **Working pipeline** Load -> crop/perspective rectify (2x supersampled) ->
  box/nearest downsample -> median noise reduction -> value banding (§7.6
  slice) -> seam assist (half-offset + blend, §12.5 steps 1-2) -> OKLab
  k-means or fixed-palette quantization (§12.2) -> dither -> nearest
  upscale -> border-extrusion padding -> albedo + recipe + build report.
- **Dithering** (§7.8 slice): none / bayer 4x4 / floyd_steinberg, all
  constrained to the active palette by construction.
- **CLI** (§14): `pixelcoat process | build | validate`, `--json` logs,
  overwrite protection, non-zero exit on failure.
- 9 tests covering schema, OKLab round-trip, palette limits,
  dither-in-palette property, pack layout, byte-identical determinism,
  perspective rectification, and the CLI end to end.

### Deliberately absent (TDD-ordered roadmap)
- Edge-aware downsampling, masks, alpha/decals, material maps, atlas
  packing, batch mode, GUI, Blender/Godot importers.
