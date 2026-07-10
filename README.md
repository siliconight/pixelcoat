# Pixelcoat

*Controlled pixel-art surface treatments for 3D worlds.*

Pixelcoat converts ordinary images — photographs, references, logos, scans —
into stylized low-resolution artwork designed to live ON 3D environments:
projected facades, decals, signs, posters, repeating materials, trim sheets.
It is not a photo filter and its output is not standalone 2D art.

Deterministic, offline, batchable, art-directable. Same source bytes + same
recipe + same version = same output hash, always. Full design:
[docs/TDD_v0_1.md](docs/TDD_v0_1.md).

## Status: v0.1.x — core + CLI

The MVP path proves the recipe -> texture pipeline before any GUI exists.
Current graph:

```
Load -> Crop/Perspective -> Downsample -> Noise Reduce -> Value Group
     -> Tile Assist -> OKLab Palette Quantize -> Dither -> Upscale -> Pad
     -> Export (albedo + recipe + build report)
```

Palette work happens in OKLab (perceptual clustering, TDD §12.2). Dithering
is grid-aligned and can never introduce colors outside the active palette.

## Install

```bash
pip install -e .
```

Python ≥ 3.10. Dependencies: numpy, pillow. Nothing else — no OpenCV, no
network, no GPU.

## Use

```bash
# Direct: photo -> 64x64, 12 colors, bayer dither, tileable
pixelcoat process wall.jpg --width 64 --height 64 --colors 12 \
    --dither bayer --tile both --output build

# Shared project palette (hex-list JSON):
pixelcoat process sign.jpg --width 128 --height 64 \
    --palette profiles/night_city_16.json --dither floyd_steinberg

# Every build writes <asset>.pixelcoat.json next to the output — the
# reproducible session. Rebuild it any time:
pixelcoat build build/sign/sign.pixelcoat.json --output build --force

# Check recipes in CI:
pixelcoat validate recipes/
```

## Pipeline position

Pixelcoat is the 2D surface-authoring sibling in the GabagoolStudios
environment pipeline (TDD §24): Deli Counter shapes spaces, Zoo compiles
assets, **Pixelcoat authors image-derived surface art**, Patina applies the
art pass, Lux owns the final lit look. Patina's `patina-photo` rectify path
is the ancestor of this tool and will eventually delegate here.

## Roadmap

Post-v0.1 in TDD order: edge-aware downsampling (§12.1), protected/
suppression masks, alpha/decal extraction (§7.11), material maps (§7.13),
atlas packing (§7.15), batch folders, then the PySide6 desktop app and the
Blender/Godot importers.
