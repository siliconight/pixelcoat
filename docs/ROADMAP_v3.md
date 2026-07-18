# Pixelcoat Roadmap v3 — where the tool actually is

**Supersedes** `PIXELCOAT_3D_ASSET_SKINNING_ROADMAP_V2.md`. That roadmap was
written with Pixelcoat in isolation and aimed most of its effort (mesh baking,
object-space, mesh-aware weathering, a Skin Job contract, a desktop GUI) at
capabilities the `gabagool_factory` pipeline **already owns**. Read against the
real factory, ~two-thirds of V2 was redundant. This is the corrected plan and
the honest status.

## Pixelcoat's lane (the one-liner)

In the composite the player sees — `Lux_light( albedo_tile × vertex_colour ) × …`
— **Pixelcoat owns the `albedo_tile`**: reusable, neutral, tileable material
packs, plus the placed **emissive focal layer** (signage, screens, lenses).
Everything else is owned elsewhere and Pixelcoat does not duplicate it:

- **Zoo** — geometry, world-meter cube UVs, per-part material kind, vertex wear.
- **Patina** — mesh-aware weathering, AO/grime, banding, cohesion, trim sheets.
- **Lux** — runtime light, colour grade, fog, vignette, bloom.
- **Level Factory** — orchestration + the desktop UI.

The rule that keeps this honest: author *neutral* albedo (never bake the teal
mood in), and flag when we'd ship something the runtime ignores or that another
tool already does.

## Status: shipped

- **Procedural material core** (was V2 T03 / Slice 2) — `procedural_surface.py`
  + `material_grammar.py`. Deterministic, tileable, crisp (posterize + per-texel
  grain + hard-edged features). **28 material grammars** across metal, concrete,
  wood, plastic, glass, plaster, leather, canvas, rubber, brick, tile, drywall,
  ceiling tile, carpet, dirt, corrugated, marble — themed for casino / stadium /
  street / bank / interior.
- **Emissive focal layer** (not in V2 at all) — `decals.py` (traffic-signal
  lenses) and `signage.py` (neon, backlit panels, CRT/LCD screens, hazard
  stripes, arrows) with a built-in 5×7 pixel font. Powered/unpowered variants;
  runtime state stays Lux's.
- **Physical scale** (V2 T15) — `meters_per_tile` through grammar → pack → Zoo
  cube UVs; verified on rendered slabs.
- **UV-island dilation** (V2 T06) — `uv_dilation.py` (exact EDT); a utility,
  less central than V2 assumed since the pipeline tiles via cube UVs.
- **CLI** — `proc-pack`, `skins-library`, `signal-lenses`, `sign`, with an
  unknown-kind guardrail.
- **Cross-tool integration (executed, not just specced):** registered 6 new Zoo
  kinds (brick/tile/drywall/ceiling_tile/carpet/dirt); added brick/tile/drywall
  styles to the wall family; authored new Zoo `floor`/`ceiling` species; proved
  a new surface **material → kind → species → skinned Blender render** end to end.
- **Determinism** — seed 1999, byte-identical output; **147 tests green.**

## Retired from V2 (owned by the factory, not us)

| V2 item | Owned by |
|---|---|
| T01/T02 Blender mesh bake, object-space/triplanar | Zoo world-meter cube UVs |
| T04/T05 + Slice 3 mesh-aware weathering | Patina |
| T10/T14 + Slice 5 round-trip material-region / UV round trip | Zoo / Deli Counter slots |
| Slice 1 Skin Job contract + Blender exporter | existing `slots.json` / `.pack.json` |
| Slice 4 Generation 6 pipeline | Lux (runtime look) |
| Slice 8 Desktop UI | Level Factory |

## Next (the real forward list)

Not from V2 — this is what actually moves Pixelcoat now:

1. **Widen materials & colorways** — more kinds and per-theme variants; the
   generator is the cheap part, so lean on it.
2. **Expand the focal layer** — more signage presets (pictograms, wayfinding,
   price/odds boards, marquees), animated screen frames.
3. **Scale/quality tuning** — e.g. coarsen the acoustic-ceiling grid; sharpen
   marble veins; per-material passes as the eye finds them.
4. **Cross-tool bookkeeping** — the Zoo changes committed this cycle (kinds, wall
   genomes, floor/ceiling species) are **not yet certified**: run Zoo's suite
   (`python -m pytest tests`) and re-certify the factory set before relying on
   them. Same for any pixelcoat VERSION bump / tag per the two-layer release flow.
5. **Compose a room** — wire floor + walls + ceiling through a Deli Counter slot
   build to see the materials together rather than as isolated slabs.

## Non-goals (unchanged, worth restating)

Pixelcoat does not model geometry, bake meshes, weather surfaces on the mesh,
light scenes, or own a GUI. It authors neutral tiling albedo + emissive decals,
deterministically, and hands them to Zoo/Patina/Lux.
