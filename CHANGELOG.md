# Changelog

All notable changes to Pixelcoat. Format follows
[Keep a Changelog](https://keepachangelog.com/); versioning follows
[SemVer](https://semver.org/).

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
