# Pixelcoat

*Controlled pixel-art surface treatments for 3D worlds.*

Pixelcoat converts ordinary images — photographs, references, logos, scans —
into stylized low-resolution artwork designed to live ON 3D environments:
projected facades, decals, signs, posters, repeating materials, trim sheets.
It is not a photo filter and its output is not standalone 2D art.

Deterministic, offline, batchable, art-directable. Same source bytes + same
recipe + same version = same output hash, always. Full design:
[docs/TDD_v0_1.md](docs/TDD_v0_1.md).

## Status: v0.8.x — two processing modes

`processing_mode` selects the graph; recipes without one are `pixel`.

**`pixel`** — the original low-res, palette-controlled, dithered treatment
(unchanged, byte-identical to v0.2 output):

```
Load -> Crop/Perspective -> Downsample -> Noise Reduce -> Value Group
     -> Tile Assist -> OKLab Palette Quantize -> Dither
     -> Material Maps (height -> normal / roughness / emissive)
     -> Upscale -> Pad -> Export (pack + recipe + build report)
```

**`generation_7`** — a separate layered-material graph for Xbox 360 / PS3
era surface skins (docs/ROADMAP_generation_7.md, Slices 1-3). Not a
higher-res pixel mode: no low-color palettes, no value banding, no
pixel-grid dither, no stepped PS1 roughness.

```
Load -> Transform -> Working Resolution (256..2048, lanczos)
     -> Linear Working Data -> Approximate Lighting Flattening
     -> Edge-Preserving Cleanup -> Frequency Separation (macro/micro)
     -> Base-Color Stylization (optional 32..256 OKLab clustering)
     -> Macro/Micro Height -> Base + Detail Normal
     -> Cavity + Surface Occlusion -> Specular/Gloss/Roughness
     -> Weathering (edge wear, cavity grime, streaks, rust, wetness)
     -> Tile Validation -> Export (pack/2 + recipe + build report)
```

Material presets: `concrete`, `brick`, `wood`, `painted_metal` — each
defines height weighting (brightness is never assumed to mean height),
normal band strengths, specular/gloss response, and how wear, grime, and
wetness behave. Roughness is derived as exactly `1 - gloss`. Metallic is
only ever produced by a preset rule (painted metal exposes steel where
wear cuts through) — never guessed from luminance. All weathering is
seeded and deterministic; every mask is exported so Zoo/Patina/importers
can drive their own variants. Lighting flattening is an approximation,
not physically accurate delighting.

Gen7 packs use `pixelcoat-pack/2` — additive over `pack/1` (maps /
tileable / meters_per_tile read the same way) plus `processing_mode`,
`material_profile`, and `import_hints` (per-map color space, normal
format, compression suggestions, roughness-source-normal). Pixel packs
stay `pack/1` and gain only an additive `processing_mode` field.

**Detail textures** (`generation_7.detail_texture`, off by default): a
small repeating detail albedo + detail normal tile for close-range
sharpness, extracted from the most ORDINARY window of the source's
high-frequency band (or procedural / imported), plus a full-res
detail_mask that fades the grain where the base maps already carry
unique features. When enabled, the Gen7-authentic split applies: the
base normal absorbs unique micro geometry and the detail slot carries
the tile; the pack gains a `detail` block (repeats per meter, blend
mode, strength, distance fade). When disabled, output is byte-identical
to v0.3.

**Previews** (`generation_7.preview`, off by default) — never alter
canonical PNGs; everything lands under `<asset>/previews/`: linear-space
mip strips with per-level normal renormalization and a shimmer warning
when high-frequency normals average short at distance; deterministic
legacy block-compression previews (BC1-style color, BC5-style
two-channel normals with Z reconstruction, BC4-style masks) with per-map
family suggestions and error stats in the build report; a 3x3 repetition
grid for tiled surfaces. Tiled builds also flag unique landmarks that
would read as obvious repeats.

## Install

```bash
pip install -e .
```

Python ≥ 3.10. Dependencies: numpy, pillow. Nothing else — no OpenCV, no
network, no GPU.

## Use

```bash
# Pixel: photo -> 64x64, 12 colors, bayer dither, tileable
pixelcoat process wall.jpg --width 64 --height 64 --colors 12 \
    --dither bayer --tile both --output build

# Generation 7: photo -> 1024 layered material pack, brick profile
pixelcoat process wall.jpg --mode generation_7 \
    --profile profiles/generation_7/brick.json \
    --width 1024 --height 1024 --tile both --meters-per-tile 2.0 \
    --output build

# Compression previews for an existing pack (reads only; writes
# only under previews/)
pixelcoat preview-compression build/wall/wall.pack.json --profile legacy_bc

# Rebuild any saved recipe (mode travels in the recipe)
pixelcoat build build/wall/wall.pixelcoat.json --output build --force

# Validate recipes
pixelcoat validate recipes/
```

`profiles/generation_7/*.json` are recipe-section fragments (tuned
starting points per material); everything they set can be overridden in
the saved recipe. On PowerShell, keep commands single-line.

## Integrations

`integrations/godot/addons/pixelcoat_importer/` — Godot 4.7 editor
plugin: **Project > Tools > Pixelcoat: Import Pack...** fixes texture
import settings from pack metadata (normal maps, directx green flip,
roughness mip filtering via the source normal, mipmaps), then writes
`<asset>_material.tres` — and `<asset>_material_wet.tres` when wet maps
ship. Detail tiles ride UV2 scaled to repeats_per_meter x
meters_per_tile. `integrations/blender/pixelcoat_import.py` — Blender
4.x add-on building the matching Principled BSDF materials. Both are
driven by the pack manifest, never filename guessing. Details:
`integrations/README.md`.

**Variations**: `generation_7.variations` accepts any of `darker`,
`lighter`, `dirtier`, `damaged` — one-recipe albedo variants (plus
roughness where gloss shifts), identical UV boundaries, listed under
`pack.variants`. Wet remains its own toggle.

**Pixel-path simplification (v0.6, TDD 7.4)**: `--downsample
edge_aware` weights each output cell by similarity to the cell's median
color, so boundaries resolve to their majority side instead of the mud
tone a palette never contained (`--edge-preserve 0..1`).
`--island-removal N` dissolves palette islands of <= N pixels into their
dominant neighbor — 8-connectivity on purpose, so ordered-dither
checkerboards chain diagonally and survive while true specks go.
`simplification.protected_mask` (grayscale, >50% = protected) carries
source detail through smoothing, banding, and island removal: lettering,
logos, window frames. `maps.emissive_mode: "mask"` +
`emissive_mask_path` cuts an emissive straight from an authored mask
(signage/neon feeding engine-side emission).

**Decals (v0.7, TDD 7.11)**: alpha extraction at SOURCE resolution
(feather in source space) from the image's own alpha, a color key
(`--alpha color_key --alpha-key '#ff00ff'`), a luminance threshold, an
authored mask, or corner-seeded background flood select
(`--alpha flood`). Working-res controls: alpha cutoff, pixel-hard
binary alpha (default), dilation, and transparent-RGB defringe —
transparent pixels take extruded neighbor colors so bilinear sampling
and mipmaps never pull a background fringe. `--decal` exports
`<asset>_decal.png` (pack key stays `albedo`, `export_type: "decal"`)
with transparent padding instead of extruded alpha. Premultiplied
export available. Edge-guided subject extraction and polygon selection
are deliberately absent per the TDD's manual-masks-first MVP guidance.

**Atlases (v0.8, TDD 7.15)**: `pixelcoat atlas <packs-or-dirs> --name
city01` packs compatible packs into one atlas PER MAP — every entry's
albedo, normal, and roughness land at the same rect, so one UV drives
every channel; maps missing from some entries get that map's neutral
fill (flat normal, mid roughness). Deterministic shelf packing (same
inputs = same bytes), 90-degree rotation recorded per entry
(`--no-rotate` to disable), `--pow2`, configurable `--gutter` with
half-gutter edge extrusion per entry (mipmap-safe RGB, alpha stays zero
in gutters for decal atlases). Manifest `<atlas>_atlas.json`
(pixelcoat-atlas/1) carries rect_px / uv / rotated / pivot / alpha_mode
/ source_pack per entry, plus `<atlas>_preview.png` with outlined rects
(TDD 8.3).

## Roadmap

The Generation 7 epic (Slices 1-5) is complete. TDD 7.4 simplification
(edge-aware downsampling, island removal, protected masks) shipped in
v0.6. Decals (7.11) shipped in v0.7, atlases (7.15) in v0.8. Remaining
pixel-path items in TDD order: batch folders (6.2), desktop app.
