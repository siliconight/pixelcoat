# Pixelcoat Roadmap Item: Optional Generation 7 Surface Skin Pipeline

**Type:** Roadmap Epic  
**Status:** Proposed  
**Target:** Post-v0.2, after the current material-pack contract and core pipeline are stable  
**Primary owners:** Pixelcoat Core, Recipe/Schema, CLI, Integrations  
**Primary integrations:** Zoo, Patina, Blender, Godot 4.7

## Summary

Add an optional **Generation 7 Surface Skin** output path to Pixelcoat.

This path will convert photographs, scans, painted references, and source textures into stylized material skins inspired by the Xbox 360, PlayStation 3, and comparable PC era of 3D environment art.

The feature is not a higher-resolution version of Pixelcoat's existing pixel-art treatment. It is a separate deterministic processing graph built around:

- Moderately high-resolution base color
- Preserved medium-frequency surface detail
- Macro and micro height extraction
- Base and detail normal maps
- Specular and gloss response
- Modern roughness conversion for Godot and Blender
- Cavity, wear, grime, streaking, damage, and wetness masks
- Tile-safe material variation
- Mipmap and legacy block-compression preview

The existing Pixelcoat pipeline remains the default and must continue producing unchanged outputs.

## Why This Belongs in Pixelcoat

Pixelcoat already owns image-derived surface authoring for the Gabagool Studios environment pipeline. It already provides deterministic recipes, image transforms, tiling assistance, material-map generation, material packs, and downstream consumption by tools such as Zoo and Patina.

Generation 7 skins are therefore a natural optional expansion of Pixelcoat's surface-authoring role.

The expansion must not turn Pixelcoat into a full Substance Designer or Substance Painter replacement. Pixelcoat should remain:

- Offline
- Deterministic
- Batchable
- Art-directable
- Focused on surfaces used in 3D worlds
- Usable through recipes, CLI, and future GUI workflows
- Compatible with the existing Pixelcoat pack contract

## User Value

An environment artist should be able to give Pixelcoat a source image and receive a cohesive, game-ready material pack that has the visual density and layered material response associated with Generation 7 environments.

The artist should not need to manually create every normal, gloss, cavity, wear, grime, and detail layer before testing the surface in Godot or Blender.

### Example Uses

- Concrete and brick walls
- Building facades
- Painted and rusted metal
- Asphalt and sidewalks
- Wood panels and doors
- Machinery and industrial props
- Furniture and vehicle surfaces
- Signs and storefront materials
- Wet, damaged, dirty, or aged surface variants
- Repeating detail textures for large environments

## Product Decision

Pixelcoat will support two explicit processing modes.

### `pixel`

The current low-resolution, palette-controlled, dithered surface pipeline.

```text
Load
-> Transform
-> Downsample
-> Noise Reduce
-> Value Group
-> Tile Assist
-> Palette Quantize
-> Dither
-> Generate Pixel-Aligned Maps
-> Nearest-Neighbor Upscale
-> Pad
-> Export
```

### `generation_7`

A separate layered-material pipeline that preserves and authors more surface information.

```text
Load
-> Transform
-> Establish Working Resolution
-> Convert to Linear Working Data
-> Approximate Lighting Flattening
-> Edge-Preserving Cleanup
-> Frequency Separation
-> Base-Color Stylization
-> Macro and Micro Height Extraction
-> Base and Detail Normal Generation
-> Cavity and Surface-Occlusion Approximation
-> Material Response Generation
-> Wear, Grime, Damage, and Wetness Layers
-> Tile Validation
-> Mipmap and Compression Preview
-> Export Material Pack
```

Generation 7 mode must bypass the following pixel-specific stages unless the artist explicitly enables a compatible version of them:

- Low color-count palette reduction
- Value-band flattening
- Pixel-grid dithering
- Pixel-cluster cleanup
- Nearest-neighbor display scaling
- Stepped PS1-style roughness

## User Story

**As an environment artist,**  
I want to select a Generation 7 surface profile when processing an image,  
so that Pixelcoat produces a layered, stylized material pack with the detail, wear, surface response, and compression character needed for Xbox 360 and PlayStation 3-inspired environments without affecting the existing pixel-art workflow.

## Functional Scope

## 1. Separate Pipeline Dispatch

Add a top-level recipe field:

```json
{
  "processing_mode": "pixel"
}
```

or:

```json
{
  "processing_mode": "generation_7"
}
```

Recipes that do not include `processing_mode` must default to `pixel`.

Recommended dispatch:

```python
def build(recipe: Recipe, out_dir: str) -> dict:
    if recipe.processing_mode == "pixel":
        return build_pixel(recipe, out_dir)

    if recipe.processing_mode == "generation_7":
        return build_generation_7(recipe, out_dir)

    raise ValueError(f"Unsupported processing mode: {recipe.processing_mode}")
```

### Required behavior

- Existing recipes remain valid.
- Existing recipe hashes and outputs remain unchanged where tool-version behavior allows.
- Pixel-specific settings may remain in old recipes but are ignored by Generation 7 mode.
- Generation 7 settings live in their own recipe section.
- Validation returns a clear error when incompatible settings are enabled together.

## 2. Generation 7 Working Resolution

Generation 7 mode must work directly at a material-authoring resolution rather than creating a very small image and enlarging it.

Recommended presets:

| Use | Working Resolution |
|---|---:|
| Small prop or decal | 256 |
| Standard prop or trim | 512 |
| Environment tile | 1024 |
| Large facade or hero surface | 2048 |

The artist may still choose exact width and height.

### Required controls

- Exact width and height
- Longest-side resolution
- Meters per tile
- Target texel density
- Power-of-two warning
- Multiple-of-four warning for block-compression compatibility
- Source-resolution warning when the requested output exceeds useful source detail

## 3. Linear Working Data

Lighting, blending, height extraction, roughness operations, and mip generation should occur using linear working values.

### Required behavior

- Decode source color into a linear working representation where applicable.
- Keep masks, height, normal, roughness, gloss, metallic, and cavity data linear.
- Encode display albedo back to sRGB for standard PNG export.
- Do not apply color gamma correction to data maps.

This should be added as a shared core utility rather than embedded in one Generation 7 node.

## 4. Approximate Lighting Flattening

Photographs often contain directional illumination, shadows, highlights, and exposure variation that should not be permanently baked into a reusable material.

Pixelcoat should offer an approximate lighting-flattening pass.

### Suggested implementation

1. Convert the source to luminance.
2. Create a large-radius blurred illumination estimate.
3. Divide or subtract that estimate from the source luminance.
4. Recombine the corrected luminance with the source chroma.
5. Blend between the original and corrected result using an artist control.

Conceptually:

```text
illumination = large_radius_blur(source_luminance)
flattened_luminance = source_luminance / max(illumination, epsilon)
result = blend(source, recombined_flattened_image, flatten_strength)
```

### Controls

- `lighting_flatten_strength`
- `illumination_radius`
- `shadow_recovery`
- `highlight_compression`
- `preserve_local_contrast`

### Limits

This is an approximation, not true photogrammetric delighting. The tool and documentation must not claim that it reconstructs physically accurate unlit albedo.

## 5. Edge-Preserving Cleanup

The Generation 7 path must remove camera noise, JPEG artifacts, and unwanted high-frequency noise without erasing material boundaries.

The first implementation should remain compatible with Pixelcoat's current NumPy and Pillow dependency model.

### MVP techniques

- Median filtering
- Small-radius Gaussian or box filtering
- Edge-mask-guided blending between original and filtered images
- Chroma-noise reduction stronger than luminance reduction
- Artist-provided protected and suppression masks when those systems become available

### Later option

An optional accelerated edge-aware backend may be considered later, but the Generation 7 MVP must not require OpenCV, cloud processing, a GPU, or neural inference.

## 6. Frequency Separation

Separate broad material forms from fine detail so each band can drive different outputs.

### Suggested implementation

```text
low_frequency = blur(source, macro_radius)
high_frequency = source - low_frequency
```

A second smaller-radius band may be used to isolate micro detail:

```text
micro_base = blur(source, micro_radius)
micro_detail = source - micro_base
```

### Use of each band

**Low frequency**

- Broad base-color variation
- Large stains and discoloration
- Macro height
- Broad surface occlusion
- Large wear patterns

**High frequency**

- Grain
- Pores
- Scratches
- Fine cracks
- Detail normal
- Cavity
- Sharpening

### Required controls

- `macro_radius`
- `micro_radius`
- `detail_gain`
- `noise_threshold`
- `protected_detail_mask`
- `suppression_mask`

Small-amplitude high-frequency information must be thresholded so compression noise does not become false geometry.

## 7. Base-Color Stylization

Generation 7 albedo should preserve more information than Pixelcoat's pixel output, but it must still look art-directed rather than like an unchanged photograph.

### Techniques

- Shadow and highlight compression
- Local contrast control
- Saturation scaling
- Hue-range bias
- Limited but moderate color clustering
- Selective sharpening
- Broad color-zone preservation
- Optional gradient compression
- Material-preset color treatment

### Recommended color-count range

- 32 to 64 colors for heavily stylized surfaces
- 64 to 128 colors for standard Generation 7 skins
- Up to 256 colors when preserving signage or complex painted detail

Palette clustering should remain perceptual and deterministic.

Dithering should default to off. A subtle, source-scale noise or ordered pattern may be offered as an optional treatment, but it must not use the existing pixel-grid behavior by default.

## 8. Macro and Micro Height

The current Pixelcoat pipeline derives one height field from post-dither albedo. Generation 7 mode needs separate macro and micro height layers.

### Macro height

Represents:

- Brick depth
- Mortar recess
- Dents
- Large chips
- Plank separation
- Broad surface deformation

### Micro height

Represents:

- Concrete pores
- Wood grain
- Fabric weave
- Fine scratches
- Paint texture
- Fine cracks

### Suggested combination

```text
combined_height =
    macro_height * macro_strength
    + micro_height * micro_strength
```

### Supported height sources

1. Inferred from source luminance and local contrast
2. Imported height map
3. Combined inferred and imported height
4. Artist-painted mask when GUI mask painting exists

### Material-aware rules

Brightness must not be assumed to mean physical height in every material.

Each material preset should define how much luminance, edges, local contrast, imported masks, and directional structure contribute.

Examples:

| Material | Macro Height | Micro Height | Notes |
|---|---:|---:|---|
| Brick | High | Medium | Mortar should recess |
| Concrete | Low | Medium-high | Suppress broad lighting gradients |
| Painted metal | Very low | Low-medium | Preserve dents, chips, and scratches |
| Rusted metal | Low-medium | Medium-high | Rust buildup may raise locally |
| Wood | Medium | Medium | Preserve directional grain |
| Fabric | Very low | High | Most response comes from microstructure |
| Asphalt | Low-medium | High | Aggregate drives microstructure |

## 9. Base and Detail Normal Maps

Generate two aligned normal maps.

### Base normal

Generated from macro height.

### Detail normal

Generated from micro height, an imported detail map, or an extracted reusable detail texture.

### Suggested gradient method

Use wrap-aware central differences or Sobel gradients:

```text
dx = height[x + 1] - height[x - 1]
dy = height[y + 1] - height[y - 1]
normal = normalize([-dx * strength, -dy * strength, 1])
```

### Required behavior

- OpenGL Y-positive output remains the default.
- Green-channel inversion remains available for DirectX-style consumers.
- Flat height produces a neutral normal.
- Tiled axes use wraparound sampling.
- Normals are renormalized after resizing and mip generation.
- Base and detail normal strength are independently adjustable.

### Outputs

```text
<asset>_normal.png
<asset>_detail_normal.png
```

## 10. Cavity and Surface-Occlusion Approximation

Pixelcoat cannot infer true geometry-based ambient occlusion from one flat image. It can generate useful surface-scale cavity and broad occlusion approximations.

### Cavity

Detect narrow recesses and cracks using local differences between height and small-radius blur.

```text
small_cavity = blur(height, small_radius) - height
```

### Surface occlusion

Detect broader recessed regions using a larger radius.

```text
broad_occlusion = blur(height, large_radius) - height
```

### Outputs

```text
<asset>_cavity.png
<asset>_surface_occlusion.png
```

The pack and UI must label the broader map `surface_occlusion`, not claim it is true baked ambient occlusion.

## 11. Material Response

Generation 7 mode should author a legacy-style material response while also exporting modern Godot and Blender-compatible maps.

### Primary authoring model

- Specular level or color
- Gloss
- Roughness derived from gloss
- Explicit metallic mask only when selected or supplied

### Relationship

```text
roughness = 1.0 - gloss
```

### Required outputs

```text
<asset>_specular.png
<asset>_gloss.png
<asset>_roughness.png
```

`metallic.png` is optional and must not be guessed from luminance alone.

### Material presets

The first supported presets should be:

- Concrete
- Brick
- Wood
- Painted metal

Later presets:

- Rusted metal
- Bare metal
- Plastic
- Glass
- Asphalt
- Tile
- Plaster
- Fabric

Each preset should define:

- Base specular level
- Base gloss
- Roughness variation
- Metallic state
- Macro and micro height weighting
- Base and detail normal strength
- Cavity influence
- Wear behavior
- Grime behavior
- Wetness response
- Color treatment defaults

## 12. Edge Wear

Generate edge wear from height gradients and raised-surface detection rather than applying scratches uniformly.

### Suggested mask

```text
edge_strength = gradient_magnitude(macro_height)
raised_area = max(macro_height - local_mean, 0)
wear_mask = edge_strength * raised_area * seeded_low_frequency_noise
```

### Artist controls

- Amount
- Width
- Contrast
- Noise scale
- Directional bias
- Protected mask
- Suppression mask
- Undercoat color
- Exposed material type

### Possible effects

- Lighten or desaturate albedo
- Reveal primer or bare material
- Increase or decrease gloss
- Increase metallic response for exposed metal
- Reduce painted micro-normal response
- Add edge-specific cavity breakup

All effects must be driven by the same exported wear mask.

## 13. Cavity Grime and Material Dirt

Grime should accumulate in recesses and along selected directions.

### Suggested mask

```text
grime_mask =
    cavity
    * seeded_low_frequency_noise
    * accumulation_bias
```

### Grime types

- Dust
- Soot
- Oil
- Mud
- Water staining
- Rust bleed

### Material effects

**Dust**

- Darken or lighten depending on preset
- Increase roughness
- Reduce micro-normal slightly

**Oil**

- Darken albedo
- Lower roughness
- Increase gloss
- Add localized streaking

**Mud**

- Shift color
- Increase macro height slightly
- Add roughness and breakup

**Water staining**

- Shift color and value
- Add directional streaks
- Create gloss variation

**Rust bleed**

- Add warm color shift
- Increase local roughness
- Extend downward from exposed or cavity regions

## 14. Directional Streaking

Support deterministic streaking for water, rust, soot, and grime.

### Suggested recurrence

```text
streak[y] = max(source_mask[y], streak[y - 1] * decay)
```

The implementation should support arbitrary direction by rotating or scanning along the chosen axis.

### Controls

- Direction
- Length
- Decay
- Width
- Density
- Seed
- Gravity bias
- Source mask
- Tile wrap

The operation must remain seamless on enabled tile axes.

## 15. Wetness Variant

Allow the artist to export a dry material and an aligned wet variant.

### Wetness mask sources

- Cavity
- Broad low areas
- Bottom-of-surface bias
- Imported mask
- Seeded variation
- Artist mask

### Wetness effects

- Modestly darken base color
- Increase gloss
- Reduce roughness
- Reduce micro-normal strength
- Preserve most macro-normal response
- Optionally add a secondary water or ripple detail normal

Wetness must be non-destructive. It should be applied as an aligned variant or exported mask rather than permanently replacing dry maps.

### Outputs

```text
<asset>_wetness.png
<asset>_wet_albedo.png
<asset>_wet_roughness.png
```

The MVP may export only the mask and allow the Godot or Blender importer to construct the variant.

## 16. Detail Textures

Large Generation 7 surfaces often use a smaller, highly repeated detail albedo and detail normal to create close-range sharpness.

Pixelcoat should support:

1. Extracted detail from the source high-frequency band
2. Procedurally generated detail
3. Imported reusable detail texture
4. Material-preset detail library

### Outputs

```text
<asset>_detail_albedo.png
<asset>_detail_normal.png
<asset>_detail_mask.png
```

### Manifest metadata

- Detail repetition per meter
- Blend mode
- Detail strength
- UV channel or triplanar recommendation
- Distance fade recommendation

Godot's material system supports secondary albedo and normal detail maps, so this should be represented directly in the Pixelcoat pack rather than flattened into the base texture.

## 17. Tiling and Variation

Generation 7 outputs must reuse Pixelcoat's tile-safe behavior and extend it to every generated map.

### Requirements

- Every map has identical dimensions and alignment.
- Every enabled tile axis uses wrap-aware filtering.
- Height, normal, cavity, wear, grime, wetness, and detail masks match at seams.
- Edge correction occurs before map generation where possible.
- Post-generated effects also support wraparound.
- Tile preview supports at least a 3 by 3 repetition grid.
- Repetition-frequency warnings identify obvious repeated stains or unique landmarks.

### Variation exports

- Base
- Darker
- Lighter
- Dirtier
- Damaged
- Wet
- Emissive, where applicable

All variants must retain the same UV boundaries.

## 18. Mipmap Generation and Preview

Generation 7 materials must be judged at multiple viewing distances.

### Required behavior

- Generate preview mip levels.
- Downsample color in linear working space.
- Renormalize normals at each mip.
- Preserve alpha coverage for cutout materials where applicable.
- Provide a distance or mip-level preview.
- Warn when high-frequency normal detail causes distant shimmer.
- Recommend roughness filtering using the related normal map in Godot.

The source PNG exports remain full resolution. Generated mip files may remain preview-only until the import integrations consume them.

## 19. Legacy Block-Compression Preview

Generation 7 surfaces should optionally preview the visible artifacts associated with legacy BC and DXT-style texture compression.

### MVP

Implement or integrate a deterministic preview that approximates 4 by 4 block compression.

Preview categories:

- Color texture compression
- Color plus alpha compression
- Two-channel normal compression
- Single-channel mask compression

### Required behavior

- Preview does not overwrite source PNG outputs.
- The UI can compare uncompressed and compressed results.
- The report identifies the suggested compression family for each map.
- Texture dimensions are checked for compatibility.
- Normal-map compression preview reconstructs and renormalizes the missing component when appropriate.

### Later option

Pixelcoat may optionally call an installed external DDS or texture-compression tool. This must remain optional and cannot become a requirement for deterministic PNG pack generation.

## Proposed Recipe Schema

This example is intentionally additive and keeps existing pixel settings intact.

```json
{
  "schema_version": "0.3",
  "tool_version": "0.3.0",
  "asset_id": "warehouse_wall_01",
  "processing_mode": "generation_7",

  "source": {
    "path": "sources/warehouse_wall.jpg"
  },

  "transform": {
    "crop": null,
    "perspective_quad": null,
    "rotation_degrees": 0
  },

  "generation_7": {
    "resolution": {
      "working_width": 1024,
      "working_height": 1024,
      "resample_method": "lanczos"
    },

    "color": {
      "lighting_flatten_strength": 0.35,
      "illumination_radius": 48,
      "shadow_recovery": 0.15,
      "highlight_compression": 0.25,
      "saturation_scale": 0.85,
      "local_contrast": 0.20,
      "maximum_colors": 96
    },

    "frequency": {
      "macro_radius": 12,
      "micro_radius": 2,
      "noise_threshold": 0.025,
      "detail_gain": 1.20
    },

    "height": {
      "source": "inferred",
      "import_path": null,
      "macro_strength": 0.80,
      "micro_strength": 0.35,
      "invert": false
    },

    "normal": {
      "base_strength": 1.0,
      "detail_strength": 0.45,
      "flip_green": false
    },

    "material": {
      "preset": "painted_metal",
      "workflow": "specular_gloss",
      "specular_level": 0.50,
      "gloss": 0.58,
      "roughness_variation": 0.20,
      "emit_roughness": true,
      "emit_metallic": true
    },

    "weathering": {
      "edge_wear": 0.20,
      "cavity_grime": 0.25,
      "vertical_streaks": 0.15,
      "rust_bleed": 0.10,
      "seed": 34127
    },

    "wetness": {
      "enabled": false,
      "amount": 0.0,
      "cavity_bias": 0.65,
      "bottom_bias": 0.25
    },

    "detail_texture": {
      "enabled": true,
      "source": "extracted",
      "import_path": null,
      "size": 128,
      "repeats_per_meter": 8.0,
      "blend_mode": "overlay"
    },

    "preview": {
      "generate_mipmaps": true,
      "compression_preview": "legacy_bc",
      "preview_distance_meters": 5.0
    }
  },

  "tiling": {
    "enabled": true,
    "axes": "both"
  },

  "export": {
    "type": "surface_texture",
    "format": "png",
    "padding": 8,
    "meters_per_tile": 2.0
  }
}
```

## Proposed Material-Pack Outputs

A Generation 7 pack may include:

```text
warehouse_wall_01_albedo.png
warehouse_wall_01_normal.png
warehouse_wall_01_detail_normal.png
warehouse_wall_01_specular.png
warehouse_wall_01_gloss.png
warehouse_wall_01_roughness.png
warehouse_wall_01_metallic.png
warehouse_wall_01_height.png
warehouse_wall_01_cavity.png
warehouse_wall_01_surface_occlusion.png
warehouse_wall_01_detail_albedo.png
warehouse_wall_01_detail_mask.png
warehouse_wall_01_wear.png
warehouse_wall_01_grime.png
warehouse_wall_01_wetness.png
warehouse_wall_01_emissive.png
warehouse_wall_01.pixelcoat.json
warehouse_wall_01.pack.json
build_report.json
```

Only enabled outputs are generated.

## Proposed Pack Manifest Additions

Preserve `pixelcoat-pack/1` compatibility where possible. Add fields rather than making downstream tools guess behavior from filenames.

```json
{
  "schema": "pixelcoat-pack/2",
  "tool_version": "0.3.0",
  "asset_id": "warehouse_wall_01",
  "processing_mode": "generation_7",
  "material_profile": "painted_metal",
  "material_workflow": "specular_gloss",

  "maps": {
    "albedo": "warehouse_wall_01_albedo.png",
    "normal": "warehouse_wall_01_normal.png",
    "detail_normal": "warehouse_wall_01_detail_normal.png",
    "specular": "warehouse_wall_01_specular.png",
    "gloss": "warehouse_wall_01_gloss.png",
    "roughness": "warehouse_wall_01_roughness.png",
    "metallic": "warehouse_wall_01_metallic.png",
    "height": "warehouse_wall_01_height.png",
    "cavity": "warehouse_wall_01_cavity.png",
    "surface_occlusion": "warehouse_wall_01_surface_occlusion.png",
    "wear": "warehouse_wall_01_wear.png",
    "grime": "warehouse_wall_01_grime.png",
    "wetness": "warehouse_wall_01_wetness.png"
  },

  "tileable": "both",
  "meters_per_tile": 2.0,

  "detail": {
    "repeats_per_meter": 8.0,
    "blend_mode": "overlay",
    "strength": 0.65
  },

  "import_hints": {
    "color_space": {
      "albedo": "srgb",
      "detail_albedo": "srgb",
      "normal": "linear",
      "detail_normal": "linear",
      "roughness": "linear",
      "metallic": "linear",
      "height": "linear",
      "masks": "linear"
    },
    "generate_mipmaps": true,
    "normal_format": "opengl",
    "albedo_compression": "color_block",
    "normal_compression": "two_channel",
    "roughness_source_normal": "warehouse_wall_01_normal.png"
  }
}
```

## CLI Additions

### Direct Generation 7 processing

```bash
pixelcoat process wall.jpg \
  --mode generation_7 \
  --profile profiles/gen7_concrete.json \
  --width 1024 \
  --height 1024 \
  --tile both \
  --output build
```

### Build an existing recipe

```bash
pixelcoat build recipes/warehouse_wall_01.pixelcoat.json \
  --output build \
  --force
```

### Preview compression without replacing source exports

```bash
pixelcoat preview-compression \
  build/warehouse_wall_01/warehouse_wall_01.pack.json \
  --profile legacy_bc \
  --output build/warehouse_wall_01/previews
```

## Code Organization

Recommended additions:

```text
pixelcoat/
  core/
    pipeline.py
    pipeline_pixel.py
    pipeline_generation_7.py
    color_space.py
    frequency.py
    lighting_flatten.py
    material_response.py
    weathering.py
    mipmaps.py
    compression_preview.py
    maps.py
  profiles/
    generation_7/
      concrete.json
      brick.json
      wood.json
      painted_metal.json
  integrations/
    blender/
    godot/
```

### Current-code alignment

- `recipe.py` remains the reproducibility contract.
- `pipeline.py` becomes the mode dispatcher.
- The current fixed processing graph moves into `pipeline_pixel.py` with no intended output change.
- Generation 7 map logic should be split into focused modules rather than making `maps.py` a single large material-authoring file.
- Pack generation should remain centralized so downstream consumers continue reading one contract.
- The build report should record mode, enabled stages, map statistics, warnings, and preview outputs.

## Delivery Plan

## Slice 1: Pipeline Separation and Backward Compatibility

### Scope

- Add `processing_mode`.
- Default missing mode to `pixel`.
- Move the current graph behind `build_pixel`.
- Add `build_generation_7` stub and validation.
- Bump recipe schema only if required.
- Add pack field for processing mode.
- Add regression fixtures for existing pixel recipes.

### Exit criteria

- Existing Pixelcoat tests pass unchanged.
- Existing reference recipes produce the expected hashes.
- Generation 7 recipes validate but fail with a clear "not implemented" message until Slice 2 lands.
- Downstream tools can ignore the additive pack field.

## Slice 2: Core Generation 7 Material Stack

### Scope

- Generation 7 working resolution
- Linear color utilities
- Approximate lighting flattening
- Edge-preserving cleanup
- Frequency separation
- Base-color stylization
- Macro and micro height
- Base and detail normal
- Cavity and surface occlusion
- Specular, gloss, and roughness
- Concrete, brick, wood, and painted-metal presets

### Exit criteria

- One source image can generate a complete dry material pack.
- Every map is aligned and tile-safe.
- Material response differs meaningfully between the four presets.
- The output can be assembled manually in Godot 4.7 and Blender.

## Slice 3: Weathering and Variants

### Scope

- Edge wear
- Cavity grime
- Directional streaks
- Rust bleed
- Exported masks
- Wetness mask and wet variant behavior
- Base, dirtier, damaged, and wet variations

### Exit criteria

- Weathering is deterministic by seed.
- Wear favors raised transitions.
- Grime favors cavities.
- Streaking follows the requested direction.
- Wetness affects only the wetness mask.
- All variants share dimensions and UV boundaries.

## Slice 4: Detail, Mipmaps, and Compression Preview

### Scope

- Extracted detail albedo
- Detail normal
- Detail mask
- Repetition metadata
- Mipmap preview
- Normal renormalization
- Legacy block-compression preview
- Compression recommendations in the build report

### Exit criteria

- Artists can compare source, uncompressed, and compressed previews.
- Close-range detail is separate from base maps.
- Distant preview does not use an unfiltered full-resolution texture.
- No preview step changes the canonical PNG outputs.

## Slice 5: Godot 4.7 and Blender Delivery

### Scope

- Extend pack importers.
- Create StandardMaterial3D or ShaderMaterial resources.
- Connect base albedo, normal, roughness, metallic, surface occlusion, detail albedo, detail normal, and detail mask.
- Configure mipmaps and texture usage hints.
- Configure Blender material nodes with the same maps.
- Expose dry and wet material options.

### Exit criteria

- A pack can be imported without manually renaming or realigning maps.
- Godot materials use detail textures and normal maps correctly.
- Blender and Godot previews are visually comparable.
- Importer behavior is driven by pack metadata rather than filename assumptions.

## Acceptance Criteria

### Compatibility

- Existing recipes without `processing_mode` use `pixel`.
- Existing pixel recipes remain valid.
- The existing pixel graph does not run through Generation 7 stages.
- Existing Pixelcoat packs remain consumable.
- Downstream tools do not need Generation 7 support to consume older packs.

### Determinism

- Same source bytes, recipe, seed, and tool version produce byte-identical canonical outputs.
- Every procedural weathering operation uses the saved recipe seed.
- Build reports include the source hash, recipe version, processing mode, and enabled outputs.

### Map correctness

- All generated maps have identical width, height, padding, and UV alignment.
- Flat height generates a neutral normal map.
- Normal values are normalized within the accepted tolerance.
- Tiled edges match on every enabled axis.
- Gloss and roughness satisfy `roughness = 1 - gloss` within one 8-bit value.
- Metallic is generated only from a preset rule, explicit value, or artist mask.
- Cavity and surface occlusion are exported separately.
- Base normal and detail normal are exported separately.

### Material behavior

- Concrete, brick, wood, and painted metal produce visibly different material responses.
- Height inference does not rely on source luminance alone.
- Edge wear favors raised transitions.
- Grime favors cavity regions.
- Wetness lowers roughness and reduces micro-normal strength only inside the wetness mask.
- Detail texture scaling is stored in the pack manifest.

### Preview and delivery

- Mipmap preview uses filtered lower-resolution levels.
- Normals are renormalized after mip generation.
- Compression preview uses 4 by 4 block behavior or an approved equivalent approximation.
- Compression preview never replaces canonical outputs.
- The Godot importer connects supported maps to appropriate material properties.
- The Blender importer treats data maps as non-color data.

### Performance

Initial target on a standard developer workstation:

| Input | Expected target |
|---|---:|
| 512 by 512, core maps | Under 2 seconds |
| 1024 by 1024, core maps | Under 8 seconds |
| 2048 by 2048, full weathering | Under 30 seconds |

These are roadmap targets, not release guarantees. Performance tests should run in CI using smaller deterministic fixtures, with local benchmark scripts for full-size material packs.

## Test Plan

## Unit Tests

- Linear to sRGB round trip
- Wrap-aware blur
- Frequency-band reconstruction
- Flat-height neutral normal
- Normal green-channel inversion
- Gloss to roughness conversion
- Cavity response on synthetic recess
- Wear response on synthetic raised edge
- Grime response on synthetic cavity
- Directional streak decay
- Wetness-mask isolation
- Mipmap normal renormalization
- Multiple-of-four compression validation

## Golden-Image Tests

Add small synthetic or CC0 fixtures for:

- Concrete
- Brick
- Wood
- Painted metal

Each fixture should have expected outputs for:

- Albedo
- Macro height
- Micro height
- Base normal
- Detail normal
- Roughness
- Cavity
- Wear
- Grime

Golden tests should be versioned intentionally. A visual algorithm change requires an explicit fixture update and changelog note.

## Integration Tests

- Build Pixel mode after graph separation.
- Build Generation 7 dry material.
- Build tileable Generation 7 material.
- Build weathered and wet variants.
- Rebuild from saved recipe.
- Validate pack manifest.
- Import pack into a Godot test project.
- Import pack into a Blender test scene when the integration exists.
- Confirm Zoo and Patina safely ignore maps they do not yet use.

## Risks and Mitigations

### Risk: Scope expands into a full PBR authoring suite

**Mitigation:** Keep the feature profile-driven and image-derived. Support a focused set of maps and material presets. Do not add node-graph authoring, texture painting, or arbitrary procedural graph construction to this epic.

### Risk: Height inference produces false geometry

**Mitigation:** Use material-aware presets, frequency separation, thresholding, imported height support, and exported intermediate masks. Clearly label inferred height as an approximation.

### Risk: Photographic lighting remains baked into albedo

**Mitigation:** Add approximate lighting flattening, shadow recovery, highlight compression, and an artist strength control. Do not claim physically accurate delighting.

### Risk: Too many generated maps make packs difficult to consume

**Mitigation:** Export only enabled maps. Keep one manifest contract. Provide importer defaults and map packing as a later optimization.

### Risk: New graph breaks deterministic outputs

**Mitigation:** Separate pipeline modules, preserve the old graph, save every seed, add golden-image tests, and include the tool version in every pack and build report.

### Risk: NumPy and Pillow are too slow for high-resolution filters

**Mitigation:** Implement separable filters, reuse intermediate buffers, avoid Python pixel loops, benchmark each stage, and add an optional accelerated backend only after the dependency-free path works.

### Risk: "Generation 7" becomes an overly broad visual label

**Mitigation:** Define the feature by functional material traits rather than claiming to reproduce every game from the era. Ship material profiles that artists can tune and save.

## Non-Goals

- Reproducing a specific copyrighted game's textures
- Scraping or distributing copyrighted texture libraries
- Creating or modifying 3D geometry
- Automatic UV unwrapping
- True photogrammetric material reconstruction
- Physically accurate delighting from one image
- Runtime image generation in a shipped game
- Neural image generation
- Cloud processing
- Replacing Substance Designer or Substance Painter
- Making Generation 7 mode the default
- Changing existing Pixelcoat pixel outputs
- Requiring a GPU
- Requiring OpenCV for the MVP
- Producing final materials without artist review

## Dependencies

The recommended roadmap order is:

1. Stabilize the current v0.2 material-map and pack behavior.
2. Complete recipe and pack compatibility tests.
3. Add processing-mode dispatch.
4. Implement the Generation 7 core material stack.
5. Implement weathering and variants.
6. Add mipmap and compression preview.
7. Extend Godot 4.7 and Blender importers.
8. Add GUI controls after the CLI and recipe path are proven.

This feature should not block current roadmap work for edge-aware downsampling, masks, decals, atlas packing, batch folders, or the desktop app. It should be planned as a separate advanced surface-authoring epic that can reuse those capabilities as they become available.

## Definition of Done

The roadmap item is complete when:

- Pixelcoat supports `pixel` and `generation_7` as explicit processing modes.
- Existing Pixelcoat recipes continue working.
- The Generation 7 graph produces aligned, deterministic material packs.
- Concrete, brick, wood, and painted-metal profiles are included.
- Core outputs include albedo, base normal, detail normal, specular, gloss, roughness, height, cavity, and surface occlusion.
- Wear, grime, streaking, and wetness masks are available.
- Detail-texture metadata is included in the pack.
- Mipmap and compression previews are available without changing canonical outputs.
- Automated tests cover determinism, seams, map alignment, map math, and visual fixtures.
- Godot 4.7 and Blender can consume the material pack without manual map renaming or alignment.
- The TDD, README roadmap, recipe schema, pack schema, CLI help, and examples are updated.

## Technical References

These references support the implementation direction and should be used as engineering guidance, not as visual assets.

- Pixelcoat repository and current processing graph:  
  https://github.com/siliconight/pixelcoat

- Pixelcoat technical design document:  
  https://github.com/siliconight/pixelcoat/blob/main/docs/TDD_v0_1.md

- Godot StandardMaterial3D detail albedo and detail normal support:  
  https://docs.godotengine.org/en/stable/tutorials/3d/standard_material_3d.html

- Godot image import, mipmaps, and roughness filtering guidance:  
  https://docs.godotengine.org/en/stable/tutorials/assets_pipeline/importing_images.html

- Microsoft Direct3D block-compression overview:  
  https://learn.microsoft.com/en-us/windows/win32/direct3d10/d3d10-graphics-programming-guide-resources-block-compression

- Epic Games detail-texturing explanation:  
  https://dev.epicgames.com/documentation/unreal-engine/texturing-material-functions-in-unreal-engine

- NVIDIA Texture Tools compression and mipmap preview reference:  
  https://developer.nvidia.com/texture-tools-exporter

- NVIDIA guidance on linear image processing:  
  https://developer.nvidia.com/gpugems/gpugems3/part-iv-image-effects/chapter-24-importance-being-linear
