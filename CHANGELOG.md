# Changelog

All notable changes to Pixelcoat. Format follows
[Keep a Changelog](https://keepachangelog.com/); versioning follows
[SemVer](https://semver.org/).

## [0.4.0] - 2026-07-13

### Added
- **Generation 7 Slice 4** (docs/ROADMAP_generation_7.md SS16-19):
  detail textures, mipmap preview, legacy block-compression preview.
  Schema 0.4; 0.1-0.3 recipes load unchanged; with the new features off,
  Gen7 canonical output is byte-identical to v0.3 (verified).
- **Detail textures** (`core/detail_texture.py`, SS16), off by default:
  - `generation_7.detail_texture` — source extracted | procedural |
    imported, tile size 32..512, repeats_per_meter, blend_mode, strength.
  - Extracted tiles crop the most ORDINARY high-frequency window (median
    micro-energy candidate — a unique landmark repeated 8x/meter reads
    instantly as tiling), keep only the window's own high-frequency band,
    are forced wrap-continuous on both axes, and re-centered so linear
    mean is exactly 0.5 (neutral under overlay/linear blending).
  - Procedural: seeded multi-octave value noise. Imported: authored tile,
    resized + wrap-repaired.
  - Full-res `detail_mask` fades grain where the base maps already carry
    strong unique high-frequency content; wraps with the surface.
  - Gen7-authentic split when enabled: base normal is built from COMBINED
    height (unique micro features merge into it), `detail_normal` becomes
    the small repeating tile, `detail_albedo` joins the pack, and
    `wet_detail_normal` is replaced by an importer hint
    (`wet_detail_strength_scale`). Pack gains a `detail` block
    (repeats_per_meter, blend_mode, strength, tile_size, uv guidance,
    distance fade) for Godot's secondary detail slots.
  - Tiles export unpadded (they are their own repeat unit) and are seam-
    validated as wrap-both regardless of surface tiling.
- **Previews** (`core/preview.py`, SS18-19), off by default, PREVIEW-ONLY
  (no preview step may alter a canonical PNG — regression-tested):
  - Mip chains: linear-space 2x box downsample, per-level normal
    renormalization, mip strips under `<asset>/previews/`, recommended
    mip at `preview_distance_meters` in the report, and a shimmer warning
    when high-frequency normal detail averages short at distance (with a
    pointer to Godot roughness filtering via the source normal).
  - Deterministic 4x4 block-compression previews: BC1-style color
    (RGB565 endpoints, 4-entry palette), BC5-style two-channel normals
    (independent 8-level ramps, Z reconstructed + renormalized),
    BC4-style single-channel masks, BC3-style color+alpha when alpha
    varies. Per-map suggested family + mean-abs-error in the report.
    Non-multiple-of-four dimensions are edge-padded for the preview only.
  - 3x3 repetition grid preview for tiled surfaces (SS17).
  - Unique-landmark warnings on tiled builds via robust median/MAD block
    statistics (a landmark cannot inflate its own yardstick).
- **CLI**: `pixelcoat preview-compression <pack.json> --profile legacy_bc
  [--output DIR]` — previews from an existing pack's canonical PNGs;
  reads only, writes only under the preview directory.
- Pack import_hints now always include `albedo_compression`,
  `normal_compression`, `mask_compression` suggestions.
- 9 new tests (51 total): slice-4 validation, detail tiles + mask +
  neutrality + p99 seams, detail-off byte-compatibility, previews-do-not-
  change-canonical-outputs, BC1 4-colors-per-block, BC5 unit-normal
  reconstruction, mip renormalization + shimmer flag, procedural/imported
  detail sources, landmark warning, preview-compression CLI.

### Deferred
- One-recipe variation exports (darker/dirtier/damaged) — all masks ship,
  importers can compose variants today; revisit with Slice 5.
- Material-preset detail library — procedural source covers it for now.

## [0.3.0] - 2026-07-13

### Added
- **Generation 7 surface skins** (docs/ROADMAP_generation_7.md, Slices
  1-3) — a second, fully separate deterministic processing graph for
  Xbox 360 / PS3-era layered materials. Selected by the new top-level
  recipe field `processing_mode` (`pixel` | `generation_7`); recipes
  without it are `pixel`. Schema 0.3; 0.1/0.2 recipes load unchanged.
- **Slice 1 — pipeline separation.** `pipeline.py` is now the mode
  dispatcher; the original graph moved verbatim to `pipeline_pixel.py`.
  Verified byte-identical pixel output across the move (albedo + all
  maps, dithered + tiled + emissive fixture). Pixel packs stay
  `pixelcoat-pack/1` and gain one additive `processing_mode` field.
- **Slice 2 — core Gen7 material stack** (`pipeline_generation_7.py`):
  - Working resolution 256..2048 with lanczos/bicubic/box resampling;
    build-report warnings for non-power-of-two, non-multiple-of-four
    (block compression), and output-exceeds-source-detail.
  - `core/color_space.py`: shared linear<->sRGB utilities. All Gen7 math
    runs linear; display albedo encodes to sRGB at export; data maps
    never receive gamma.
  - `core/lighting_flatten.py`: approximate lighting flattening (blurred
    illumination estimate divided out, shadow recovery, highlight
    compression, artist strength). Documented as an approximation, never
    as physical delighting.
  - `core/frequency.py`: wrap-aware separable cumsum box/smooth blur,
    macro/micro band separation with soft noise thresholding (compression
    noise never becomes false geometry), edge-preserving cleanup (median
    + blur blended by an edge mask; chroma smoothed harder than luma).
  - Base-color stylization: saturation, local contrast, optional MODERATE
    OKLab clustering 32..256 colors via new
    `quantization.extract_palette_large` (vectorized Lloyd + subsampled
    k-means++, matmul nearest mapping) — dithering does not exist in this
    mode. The pixel path's clusterer is untouched.
  - Material-aware macro + micro height (§8: presets weight the bands;
    concrete suppresses broad luminance gradients; brightness is never
    assumed to mean height), imported/combined height sources, base +
    detail normal (OpenGL Y+, `flip_green`), cavity + surface_occlusion
    (labeled honestly — not baked AO).
  - `core/material_response.py`: specular/gloss authoring with roughness
    derived as exactly `1 - gloss` (within one 8-bit value by
    construction); presets concrete / brick / wood / painted_metal;
    metallic only from a preset rule, explicit value, or mask.
- **Slice 3 — weathering** (`core/weathering.py`), all seeded and
  deterministic, every mask exported: edge wear from height gradients on
  raised transitions; cavity grime; directional streaks via the decay
  recurrence (down/up/left/right, seam-carrying on wrapped axes); rust
  bleed; wetness mask + wet_albedo / wet_roughness / wet_detail_normal
  variant (darkens, glosses, softens micro response only inside the
  mask; bottom bias auto-disabled on y-tiling surfaces, which have no
  "bottom").
- **Tile safety**: new `tiling.make_tileable_wrap` with a hard wrap-
  continuity guarantee for Gen7 (the v0.1 `make_tileable` soft assist is
  behavior-locked to the pixel path); every Gen7 stage is wrap-aware;
  per-map seam validation compares the seam step against the texture's
  own interior p99 statistics and reports to the build report.
- **`pixelcoat-pack/2`** for Gen7: additive over pack/1 + material
  profile/workflow and `import_hints` (per-map color space, normal
  format, mipmaps, roughness-source-normal for Godot roughness
  filtering).
- **CLI**: `process --mode generation_7 --profile <json>
  --meters-per-tile`; gen7 report line prints map count + warnings.
  `profiles/generation_7/{concrete,brick,wood,painted_metal}.json`
  tuned starting fragments.
- `generation_7.detail_texture` and `generation_7.preview` recipe
  sections exist but validate-and-refuse with a clear "arrives in v0.4"
  error (Slice 4: detail textures, mipmap + block-compression preview).
- 24 new tests (42 total): linear round trip, wrap-blur roll-invariance,
  band reconstruction, soft threshold, wrap-guarantee continuity,
  gloss+roughness == 255 +/- 1, cavity-on-recess, wear-favors-raised-
  edges, grime-favors-cavities, streak direction/decay/determinism/seed,
  metallic-preset-rule, wetness isolation, dispatch, pack/2 manifest +
  map alignment + clean tiled seams, byte-identical gen7 determinism,
  gen7 recipe round trip, four-preset differentiation, pixel pack
  additive field, 0.2-recipe compatibility, slice-4 rejection, imported
  height, resolution warnings, CLI gen7 + profile end to end.

### Performance (Linux dev box, roadmap targets)
- 1024x1024 full weathering + 96-color clustering: ~6.5s (target: <8s
  core maps). 2048x2048 full weathering: ~25s (target: <30s).

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
