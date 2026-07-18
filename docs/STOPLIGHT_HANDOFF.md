# Stoplight (Traffic Signal) — Pixelcoat parts & Zoo handoff

What Pixelcoat delivers for a pole-mounted traffic signal, and what Zoo still
has to build. Pixelcoat skins surfaces; it does not model — the geometry is a
new Zoo species.

## Material assignment (per part)

| Part | Treatment | Source | UV |
|---|---|---|---|
| Pole / mast arm | galvanized or raw steel, tiling | `metal_galvanized_stadium` (or a painted metal) | world-meter **cube UVs** (Zoo default) — a cylinder tiles with no stretch |
| Signal housing + visors/hoods | weathered dark-green painted enamel, tiling | `metal_painted_trafficsignal` | cube UVs |
| Backplate (hi-vis border) | bright flat albedo or emissive frame | a bright-yellow-green pack, or an emissive decal | authored quad |
| The 3 lenses (R/Y/G) | **emissive decal faces** | `signal-lenses` packs (below) | **authored UV quad per lens**, EXTEND, never tiled |

The pole and housing are ordinary tiling skins — nothing bespoke. The lenses are
the only part that needs placed, per-face art.

## The lens packs (Pixelcoat provides)

Generate with:

```
pixelcoat signal-lenses --out art/zoo/signal_lenses --size 128
```

Produces six emissive decal packs — `lens_{red,yellow,green}_{lit,off}` — each a
`*.pack.json` with `albedo` + `emissive` + `roughness`. The glow lives in the
albedo brightness (Zoo's emissive-face path drives emission from albedo); an
`emissive` map is also written for the tiling import path. `tileable: null`,
`extension: extend`, nearest interpolation — a lens face never tiles.

## Zoo side — the new `traffic_signal` species

Zoo has no traffic-signal species yet (closest existing: `streetlight`,
`sign_box`, `security_camera`). Build one as a Knowledge Pack (genome + recipe),
reusing the established patterns:

1. **Geometry** (`recipes/traffic_signal.py`): vertical `pole` (cylinder),
   optional `mast_arm`, `signal_head` (box), three `visor` hoods, and three thin
   `lens_face` quads recessed in the head; optional `backplate`. Pivot
   **bottom-center on Z=0**, unit scale applied, per `COORDINATE_CONTRACT.md`.
   Collision on (a bounding proxy is fine — the lenses need none).
2. **Material kinds**: tag `pole`/`mast_arm` and `signal_head`/`visor` as
   `metal` so the tiling skin resolves; give each `lens_face` its **own authored
   UV quad** (not the cube projection) so the lens art lands square on the face.
3. **Emissive wiring**: apply the lens packs through the emissive-face path
   (the one `sign_box` uses — `make_emissive_textured_material`, albedo → glTF
   emission). Keep the `_Face` suffix on the lens material names so **Lux's
   emissive binder** finds them.
4. **Which lens is lit = runtime, never baked.** Assign the `_lit` variants and
   let Lux / gameplay drive `emissive_energy` per lens material (0 = dark), or
   swap `_lit`/`_off` packs on state change. Baking one fixed "green is on" state
   into the geometry is the thing to avoid — author all three, the engine
   decides. (Lux emissive energy ~1.0 reads as lit; push past the preset's glow
   threshold for bloom.)

## Determinism / theme

Everything above is deterministic (seed 1999). The tiling metals live in the
theme's `--skins` library (`metal_<theme>/`); the lens packs are per-asset decals
referenced directly by the species, not resolved by kind. One `traffic_signal`
species + these packs = a full skinned signal, rebuildable from source.

## Not in scope for Pixelcoat

The mesh itself (pole, head, visors, lens quads, backplate), its collision, and
the runtime signal-state logic. Those are Zoo (geometry) and Lux/gameplay
(runtime) respectively.
