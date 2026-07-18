# Changelog

## [0.10.0] - DELCO signage packs: the tool finally fed for its purpose

### Added
- `recipes/delco_signage/` — six sign recipes (deli, pawn, auto, open-24,
  cold beer, checks cashed): 128x64 edge-aware crush, 12-color oklab
  palettes, bayer dither, `export.type: sign`, EMISSIVE THRESHOLD maps so
  the letterforms are what glows. Sources ship at `recipes/sources/`
  (procedurally generated period sign faces; `tools/gen_sign_sources.py`
  included for variants — a recipe plus the source bytes IS the asset).
- `tools/make_delco_signage.ps1` — builds all six packs into
  `_runs\skins\delco_signage\signs_delco/<asset_id>/`, the exact layout
  Zoo v0.31's sign-pack resolver consumes via `--skins`.
- All six packs validated end-to-end in-container: built through the real
  CLI, loaded by Zoo's real `skins.load_pack` (albedo+emissive+roughness).


All notable changes to Pixelcoat. Format follows
[Keep a Changelog](https://keepachangelog.com/); versioning follows
[SemVer](https://semver.org/).

## [0.9.0] - 2026-07-13

### Added
- **Folder batch processing** (TDD 6.2): `core/batch.py` +
  `pixelcoat batch <folder>`. This completes the CLI-era TDD backlog —
  what remains of the v0.1 TDD is the desktop app epic. No recipe or
  pipeline changes (schema stays 0.7); additive module + CLI.
- One style template for the whole folder (`--recipe style.json` —
  ordinary recipe JSON; asset_id and source.path are injected per file,
  so a saved recipe works as-is and a template may omit them), or
  presets mapped by filename pattern (`--map 'poster_*=poster.json'`,
  fnmatch, first match wins, template as fallback) — 6.2.2 in full.
- Failure isolation (6.2.4): a bad file lands in the batch report's
  failures list and the batch continues; exit code is nonzero only when
  NOTHING processed. Files process in sorted order; two runs of the
  same folder produce byte-identical outputs.
- Asset ids from file stems; collisions under `--recursive`
  disambiguate deterministically by prefixing parent folder names
  (sub/wall.png -> sub_wall).
- `--atlas NAME` combines the compatible outputs after the batch
  (6.2.6); atlas errors (e.g. mixed modes) are recorded in the report
  instead of failing the batch. `batch_report.json` written at the
  output root with entries, failures, per-file durations, and the
  atlas report.
- Generation 7 templates work unchanged — a folder of photos becomes a
  folder of gen7 material packs in one command.
- 7 new tests (87 total): failure isolation, collision disambiguation,
  template + pattern-map sizing, byte-determinism across runs,
  batch + atlas, gen7 template, batch CLI.

## [0.8.0] - 2026-07-13

### Added
- **Atlas and trim-sheet packing** (TDD 7.15, output 8.3):
  `core/atlas.py` + `pixelcoat atlas <packs-or-dirs> --name <atlas>`.
  No recipe or pipeline changes — recipes stay schema 0.7 and every
  existing output is untouched by construction (additive module + CLI;
  byte-compatibility tests stay green).
- One atlas PER MAP: every entry's albedo/normal/roughness land at the
  same rect, so a single UV rect drives every channel. Maps missing
  from some entries are filled with that map's neutral value (flat
  normal 128/128/255, mid roughness, black emissive) instead of
  rejecting the input; mixed processing modes are rejected with a
  grouping hint.
- Deterministic shelf packing: entries sort tallest-first with asset-id
  tiebreak; same inputs produce byte-identical atlases. 90-degree
  rotation on by default, taken only when it lays an entry wider than
  tall, recorded per entry (`--no-rotate` to disable). `--pow2` rounds
  dimensions up; `--gutter N` spacing with HALF-gutter edge extrusion
  per entry so two entries sharing a gutter strip each own their side
  (mipmap-safe RGB); alpha stays zero throughout gutters when any entry
  carries alpha (decal atlases sample clean at every filter level —
  same rule as the single-decal exporter).
- Manifest `<atlas>_atlas.json` (schema pixelcoat-atlas/1) per the TDD
  example: rect_px, uv, rotated, pivot, alpha_mode, source_pack per
  entry + atlas maps/size/gutter. `<atlas>_preview.png` with outlined
  entry rects (8.3). Build report includes occupancy.
- CLI accepts .pack.json paths or directories (recursive scan).
- 7 new tests (80 total): end to end (manifest, no overlaps, rects crop
  back to exact source pixels with rotation honored, uv consistency),
  byte-determinism across runs, rotation + toggle, pow2 + transparent
  gutters, neutral fill for missing maps, mixed-mode rejection,
  atlas CLI.

## [0.7.0] - 2026-07-13

### Added
- **Alpha + decal generation** (TDD 7.11), the posters-and-signs
  release. Schema 0.7; alpha.source defaults to "none" which bypasses
  everything; both paths verified byte-identical against baselines.
- **Alpha sources** (`core/alpha.py`), run at SOURCE resolution so
  feathering happens in source space and the downsample turns feathered
  edges into clean coverage: existing source alpha; color-key removal
  (hex key + tolerance, soft shoulder to 1.5x tol); luminance threshold
  (+ invert); authored grayscale mask; background flood select seeded
  from the four corners (PIL C floodfill; enclosed holes that match the
  background color are correctly kept — they are not corner-connected).
  Edge-guided subject extraction and polygon selection deliberately
  absent per the TDD MVP guidance (manual masks over unreliable
  recognition; polygons are GUI-era).
- **Decal controls** at working resolution, after quantize + dither:
  alpha cutoff; pixel-hard binary alpha (default on); dilation padding;
  transparent-RGB cleanup (iterative defringe — transparent pixels take
  extruded opaque-neighbor colors, so the 7.11 acceptance criterion
  "no color fringes" is a tested property, and border extrusion falls
  out of the same fill); straight or premultiplied alpha.
- **Decal export** (`export.type: "decal"`, CLI `--decal`): file named
  `<asset>_decal.png` per TDD 8.2 with the pack key remaining "albedo"
  (consumers read keys, not filenames); padding extrudes RGB for
  mipmap safety but zero-pads ALPHA — decal padding stays transparent.
  Packs gain an additive `export_type` field.
- CLI: `--alpha {source,color_key,luminance,mask,flood}`, `--alpha-key`,
  `--alpha-tolerance`, `--alpha-threshold`, `--alpha-invert`,
  `--alpha-mask`, `--alpha-feather`, `--alpha-dilate`, `--decal`.
- Build-report `final_color_count` now counts OPAQUE pixels only (the
  defringe fill under transparent pixels is deliberately off-palette
  and invisible).
- 10 new tests (73 total): color-key end to end + TDD 8.2 naming +
  transparent padding, no-fringe acceptance criterion, pixel-hard vs
  soft alpha, dilation growth, luminance + mask sources, flood keeping
  enclosed background-colored holes, premultiplied export, decal
  requires an alpha source, v0.7 defaults byte-compatibility, decal CLI.

## [0.6.0] - 2026-07-13

### Added
- **Pixel-path simplification slice** (TDD 7.4 + 7.13). Schema 0.6;
  every new field defaults off; both processing paths verified
  byte-identical against their baselines (pixel vs v0.2, gen7 vs v0.5).
- **Edge-aware downsampling**: `pixel.downsample_method: "edge_aware"`
  (+ `pixel.edge_preserve` 0..1, CLI `--downsample edge_aware
  --edge-preserve`). Per output cell, source pixels are weighted by
  similarity to the cell's MEDIAN color, so boundary cells resolve to
  their majority side instead of smearing both sides into a mud tone the
  palette never contained. edge_preserve 0 approximates box; 1 commits
  hard. Deterministic, pure NumPy (4x lanczos supersample + weighted
  cell collapse).
- **Small-island removal**: `simplification.island_removal` (CLI
  `--island-removal N`) dissolves connected same-palette regions of
  <= N pixels into their most common neighbor after dithering.
  8-connectivity ON PURPOSE: ordered-dither checkerboards chain
  diagonally into large components and survive; genuinely isolated
  specks go (fixture: 117 of 9216 pixels touched on a bayer build vs
  1608 orphans under 4-connectivity, which would have eaten the dither).
- **Protected detail mask**: `simplification.protected_mask` (grayscale
  path, >50% = protected; CLI `--protected-mask`). Protected regions
  keep source detail through noise reduction, value banding, and island
  removal — lettering, logos, window frames, cracks (TDD 7.4).
- **Mask-driven emissive**: `maps.emissive_mode: "mask"` +
  `maps.emissive_mask_path` — emissive cut directly from an authored
  mask, pixel-aligned with albedo (TDD 7.13; signage/neon feeding
  engine-side emission).
- 6 new tests (63 total): edge-aware boundary commitment + box
  approximation at strength 0, island removal end to end + protected
  exemption, protected mask preserving detail banding would erase,
  emissive mask mode + validation, v0.6 defaults byte-compatibility
  round trip.

## [0.5.0] - 2026-07-13

### Added
- **Generation 7 Slice 5** — pack-metadata-driven delivery. This closes
  the Generation 7 epic (docs/ROADMAP_generation_7.md, Slices 1-5).
  Schema 0.5; earlier recipes load unchanged; both processing paths
  verified byte-identical with new features off (pixel vs v0.2 baseline,
  gen7 vs v0.4 baseline).
- **Godot 4.7 importer**
  (`integrations/godot/addons/pixelcoat_importer/`): editor plugin with
  a Tools menu action that imports a `.pack.json` (pack/1 or pack/2) —
  fixes each texture's `.import` from import_hints (normal maps enabled,
  green flipped for directx packs, `roughness/src_normal` mip filtering,
  mipmap generation), reimports, then writes `<asset>_material.tres`
  StandardMaterial3D wiring albedo / normal / roughness (R, drops in as
  authored `1 - gloss`) / metallic / surface_occlusion (AO slot) and the
  detail slots: pack/2 tiles ride UV2 with `uv2_scale =
  repeats_per_meter x meters_per_tile`; packs without tiles wire the
  full-res micro normal on UV1. Wet maps produce a second
  `<asset>_material_wet.tres`. `pack_importer.gd` is pure logic,
  callable headless. Parallax off by default; specular map noted as
  ShaderMaterial territory (no per-pixel StandardMaterial3D slot).
- **Blender 4.x importer** (`integrations/blender/pixelcoat_import.py`):
  File > Import add-on building the matching Principled BSDF materials —
  albedo sRGB, all data maps Non-Color, AO multiplied into base color,
  normals through a Normal Map node with directx green flip, detail
  tiles via Mapping-node repetition blended through the detail mask,
  detail normals mixed by mask (documented linear approximation), wet
  material variant honoring `wet_detail_strength_scale`.
- **Variation exports** (SS17): `generation_7.variations` — any of
  darker / lighter / dirtier / damaged. One recipe, identical UV
  boundaries; dirtier and damaged re-run the weathering composite with
  amplified grime/wear masks so variants stay preset-consistent
  (painted metal "damaged" brightens toward bare steel), and export a
  shifted roughness alongside. Pack gains a `variants` list.
- `integrations/README.md` — install, usage, and the Godot/Blender
  mapping notes.
- 6 new tests (57 total): variation validation / exports / off-is-
  byte-identical / recipe round trip, Godot addon file sanity
  (metadata-driven, required import params present), Blender add-on
  AST parse + map coverage.

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
