# Material Coverage Map (buildings & props)

Living map of the tiling-material vocabulary for the FPS art pass: what
Pixelcoat authors, and where the **Zoo kind** dependency sits. Pixelcoat can
author any surface; Zoo only *resolves* a fixed kind list, so new surfaces need
a one-line Zoo addition **and** a species that requests the kind.

## Covered today (Pixelcoat grammars in `profiles/materials/`)

| Surface | Grammar id | Zoo kind | Kind status |
|---|---|---|---|
| Painted metal | `painted_metal_industrial` | metal | ✅ existing |
| Brass / chrome / galvanized / painted / rusted / corrugated / traffic-signal | `metal_*`, `corrugated_metal_delco` | metal | ✅ existing |
| Concrete (interior / board-form / polished / sidewalk / asphalt) | `concrete_*`, `asphalt_street` | concrete | ✅ existing |
| Marble | `marble_bank_floor` | concrete¹ | ✅ resolves as concrete |
| Plaster | `plaster_delco` | plaster | ✅ existing |
| Wood | `wood_delco` | wood | ✅ existing |
| Plastic | `plastic_delco` | plastic | ✅ existing |
| Glass | `glass_delco` | glass | ✅ existing |
| Leather | `leather_delco` | leather | ✅ existing |
| Canvas | `canvas_delco` | canvas | ✅ existing |
| Rubber | `rubber_delco` | rubber | ✅ existing |
| **Brick** | `brick_delco` | **brick** | 🟡 registered — pending cert |
| **Ceramic tile** | `tile_delco` | **tile** | 🟡 registered — pending cert |
| **Drywall / painted wall** | `drywall_delco` | **drywall** | 🟡 registered — pending cert |
| **Acoustic ceiling tile** | `ceiling_tile_delco` | **ceiling_tile** | 🟡 registered — pending cert |
| **Carpet** | `carpet_delco` | **carpet** | 🟡 registered — pending cert |
| **Dirt / ground** | `dirt_delco` | **dirt** | 🟡 registered — pending cert |

¹ `marble` isn't a Zoo kind; it's authored as `concrete` so it resolves. A
dedicated `marble`/`stone` kind is optional (same one-line addition below).

🟡 **Step 1 has been applied** — the six kinds are now in Zoo's `KNOWN_KINDS`
(`core/skins.py`) and `ROUGHNESS` (`bpylayer/materials.py`), and Pixelcoat's
`_ZOO_KINDS` guardrail matches, so `skins-library` no longer warns. This is
**not yet certified**: run Zoo's suite (`python -m pytest tests`, expect 199
green) and re-certify the factory set before relying on it. **Step 2 (species
requesting the kinds) is still open** — see below.

## The Zoo dependency — two steps

Registering a kind is a **Zoo repo** change, so it goes through Zoo's tests +
factory re-certification, not a silent edit from here.

**Step 1 — register the kinds (one line each, additive).**

`zoo/zoo_keeper/core/skins.py` — extend `KNOWN_KINDS`:

```python
KNOWN_KINDS = ("laminate", "wood", "metal", "plastic", "leather", "rubber",
               "canvas", "carbon", "glass", "paper", "concrete", "plaster",
               "brick", "tile", "drywall", "ceiling_tile", "carpet", "dirt")
```

`zoo/zoo_keeper/bpylayer/materials.py` — add roughness defaults (used for any
socket a pack doesn't texture):

```python
ROUGHNESS = {..., "brick": 0.90, "tile": 0.35, "drywall": 0.90,
             "ceiling_tile": 0.92, "carpet": 0.98, "dirt": 0.97}
```

(No `METALLIC` change — none of these are metal.) Then run Zoo's suite
(`python -m pytest tests`, 199 green) and re-certify the factory set.

**Step 2 — species request the kinds.** A pack is only *applied* when a Zoo
species asks for that `material_kind`. In `recipes/_arch.py::build_slab` the kind
is `plan["material"]`, which comes straight from the chosen **style's `material`
field** in the genome — so enabling a wall to be brick is a pure genome edit
(no recipe/bpy change), exactly how the desk's `1970s` style sets `wood`.

**Done (genome-only, this pass):** the whole wall family — `wall`, `wallEnd`,
`doorway`, `window`, `breach` — now offers `brick` / `tiled` / `drywall` styles
(added to `materials.options` + a style per kind). Building any of them with
`style=brick` + `theme=delco` sets `material=brick`, which the skin resolver
maps to the `brick_delco` pack. *Which* style a slot uses is chosen by the
Deli-Counter slot / kit at build time — that authoring step is what actually
puts brick on a given wall.

**Remaining — floor / ceiling / ground (`carpet`, `dirt`, `ceiling_tile`, tiled
floors).** These are **not** wall-family: `build_slab` makes a *vertical* slab,
and Zoo has no floor/ceiling/ground module. Two options, both bigger than a
genome edit: (a) Deli Counter assigns the material on its own floor/ceiling
shell geometry (a DC concern), or (b) add a new Zoo horizontal-slab species
(`floor` / `ceiling` / `ground`) — a small **bpy recipe** (a horizontal slab,
pivot per the coordinate contract), which needs Blender to build and validate
and so is **not** done here. Spec, not shipped.

**Cert:** the genome edits are data-only (low risk); run Zoo's suite (esp.
`test_genome`, `test_meta_validate`, `test_arch`, `test_structural_species`) and
re-certify before relying on them.

When Step 1 lands, update Pixelcoat's `_ZOO_KINDS` guardrail list in
`pixelcoat/cli/main.py` to match, and the warnings clear.

## Still uncovered (future fills, same pattern)

Roofing/shingle, corrugated fiberglass, chain-link/mesh, terrazzo, linoleum,
wet variants (wet concrete/asphalt), snow/gravel, ceiling acoustic variants,
fabric/upholstery. Each is a grammar + (if new) a Zoo kind. Trim/edge detail
(pipes, panels, rivets) is **Patina's** `--trim-sheet`, not a Pixelcoat tiling
material — don't duplicate it here.
