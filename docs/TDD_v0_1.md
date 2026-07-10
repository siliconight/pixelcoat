# Pixelcoat
## Technical Design Document

**Version:** 0.1  
**Status:** Proposed  
**Target Platforms:** Windows and Linux  
**Primary Integrations:** Blender and Godot 4.7  
**License Recommendation:** MIT or Apache 2.0  

---

## 1. Executive Summary

Pixelcoat is an offline image-processing tool that converts ordinary image files into stylized 2D pixel art designed specifically for use on 3D environments.

The output is not intended to stand alone as finished 2D artwork. Its purpose is to become a visual layer that can be:

- Projected onto 3D surfaces
- Painted into an existing texture set
- Used as decals, signs, posters, grime, graffiti, windows, storefronts, props, and facade detail
- Converted into trim sheets or texture atlases
- Previewed on simple 3D geometry before export

Pixelcoat should help environment artists quickly turn photographs, concept images, logos, scanned materials, or hand-painted references into cohesive low-resolution artwork that looks intentional when applied to a 3D world.

The system must be deterministic, batchable, offline, and art-directable. It should prioritize readable shapes, controlled palettes, clear value grouping, and texture continuity over literal photographic accuracy.

---

## 2. Product Goal

Enable an environment artist to take an image and produce a projection-ready or texture-paint-ready pixel-art asset in minutes without manually rebuilding the image pixel by pixel.

### Example Use Cases

1. Convert a photograph of a storefront into a stylized facade texture.
2. Convert a sign or poster into a pixel-art decal.
3. Convert brick, concrete, tile, wood, or metal references into repeating environment textures.
4. Convert a city photograph into a low-resolution background card.
5. Convert graffiti, stickers, stains, cracks, and damage into transparent overlays.
6. Convert a window photograph into an emissive night-window texture.
7. Convert a reference prop image into a texture that can be projected onto simplified geometry.
8. Process a folder of source images into a consistent atlas using one shared style profile.

---

## 3. Design Principles

### 3.1 Environment Art First

Every feature must support the final act of placing the image onto a 3D surface.

Pixelcoat is not a general-purpose photo filter application. It should make environment production faster.

### 3.2 Stylization Over Reduction

Simple nearest-neighbor resizing is not enough. Pixelcoat must preserve important silhouettes, edges, material breaks, and focal details while removing noise.

### 3.3 Art Direction Over Automation

The artist must be able to control:

- Resolution
- Palette
- Edge strength
- Detail preservation
- Dithering
- Material treatment
- Transparency
- Tiling behavior
- Projection behavior

### 3.4 Deterministic and Offline

The same input, settings, version, and random seed must always produce the same output.

No cloud service or generative AI dependency is required.

### 3.5 Non-Destructive Workflow

Source images must never be overwritten. Every operation should be represented in a saved recipe that can be adjusted and regenerated.

### 3.6 Pipeline Friendly

Pixelcoat must support:

- Single image processing
- Folder batch processing
- Command-line processing
- GUI-based art direction
- Saved presets
- Machine-readable manifests
- Blender and Godot import helpers

---

## 4. Scope

### 4.1 In Scope

- PNG, JPG, JPEG, WEBP, BMP, and TIFF input
- Pixel-art conversion
- Palette reduction
- Controlled dithering
- Edge-aware simplification
- Material-specific presets
- Alpha extraction and mask generation
- Seamless texture assistance
- Decal generation
- Trim-sheet and atlas packing
- Normal, roughness, metallic, emissive, and height-mask generation
- Blender preview and texture assignment
- Godot 4.7 material generation
- Batch processing
- CLI and desktop GUI
- JSON-based recipes and manifests

### 4.2 Out of Scope

- Creating or modifying 3D geometry
- Full UV unwrapping
- Automated photogrammetry
- Neural image generation
- Image ownership or copyright verification
- Character sprite animation
- General digital painting
- Full PBR authoring comparable to Substance 3D Designer or Painter
- Runtime image conversion inside the shipped game

---

## 5. Definitions

### Source Image

The original image supplied by the artist.

### Pixel Asset

A stylized low-resolution output intended for use on a 3D surface.

### Recipe

A JSON document containing every setting required to reproduce an output.

### Style Profile

A reusable collection of artistic settings such as palette, edge behavior, dithering, material response, and export scale.

### Projection Ready

An image with predictable dimensions, transparency, padding, color space, and metadata suitable for planar projection, decals, texture painting, or shader sampling.

### Working Resolution

The internal low-resolution canvas where pixel decisions are made.

### Display Resolution

The exported image resolution after nearest-neighbor enlargement.

### Material Pack

A group of texture maps and metadata representing one environment-art asset.

---

## 6. Primary User Workflow

### 6.1 Single Image Workflow

1. Artist imports an image.
2. Pixelcoat analyzes dimensions, contrast, alpha, dominant colors, and edge density.
3. Artist selects an output type:
   - Surface texture
   - Decal
   - Sign or poster
   - Window or emissive panel
   - Background card
   - Material sample
   - Trim strip
4. Artist selects a style profile.
5. Pixelcoat generates a preview.
6. Artist adjusts resolution, palette, value grouping, edge behavior, detail masks, and dithering.
7. Artist optionally defines crop, perspective correction, alpha regions, tiling boundaries, and protected details.
8. Pixelcoat generates texture maps and preview files.
9. Artist exports to Blender, Godot, or a standard folder.

### 6.2 Batch Workflow

1. Artist selects a folder.
2. Artist assigns one style profile to all images or maps presets by filename pattern.
3. Pixelcoat processes each image deterministically.
4. Failed files are reported without stopping the full batch.
5. Outputs are written with per-asset manifests.
6. Optional atlas generation combines compatible outputs.

### 6.3 Blender Workflow

1. Artist selects an object or face set.
2. Pixelcoat Blender add-on imports a Pixelcoat material pack.
3. The artist chooses:
   - Replace material
   - Add decal plane
   - Project from current view
   - Bake into existing texture
4. The add-on creates image nodes and material connections.
5. The artist adjusts scale, offset, rotation, and blend mode.
6. The material can be exported with the model as GLB.

### 6.4 Godot Workflow

1. Artist imports a Pixelcoat material pack into the project.
2. The Godot import plugin reads the manifest.
3. The plugin creates:
   - StandardMaterial3D or ShaderMaterial
   - Texture resources
   - Optional decal material
   - Optional emissive material
4. The artist applies the material to a MeshInstance3D, Decal, Sprite3D, or quad.

---

## 7. Functional Requirements

## 7.1 Image Import

The system must:

- Accept common raster image formats
- Preserve embedded alpha when available
- Detect color profile when possible
- Convert source data into a linear internal representation where required
- Preserve the untouched source file path in the recipe
- Warn when images are extremely low resolution, heavily compressed, or unusually large
- Support drag-and-drop import
- Support clipboard paste as an optional convenience feature

### Acceptance Criteria

- A valid PNG, JPG, WEBP, BMP, or TIFF can be imported.
- The original image is displayed without modification.
- Image width, height, alpha state, and color profile are reported.
- Import failure returns an actionable error message.

---

## 7.2 Crop and Perspective Correction

The system must support:

- Rectangle crop
- Arbitrary quadrilateral crop
- Perspective correction
- Rotation in 90-degree increments
- Fine rotation
- Horizontal and vertical flip
- Safe-area guides
- Automatic content bounds detection

Perspective correction is important for signs, walls, posters, doors, windows, and storefront references photographed at an angle.

### Acceptance Criteria

- The user can identify four corners and produce a rectified rectangular image.
- The corrected image can be regenerated from the saved recipe.
- Crop and correction operations do not modify the source file.

---

## 7.3 Resolution Planning

The artist must be able to define output using either:

- Exact working dimensions
- Longest-side pixel count
- Pixels per meter
- Pixels per texel density target
- Preset resolution classes

Recommended presets:

- Micro decal: 8 to 32 pixels
- Small prop detail: 16 to 64 pixels
- Sign or poster: 32 to 128 pixels
- Wall section: 64 to 256 pixels
- Facade: 128 to 512 pixels
- Background card: 128 to 1024 pixels

The tool should warn when the source detail exceeds what can remain readable at the selected resolution.

### Acceptance Criteria

- The artist can select an exact working resolution.
- Preview updates show the actual pixel grid.
- Export enlargement uses nearest-neighbor scaling only unless explicitly overridden.

---

## 7.4 Image Simplification

Before palette reduction, the system should simplify the source while preserving important structure.

Required operations:

- Bilateral or edge-preserving smoothing
- Noise reduction
- Local contrast control
- Shadow and highlight compression
- Value-band grouping
- Edge-aware downsampling
- Small-island removal
- Shape closing and opening
- Material-boundary preservation

The artist must be able to tune the strength of each stage.

### Protected Detail Mask

The artist can paint or generate a mask identifying regions where detail should be preserved.

Examples:

- Lettering
- Face-like motifs in posters
- Door handles
- Window frames
- Cracks
- Logos
- High-contrast signs

### Suppression Mask

The artist can mark regions where detail should be removed.

Examples:

- Camera noise
- Foliage clutter
- Compression artifacts
- Repetitive brick noise
- Background objects

---

## 7.5 Palette Generation and Management

Pixelcoat must support:

- Automatic palette extraction
- Fixed palette import
- Shared project palette
- Per-material palette
- Palette locking
- Palette remapping
- Color merging
- Manual color editing
- Ordered palette ramps
- Light, midtone, shadow, and accent designation

Supported palette sources:

- GPL palette files
- PNG palette strips
- JSON palette definitions
- Hex code lists
- Existing image palettes

### Automatic Palette Methods

At minimum:

- Median cut
- K-means clustering
- NeuQuant or equivalent
- Perceptual clustering in LAB or OKLab color space

### Palette Constraints

The user can define:

- Maximum total colors
- Maximum colors per tile
- Maximum colors per material group
- Reserved colors
- Forbidden colors
- Minimum perceptual distance between colors

### Acceptance Criteria

- The user can produce an output with a fixed maximum color count.
- Locked colors remain unchanged during regeneration.
- Imported palettes can be reused across multiple assets.
- Color reduction is calculated in a perceptual color space.

---

## 7.6 Value Grouping

Pixelcoat must provide explicit control over value structure.

The system should allow:

- Two-tone, three-tone, four-tone, and custom-band modes
- Separate value grouping from hue grouping
- Shadow, midtone, and highlight bias
- Black-point and white-point adjustment
- Silhouette preservation
- Local contrast preservation
- Material-aware contrast

This feature should help an environment asset remain readable at a distance.

### Acceptance Criteria

- A grayscale preview can display the final value grouping.
- The artist can restrict an output to a chosen number of value bands.
- Important edges remain visible after value reduction when edge preservation is enabled.

---

## 7.7 Edge Treatment

The system must identify and stylize edges.

Edge modes:

- No explicit edge treatment
- Preserve source edges
- Darken boundaries
- Lighten boundaries
- Palette-outline edges
- Selective silhouette outline
- Material boundary outline
- Broken pixel clusters

Controls:

- Edge threshold
- Edge thickness
- Edge color rule
- Edge continuity
- Minimum edge length
- Interior-edge suppression
- Text-edge protection

The system should avoid outlining every photographic detail because this creates visual noise.

---

## 7.8 Dithering

Required dithering options:

- None
- Bayer ordered dithering
- Blue-noise dithering
- Floyd-Steinberg
- Atkinson
- Sierra Lite
- Custom pattern import
- Clustered-dot patterns

Controls:

- Strength
- Scale
- Direction
- Region mask
- Color-pair selection
- Shadow-only dithering
- Highlight-only dithering
- Material-specific dithering

Dithering must be aligned to the working pixel grid and remain stable between regenerations.

### Acceptance Criteria

- The same seed and settings produce identical dither patterns.
- Dithering can be limited to selected value ranges.
- Dithering does not introduce colors outside the active palette.

---

## 7.9 Pixel Cluster Cleanup

The system should detect poor pixel-art artifacts and offer automatic cleanup.

Detection targets:

- Single-pixel noise
- Isolated color islands
- Jagged diagonals
- Accidental stair-step patterns
- Inconsistent line thickness
- Tiny holes
- Repetitive checkerboard noise
- Unreadable letter fragments

Cleanup modes:

- Conservative
- Balanced
- Aggressive
- Manual review only

A before-and-after difference preview must be available.

---

## 7.10 Text and Sign Preservation

For signs, posters, labels, and storefronts, the artist may need readable text.

Pixelcoat should provide:

- Text-region detection
- Contrast enhancement for text regions
- Manual protected regions
- Optional replacement of detected text with manually entered text
- Pixel-font rendering
- Alignment and spacing controls
- Separate text palette

Automatic optical character recognition is optional and must not be required for the MVP.

The MVP should prioritize manual text replacement and protected masks rather than unreliable automated recognition.

---

## 7.11 Alpha and Decal Generation

The system must support decal-oriented output.

Alpha sources:

- Existing source alpha
- Color-key removal
- Luminance threshold
- Edge-guided subject extraction
- Manual mask painting
- Polygon selection
- Background flood select

Decal output controls:

- Alpha cutoff
- Edge feathering in source space
- Pixel-hard alpha mode
- Dilation padding
- Transparent RGB cleanup
- Premultiplied or straight alpha
- Border extrusion

### Acceptance Criteria

- A transparent PNG can be exported with clean edges.
- Transparent pixels do not contain obvious color fringes.
- Padding can be added for mipmapping and atlas packing.

---

## 7.12 Seamless Texture Assistance

For repeating wall, floor, roof, and material textures, Pixelcoat should provide:

- Offset preview
- Wraparound painting
- Edge blending
- Patch-based seam correction
- Mirrored-edge option
- Tile preview grid
- Repetition-frequency warnings
- Randomized variation export

The system should not promise perfect automatic tiling for all images. It should provide assistance and clear visual validation.

### Variation Set

The artist can export multiple compatible variants:

- Base
- Darker
- Lighter
- Dirtier
- Damaged
- Wet
- Emissive

Each variant must retain aligned UV boundaries.

---

## 7.13 Material Map Generation

Pixelcoat should generate optional supporting maps for environment materials.

### Albedo

The primary pixel-art color output.

### Normal

Generated from height or edge structure. The user can control strength and smoothing.

### Roughness

Generated using luminance, material classification, or a manual mask.

### Metallic

Generated only when explicitly enabled or painted through a mask.

### Height

Generated from value groups, edges, or a manually authored mask.

### Emissive

Generated from selected palette colors, luminance range, or manual mask.

### Opacity

Generated for decals, fences, foliage cards, signs, and layered surfaces.

### Cavity or Grime Mask

Generated from local contrast, edges, or a user mask.

Every generated map must remain pixel aligned with the albedo.

---

## 7.14 Material Presets

Recommended built-in presets:

- Painted brick
- Raw brick
- Concrete
- Asphalt
- Tile
- Wood plank
- Painted metal
- Rusted metal
- Glass window
- Emissive window
- Neon sign
- Paper poster
- Vinyl sign
- Graffiti
- Grime overlay
- Cracks and damage
- Storefront facade
- Distant skyline
- Foliage card

Each preset may adjust:

- Smoothing
- Palette size
- Edge treatment
- Dither method
- Contrast
- Tiling assistance
- Roughness generation
- Normal generation
- Alpha behavior

---

## 7.15 Atlas and Trim-Sheet Generation

Pixelcoat should allow compatible outputs to be packed into:

- Decal atlas
- Sign atlas
- Window atlas
- Grime atlas
- Trim sheet
- Material swatch sheet

Packing requirements:

- Configurable padding
- Power-of-two output option
- Rotation toggle
- Grouping by material type
- Grouping by color space
- Grouping by resolution class
- Stable deterministic packing
- Atlas manifest with UV rectangles

### Atlas Manifest Example

```json
{
  "schema_version": "0.1",
  "atlas": "city_decals_01.png",
  "width": 1024,
  "height": 1024,
  "entries": [
    {
      "id": "poster_no_parking",
      "rect_px": [16, 16, 128, 192],
      "uv": [0.015625, 0.015625, 0.125, 0.1875],
      "pivot": [0.5, 0.5],
      "alpha_mode": "cutout"
    }
  ]
}
```

---

## 7.16 3D Surface Preview

The desktop application should include a lightweight preview scene.

Preview geometry:

- Plane
- Cube
- Cylinder
- Wall corner
- Floor and wall intersection
- Simple storefront
- User-supplied GLB

Preview controls:

- UV scale
- Offset
- Rotation
- Wrap mode
- Filtering mode
- Alpha cutoff
- Normal strength
- Roughness
- Emission
- Lighting direction
- Camera distance
- Pixel snapping preview

The 3D preview is not a replacement for Blender or Godot. It exists to catch obvious projection, scale, tiling, and readability problems before export.

---

## 8. Output Types

## 8.1 Surface Texture Pack

```text
asset_name/
  asset_name_albedo.png
  asset_name_normal.png
  asset_name_roughness.png
  asset_name_height.png
  asset_name_emissive.png
  asset_name_mask.png
  asset_name.pixelcoat.json
  asset_name_preview.png
```

## 8.2 Decal Pack

```text
asset_name/
  asset_name_decal.png
  asset_name_normal.png
  asset_name_roughness.png
  asset_name.pixelcoat.json
  asset_name_preview.png
```

## 8.3 Atlas Pack

```text
atlas_name/
  atlas_name_albedo.png
  atlas_name_normal.png
  atlas_name_roughness.png
  atlas_name_atlas.json
  atlas_name_preview.png
```

## 8.4 Blender Pack

```text
asset_name/
  textures/
  asset_name.pixelcoat.json
  asset_name_blender.py
```

The optional Python file can reconstruct the material inside Blender.

## 8.5 Godot Pack

```text
asset_name/
  textures/
  asset_name.pixelcoat.json
  asset_name.tres
  asset_name_preview.png
```

---

## 9. Recipe Format

Every processed asset must include a recipe.

### Example Recipe

```json
{
  "schema_version": "0.1",
  "tool_version": "0.1.0",
  "asset_id": "south_street_storefront_01",
  "source": {
    "path": "sources/south_street_storefront.jpg",
    "sha256": "SOURCE_HASH",
    "color_space": "sRGB"
  },
  "transform": {
    "crop": [104, 36, 1420, 1024],
    "perspective_quad": [
      [122, 64],
      [1375, 95],
      [1344, 998],
      [151, 976]
    ],
    "rotation_degrees": 0
  },
  "pixel": {
    "working_width": 256,
    "working_height": 128,
    "display_scale": 4,
    "downsample_method": "edge_aware"
  },
  "simplification": {
    "edge_preserving_smoothing": 0.45,
    "noise_reduction": 0.3,
    "value_bands": 5,
    "small_island_threshold": 3
  },
  "palette": {
    "method": "oklab_kmeans",
    "max_colors": 24,
    "locked_palette": "palettes/night_city_24.json"
  },
  "edges": {
    "mode": "material_boundary",
    "threshold": 0.42,
    "thickness": 1
  },
  "dither": {
    "method": "blue_noise",
    "strength": 0.18,
    "seed": 41027
  },
  "tiling": {
    "enabled": false
  },
  "maps": {
    "normal": true,
    "roughness": true,
    "height": false,
    "emissive": true
  },
  "export": {
    "type": "surface_texture",
    "format": "png",
    "nearest_neighbor_upscale": true,
    "padding": 8
  }
}
```

---

## 10. Proposed Architecture

Pixelcoat should use a layered architecture so the image-processing engine can operate independently from the GUI and integrations.

```text
pixelcoat/
  core/
    image_io/
    transforms/
    analysis/
    simplification/
    quantization/
    dithering/
    edge_processing/
    masks/
    tiling/
    map_generation/
    atlas/
    export/
  profiles/
  recipes/
  cli/
  desktop/
  integrations/
    blender/
    godot/
  tests/
  examples/
```

### 10.1 Core Engine

Responsibilities:

- Load images
- Apply deterministic processing graph
- Generate maps
- Export artifacts
- Validate recipes
- Report errors and metrics

The core engine must not depend on the desktop GUI.

### 10.2 Processing Graph

Each recipe compiles into a sequence of processing nodes.

Example:

```text
Load
  -> Color Normalize
  -> Crop
  -> Perspective Correct
  -> Edge-Preserving Simplify
  -> Downsample
  -> Value Group
  -> Palette Quantize
  -> Edge Stylize
  -> Dither
  -> Cluster Cleanup
  -> Generate Maps
  -> Pad
  -> Export
```

Nodes should support caching so adjusting a late-stage parameter does not rerun every earlier stage.

### 10.3 Desktop Application

Recommended framework options:

1. **Python + PySide6**
   - Fastest path to an offline desktop tool
   - Strong image-processing ecosystem
   - Easy Blender-adjacent scripting

2. **Rust + Tauri**
   - Better packaging and performance
   - More engineering cost

3. **C++ + Qt**
   - Maximum control
   - Highest implementation cost

### Recommendation

Use Python 3.12 with PySide6 for the MVP. Keep the core processing interfaces modular so performance-critical stages can later move to Rust, C++, or GPU compute.

---

## 11. Recommended Technical Stack

### Core

- Python 3.12
- NumPy
- Pillow
- OpenCV
- scikit-image
- colour-science or custom OKLab conversion
- Pydantic for recipe validation
- Click or Typer for CLI

### Desktop GUI

- PySide6
- OpenGL or Vulkan-backed viewport through Qt where practical
- Optional pyglet, moderngl, or Qt3D for 3D preview

### Packaging

- PyInstaller for early builds
- Nuitka as an optional optimized packaging path

### Testing

- pytest
- Hypothesis for image-processing property tests
- Golden-image comparison tests

### Optional Acceleration

- Numba
- OpenCL
- Vulkan compute
- Rust extension modules through PyO3

---

## 12. Core Algorithms

## 12.1 Edge-Aware Downsampling

Standard image reduction averages neighboring pixels and often destroys the structural lines that environment art needs.

Pixelcoat should use an edge-aware method:

1. Detect strong luminance and chroma edges.
2. Build an edge-confidence map.
3. Reduce flat regions aggressively.
4. Preserve high-confidence boundaries.
5. Snap the result to the target pixel grid.
6. Resolve conflicting samples using perceptual importance.

Importance score may consider:

- Local contrast
- Edge strength
- Saturation
- Protected-detail mask
- Distance from image center
- User-defined focal mask

---

## 12.2 Palette Quantization

Recommended pipeline:

1. Convert source pixels to OKLab.
2. Exclude fully transparent pixels.
3. Weight protected regions more heavily.
4. Cluster colors.
5. Merge clusters below a minimum perceptual distance.
6. Map clusters to locked or project colors where required.
7. Reconstruct RGB output.
8. Apply optional dithering.

---

## 12.3 Pixel Cluster Scoring

Each connected color region can receive a quality score based on:

- Area
- Perimeter-to-area ratio
- Number of one-pixel protrusions
- Diagonal consistency
- Color contrast with neighbors
- Whether the cluster intersects a protected region

Low-quality clusters may be merged into the most perceptually similar neighboring region.

---

## 12.4 Height and Normal Generation

Height generation sources:

- Luminance
- Value bands
- Edge distance field
- User-painted mask
- Material preset rules

Normal generation process:

1. Generate or load height.
2. Apply pixel-preserving blur if enabled.
3. Compute Sobel or Scharr gradients.
4. Normalize into tangent-space normal values.
5. Preserve exact map dimensions.
6. Optionally quantize normal directions for a stylized response.

---

## 12.5 Seam Assistance

Suggested MVP method:

1. Offset image by 50 percent horizontally and vertically.
2. Place seams in the center.
3. Offer clone, patch, and blend operations.
4. Re-run palette enforcement after repair.
5. Validate tile edges pixel by pixel.

Automatic patch matching can be introduced after the manual workflow is reliable.

---

## 13. User Interface

## 13.1 Main Layout

```text
+---------------------------------------------------------------+
| Menu | Project | Profile | Batch | Export                     |
+----------------------+----------------------+-----------------+
| Source and Masks     | 2D Pixel Preview     | Settings        |
|                      |                      |                 |
| Crop                  | Before / After       | Resolution      |
| Perspective           | Pixel Grid           | Palette         |
| Protected Mask        | Tiling Preview       | Edges           |
| Suppression Mask      | Map Preview          | Dither          |
| Alpha Mask            |                      | Cleanup         |
+----------------------+----------------------+-----------------+
| Timeline / Processing Graph / Errors / Performance            |
+---------------------------------------------------------------+
```

### 13.2 Preview Modes

- Original
- Corrected source
- Simplified source
- Value groups
- Palette result
- Edge map
- Dither result
- Alpha
- Normal
- Roughness
- Emissive
- Tiling grid
- 3D surface preview
- Difference comparison

### 13.3 Essential UX Rules

- Every slider must expose a numeric value.
- Every operation must be undoable.
- Regeneration must show progress.
- Warnings must explain how to fix the problem.
- Preview zoom must include nearest-neighbor display.
- The artist must be able to inspect individual pixels.
- Preset changes must not erase manual masks.

---

## 14. Command-Line Interface

### Single Image

```bash
pixelcoat process storefront.jpg \
  --profile profiles/night_city.json \
  --width 256 \
  --height 128 \
  --output build/storefront
```

### Existing Recipe

```bash
pixelcoat build recipes/storefront.pixelcoat.json
```

### Batch Folder

```bash
pixelcoat batch sources/signs \
  --profile profiles/signs_32.json \
  --output build/signs
```

### Atlas

```bash
pixelcoat atlas build/signs \
  --size 1024 \
  --padding 8 \
  --output build/sign_atlas
```

### Validation

```bash
pixelcoat validate recipes/
```

### CLI Requirements

- Non-zero exit code on failure
- Machine-readable JSON log option
- Human-readable log option
- Deterministic seed support
- Continue-on-error mode for batches
- Dry-run mode
- Overwrite protection

---

## 15. Blender Integration

The Blender add-on should focus on applying Pixelcoat outputs rather than recreating the full editor.

### Blender Add-On Features

- Import material pack
- Create material nodes
- Configure nearest-neighbor filtering
- Configure alpha blend or clip mode
- Add decal plane aligned to selected face
- Project image from current camera view
- Bake Pixelcoat output into an existing texture set
- Apply atlas UV rectangle
- Set pixel density helper
- Export GLB with compatible material settings

### Recommended Blender Material Behavior

- Albedo uses nearest interpolation.
- Normal maps use non-color data.
- Roughness uses non-color data.
- Emissive texture can share the albedo palette or use a dedicated map.
- Texture coordinates can be UV, generated, or object projected.

### Blender Add-On Non-Goals

- Full UV editing
- Full image stylization controls
- Replacing Blender texture painting
- Managing the entire GLB export pipeline

---

## 16. Godot 4.7 Integration

Pixelcoat should include an EditorImportPlugin or companion editor plugin.

### Supported Targets

- StandardMaterial3D
- ShaderMaterial
- Decal
- Sprite3D
- MeshInstance3D
- CSG surfaces during prototyping

### Import Rules

- Disable texture filtering by default for strict pixel art.
- Disable mipmaps for small decals when appropriate.
- Allow mipmaps for large environment textures where distance shimmer would otherwise occur.
- Support alpha scissor for hard-edged decals.
- Support alpha blend for soft grime and atmospheric overlays.
- Set color space correctly for each map.
- Preserve source dimensions.

### Optional Pixelcoat Shader

A shared Godot shader may support:

- Pixel snapping
- Palette lookup
- Distance-based pixel density
- Dithered fade
- Emissive pulse
- UV scaling
- Atlas selection
- Grime blending
- Secondary tint

### Example Godot Manifest Fields

```json
{
  "godot": {
    "material_type": "StandardMaterial3D",
    "texture_filter": "nearest",
    "mipmaps": true,
    "alpha_mode": "scissor",
    "alpha_scissor_threshold": 0.5,
    "uv_scale": [1.0, 1.0],
    "normal_strength": 0.65,
    "emission_energy_multiplier": 1.8
  }
}
```

---

## 17. Performance Requirements

### MVP Targets

On a modern desktop CPU:

- 1024 x 1024 source to 128 x 128 output preview in under 1 second for common recipes
- 4096 x 4096 source to 512 x 512 output in under 5 seconds for common recipes
- Preview response under 250 milliseconds for late-stage adjustments when cached
- Batch processing of 100 small decals without memory growth beyond defined limits

### Memory

- Streaming or tiled processing should be used for unusually large images.
- Cached intermediate images must have configurable limits.
- The application must expose cache clearing.

---

## 18. Error Handling

The system must detect and explain:

- Unsupported image format
- Corrupt file
- Missing source file
- Invalid recipe schema
- Missing palette
- Unwritable output folder
- Insufficient memory
- Atlas overflow
- Invalid crop area
- Degenerate perspective quad
- Fully transparent result
- Palette smaller than required locked colors
- Export map size mismatch

Errors must include:

- What failed
- Which asset failed
- Which stage failed
- Suggested correction
- Whether batch processing continued

---

## 19. Logging and Diagnostics

Each build may produce:

```text
build_report.json
build_log.txt
```

Recommended report fields:

- Tool version
- Recipe version
- Source hash
- Processing duration by stage
- Input and output dimensions
- Final color count
- Final value-band count
- Alpha coverage
- Edge density
- Tile-seam score
- Warnings
- Exported file hashes

---

## 20. Testing Strategy

## 20.1 Unit Tests

- Color conversion
- Palette quantization
- Dither determinism
- Crop and perspective transforms
- Alpha extraction
- Padding
- Atlas UV generation
- Recipe validation
- Output naming

## 20.2 Golden Image Tests

A controlled set of inputs should be processed and compared against approved outputs.

Test categories:

- Signs
- Brick
- Concrete
- Windows
- Posters
- Graffiti
- Transparent decals
- Tiling materials
- Emissive panels
- Storefronts

Image comparison should allow small defined tolerances where platform-dependent math may differ.

## 20.3 Property Tests

Examples:

- Output dimensions always match the recipe.
- Output colors never exceed the palette limit.
- Dither output never uses colors outside the palette.
- All generated maps have identical dimensions.
- Transparent output remains transparent after padding.
- Same recipe and source hash produce the same output hash.

## 20.4 Integration Tests

- Blender material creation
- Godot material import
- GLB export with textures
- Atlas import and UV lookup
- Batch continue-on-error behavior

---

## 21. Security and Privacy

Pixelcoat is designed to run offline.

Requirements:

- No automatic image upload
- No telemetry by default
- No source-image collection
- No network dependency for processing
- Optional update checks must be clearly disclosed and disableable
- Recipe files should use relative paths where practical
- External scripts must never be executed from untrusted recipes

---

## 22. MVP Definition

The MVP should prove that Pixelcoat can turn ordinary source images into useful environment-art textures that can be applied in Blender and Godot 4.7.

### MVP Features

1. Image import
2. Crop and perspective correction
3. Working-resolution controls
4. Edge-aware simplification
5. Palette extraction and fixed palette support
6. Value grouping
7. Four dithering methods
8. Protected-detail mask
9. Alpha and decal output
10. Albedo, normal, roughness, and emissive maps
11. Recipe save and reload
12. PNG export
13. Folder batch processing
14. Blender material importer
15. Godot material importer
16. Plane, cube, and wall-corner preview

### MVP Acceptance Criteria

- An artist can import a storefront photograph and export a stylized pixel-art facade texture.
- An artist can import a poster image and export a transparent or rectangular decal.
- An artist can import a wall material and produce a visibly seamless repeating texture with manual seam assistance.
- A saved recipe reproduces the same output from the same source.
- A folder of at least 50 images can be processed without manual intervention.
- Blender can import the output and create a correctly connected material.
- Godot 4.7 can import the output and create a usable material resource.
- Output textures remain pixel aligned across all generated maps.
- The artist can use a shared palette across multiple images.

---

## 23. Post-MVP Roadmap

### Phase 2: Environment Production Features

- Atlas and trim-sheet builder
- Seam automation
- Material variation generator
- Custom processing graph editor
- User-supplied GLB preview
- Texture bake helper
- Pixel-font sign editor
- Project-wide palette audit

### Phase 3: Advanced Stylization

- Semantic region assistance without cloud dependency
- Material classification
- Perspective-aware facade segmentation
- Depth-assisted normal generation
- Multi-angle source blending
- Palette harmonization across a full level
- Camera-distance readability scoring

### Phase 4: Pipeline Automation

- Watch folders
- Headless build server support
- Git-friendly asset manifests
- Godot automatic reimport
- Blender batch material assignment
- Integration with Deli Counter, Patina, Zoo, Lux, and Dispatch

---

## 24. Integration With the Existing World-Building Pipeline

Pixelcoat can act as the 2D surface-authoring companion to the broader environment pipeline.

### Zoo

Zoo creates or assembles the base 3D asset. Pixelcoat creates stylized surface art, labels, wear, signs, and material treatments for that asset.

### Deli Counter

Deli Counter creates greybox spaces. Pixelcoat can generate temporary or final wall, floor, sign, and facade textures for those spaces.

### Patina

Patina applies a broader visual pass to geometry and materials. Pixelcoat can provide the image-derived texture assets used by that pass.

### Lux

Lux controls lighting and final visual response. Pixelcoat emissive masks, value grouping, and palette choices should be testable under Lux lighting profiles.

### Dispatch

Dispatch can validate that required texture packs, atlases, decals, and material manifests are present in a mission build.

### Suggested Contract

```text
Pixelcoat Input:
  source image
  style profile
  intended surface type
  physical dimensions or texel density

Pixelcoat Output:
  texture maps
  material manifest
  atlas metadata when applicable
  preview image
  deterministic recipe
```

---

## 25. Key Risks and Mitigations

### Risk: Outputs Look Like Cheap Photo Filters

**Mitigation:** Prioritize value grouping, palette control, protected details, edge processing, and cluster cleanup rather than relying on resizing and dithering alone.

### Risk: Too Many Controls Overwhelm Artists

**Mitigation:** Lead with material presets and task-oriented output types. Place advanced controls behind expandable panels.

### Risk: Pixel Art Shimmers at Distance

**Mitigation:** Support mipmaps, distance-aware material settings, texture padding, and Godot shader options.

### Risk: Text Becomes Unreadable

**Mitigation:** Add protected masks, manual text replacement, and dedicated sign presets.

### Risk: Generated Normal Maps Look Noisy

**Mitigation:** Generate normals from simplified height information, not directly from photographic noise.

### Risk: Tiled Textures Reveal Repetition

**Mitigation:** Provide tile previews, variation sets, seam scoring, and atlas-based alternates.

### Risk: Blender and Godot Interpret Materials Differently

**Mitigation:** Use explicit map metadata, shared validation scenes, and integration tests.

### Risk: Large Images Make Preview Slow

**Mitigation:** Cache stages, use proxy images for previews, and reserve full-resolution processing for export.

---

## 26. Open Technical Decisions

1. Whether the MVP desktop app should use PySide6 or a Godot-based editor shell.
2. Whether the 3D preview should use Qt3D, moderngl, or an embedded Godot viewport.
3. Whether material maps should remain full-color or optionally use packed channel textures.
4. Whether automatic text detection belongs in the MVP.
5. Whether project palettes should be centralized in a dedicated palette library.
6. Whether Blender baking should be included in the first public release.
7. Whether Pixelcoat should directly modify existing texture files or always export separate layers.

### Recommendation

For the first implementation:

- Use Python and PySide6.
- Export separate, non-destructive layers.
- Treat Blender baking as post-MVP.
- Use an embedded lightweight OpenGL preview.
- Keep text handling manual and mask-driven.
- Support central project palettes from the beginning.

---

## 27. Definition of Done

Pixelcoat v1.0 is complete when an environment artist can consistently:

1. Import a source image.
2. Correct its crop and perspective.
3. Convert it into intentional pixel art using a controlled palette.
4. Preserve or remove specific details.
5. Generate the texture maps needed for a 3D surface.
6. Preview the result on representative geometry.
7. Export the result with a reproducible recipe.
8. Apply it in Blender.
9. Import and use it in Godot 4.7.
10. Batch the same process across a folder of environment images.

The output should feel authored, reusable, and appropriate for a cohesive stylized 3D world rather than like a photograph that was merely reduced in resolution.

---

## 28. Final Product Statement

Pixelcoat turns source images into controlled pixel-art surface treatments for 3D worlds.

It exists to help environment artists move quickly from reference imagery to projection-ready textures, decals, signs, materials, and facade details without sacrificing palette discipline, readability, or visual cohesion.
