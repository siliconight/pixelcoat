# Pixelcoat

*Controlled pixel-art surface treatments for 3D worlds.*

Pixelcoat converts ordinary images — photographs, references, logos, scans —
into stylized low-resolution artwork designed to live ON 3D environments:
projected facades, decals, signs, posters, repeating materials, trim sheets.
It is not a photo filter and its output is not standalone 2D art.

Deterministic, offline, batchable, art-directable. Same source bytes + same
recipe + same version = same output hash, always. Full design:
[docs/TDD_v0_1.md](docs/TDD_v0_1.md).

## Status: v0.4.x — two processing modes

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

## Roadmap

Gen7 Slice 5 (Godot 4.7 / Blender importers driven by pack metadata) and
one-recipe variation exports (darker/dirtier/damaged — the masks already
ship, so importers can build these today) arrive next. Pixel-path items
(edge-aware downsampling, masks, decals, atlases, batch, GUI) continue on
the TDD order.
