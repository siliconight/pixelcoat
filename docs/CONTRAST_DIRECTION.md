# Controlled Contrast — how it lands in Patina / Pixelcoat / Zoo

Measured against the shipped library on 2026-08-05 with
`pixelcoat/tools/art_standard_audit.py` (51 grammars, 9 themes, synthesized at
256px, seed 1999). Every number below is from that run, not from reading the
grammar JSON — the layer stack moves a material a long way from its stated
palette.

---

## 1. What the measurement actually says

**Our failure mode is not the one the standard leads with.**

§23's headline failure is "Everything Is Saturated". We are not that. Oklab
chroma across the 38 environment-tier grammars:

```
min 0.006   p25 0.011   p50 0.023   p75 0.049   p90 0.074   max 0.109
```

A saturated sRGB primary sits at 0.21–0.31. Our median wall is at **0.023** —
essentially neutral. Six grammars exceed the 0.060 budget and the worst
(`metal_brass_casino`, 0.109) is still a third of a primary. Theme rollups run
0.032–0.048. The palette is already restrained; adding a saturation-reduction
pass would be solving a problem we don't have.

**Emissive: zero grammars in the entire library emit.** We pass §8 trivially,
by having never spent the budget at all. That is not a pass — it means the
navigation layer (§2 secondary: "localized emissive strips or signage") has no
mechanism, which is exactly why `Sign_Box_Face` renders as a blank white
rectangle. See §4.3.

So the three real findings are elsewhere.

### 1.1 We spend peak luminance on floors and ceilings — §5, §19

§19: *"Do not use pure black cavities [or] pure white edge wear."*
§5: *"The brightest white in the scene should normally belong to energy, an
objective, a critical gameplay state."*

Fraction of pixels above Oklab L .94:

```
subway_tile_white     tile          44.7%   rough 0.13
travertine_warm       concrete      14.2%   rough 0.38
stucco_warm           plaster       13.2%   rough 0.81
ceiling_tile_delco    ceiling_tile  12.3%   rough 0.90
brick_painted_white   brick          7.0%   rough 0.67
vct_floor_beige       tile           5.2%   rough 0.34
tile_delco            tile           1.5%   rough 0.29
```

Nothing is crushed — `crushed_frac` is 0.000 across the whole library — so this
is one-sided. `subway_tile_white` puts nearly half its surface at peak white,
and `ceiling_tile_delco` is in **every single theme**, which means every
interior ceiling in every building is competing for the same luminance a muzzle
flash needs. This is the finding with the most direct gameplay cost: it is
§12 figure-ground, and it fires on interiors, where the combat is.

### 1.2 Detail frequency is concentrated in exactly the wrong materials — §10, §11

Edge-density proxy (std of albedo L minus a tiling box blur):

```
brick_glazed_green    brick     hf 0.178   Lrange 0.432
terrazzo              tile      hf 0.145   Lrange 0.362
concrete_delco        concrete  hf 0.119   Lrange 0.290
tile_delco            tile      hf 0.118   Lrange 0.305
brick_delco           brick     hf 0.118   Lrange 0.296
subway_tile_white     tile      hf 0.107   Lrange 0.328
```
distribution: `p25 0.038  p50 0.051  p75 0.074  p90 0.118  max 0.178`

The top of the list is brick and tile — grid materials — at 2–3.5× the median.
§11: *"Environment surfaces near combat spaces should avoid ... repeated panel
lines ... Busy edge patterns behind enemies create visual camouflage."* Brick
and tile are what walls and floors are made of, so the busiest materials we own
are the ones with the largest screen area.

### 1.3 The environment is glossier than the standard's tertiary tier — §7

```
glass_facade_mirror_blue    0.08     subway_tile_white   0.13
glass_facade_bronze         0.10     brick_glazed_green  0.20
glass_facade_spandrel_green 0.12     marble_bank_floor   0.22
```

§7 reserves *"lower roughness, stronger specular highlights"* for focal gameplay
materials. Two readings, and this one is a real direction call rather than a bug:

- The curtain-wall glass at 0.08–0.12 is arguably **correct** — a mirror facade
  is a §2-secondary navigation landmark, and it is the one thing giving the
  rockay family its cohesion. Judged as tertiary it fails; judged as secondary
  it is doing its job.
- `subway_tile_white` at rough 0.13 **and** 44.7% blown is not defensible under
  any tier. A glossy near-white tile is a specular highlight generator at eye
  level indoors.

This is the argument for tiering the budget rather than applying one threshold
by material kind — see §3.1.

---

## 2. The structural gap: there is no quiet tier, anywhere

§18 is the clause we fail hardest, and we fail it three times independently:

**Pixelcoat.** A theme profile is `{kind: grammar_id}` — exactly one grammar per
kind. `build_theme_library` writes one `<kind>_<theme>/` pack per entry, and Zoo
resolves `find_pack(kind, theme)` to that one pack. **There is structurally no
way to have a quiet brick and a hero brick in the same theme.** Every brick wall
in a building wears the same brick by construction.

**Zoo.** `relief_parts` is applied to every non-void wall — plinth, piers every
2.4 m, recessed fields, cap. §18 is explicit: *"Do not make every modular piece
a hero asset. A healthy kit requires visually quiet pieces. Otherwise, assembled
environments become uniformly noisy."* Every wall we ship is a hero asset.

*Correction, verified against `zoo_keeper/core/arch.py` at 17996 bytes:* an
earlier draft of this doc said there is no plain-slab wall module any more.
That is wrong. `relief_parts` has an explicit degenerate path — if
`reveal <= _EPS`, or a bay would be narrower than `min_field`, it returns a
single `("Panel", …)`, which is exactly the quiet module. And `dna.py` already
threads a style block's `relief` into `plan["params"]["relief"]`, which
`relief_parts` merges over its defaults. **A quiet wall tier is one style-block
field away — `relief: {reveal: 0}` — and needs no Zoo code change at all.**
Measured across eight authored wall widths: 56 relief parts collapse to 8 plain
panels, a 7× reduction, with collision untouched (the collider is built from
`slab`, never from `visual`).

**Patina.** Dressing is applied per eligible wall face, not against a budget.
§3's 70/20/10 is a compositional target; a per-face rule cannot express it.

The user's earlier read — *"it looks like a lot of tiles that just cover the
building? Does that help the look or just add another layer of identical
paint?"* — was this clause, arrived at by eye, a week before the standard
existed. The answer is the second one, and it is structural.

---

## 3. What changes, per tool

### 3.1 Pixelcoat — declare the tier, then honour it

**P1. Grammars declare a tier.** Add `"tier"` to the grammar schema, mapping to
§18's four categories: `foundation` (plain walls, floors, ceilings — judged
hard), `functional`, `identity` (landmark silhouettes, faction motifs — looser),
`accent` (hero panels, decals — exempt). This replaces the audit's current
guess-by-kind, and it makes the mirror-facade question answerable in data:
`glass_facade_mirror_blue` declares `identity` and stops failing a budget it was
never meant to meet, while `subway_tile_white` declares `foundation` and its
44.7% blown becomes a hard failure.

**P2. Derive the quiet sibling instead of authoring it.** The measurements that
define "quiet" are the ones the audit already computes, so the inverse operation
is mechanical. Probed on four grammars (contrast compressed to 55%, chroma to
50%):

```
                        blown          Lrange           hf              chroma
ceiling_tile_delco   12.3% -> 0.3%   .157 -> .105   .055 -> .037   .019 -> .009
brick_glazed_green    0.0% -> 0.0%   .432 -> .294   .178 -> .126   .047 -> .025
brick_delco           0.0% -> 0.0%   .296 -> .204   .118 -> .082   .081 -> .040
subway_tile_white    44.7% -> 44.7%  .328 -> .222   .107 -> .075   .007 -> .004
```

Value range, edge density and chroma all move as intended. **`subway_tile_white`
does not budge on `blown_frac`, and that is the useful result** — its median L
is 0.940, i.e. the *centre* of the material is at the blown threshold, not its
tail. Compressing toward the median cannot fix a material whose median is the
problem.

So the transform is two operations, not one: a contrast compression for
materials with a blown tail (`ceiling_tile_delco` p5 .787 / median .859), and a
**median remap** for the ones sitting at the ceiling (`subway_tile_white` p5
.657 / median .940, `travertine_warm` median .906, `stucco_warm` median .873).
The audit already reports both percentiles, so the tool can pick which operation
a given grammar needs rather than applying one blindly.

This is the single highest-leverage change on this list. Nothing else in §18,
§11 or §16 is implementable without it.

**P3. Extend the theme profile with a `quiet` block**, same kinds, and have
`build_theme_library` write `<kind>_<theme>_quiet/`. Zoo grows
`find_pack(kind, theme, tier=)`. Cost: doubles the pack count per theme, not
the kit — the same module can swap its skin.

**P4. Land `tools/art_standard_audit.py` as a gate.** Not as a red-on-main test
of the current 30 offenders — that gets ignored within a week. As a *baseline*:
snapshot today's numbers, fail on regression, and burn the baseline down
deliberately. The `subway_tile_white` and `ceiling_tile_delco` blown highlights
are the two worth fixing first, because they are interior surfaces with the
largest screen area during combat.

### 3.2 Zoo — relief becomes a tier decision, not a universal one

**Z1.** Gate `relief_parts` on the module's tier. The plumbing already exists:
`dna.py` reads `relief` off the style block and threads it into
`plan["params"]["relief"]`, so a style authored without a relief block already
produces a plain slab. DC simply authors one style today. The fix is upstream of
Zoo — it is a DC authoring change, not a Zoo code change, which makes it cheap.

**Z2.** Which walls earn relief is a question we can already answer.
`slots.outward_sign` + `slots.footprint_center` — written this week for the
dressing-direction fix — is exactly the function that decides whether a face
looks out at the street. Street-facing elevations get the piers; rear
elevations and interior partitions get the slab. That is §17's *"richness
through scale, layering, silhouette"* rather than through uniform paneling, and
it reuses code that is already committed and measured.

### 3.3 Patina — dress to a budget, and protect the choke points

**Pa1.** Dressing density becomes a fraction of eligible faces, ranked by
visibility, rather than a per-face rule. §3 is a compositional target and needs
a compositional mechanism.

**Pa2. Quiet zones behind combat — with a known blocker.** §11 and §16 want the
walls behind cover and firing lanes left plain. Patina cannot do that today:
it runs per-building, before Lot places anything on the site, so the firing
lanes do not exist yet. That is an ordering problem, not a missing feature, and
it should be recorded as such rather than half-solved.

What Patina *can* do today without new inputs: leave the interior faces flanking
a doorway undressed. In a CQB map the doorway is the choke point, so it is the
most reliable predictor of where a silhouette will be read, and `openings.py`
already has the geometry. That is the 80% case for free.

**Pa3. Spend the emissive budget on navigation, not decoration.** We have zero
emissive anywhere, and a blank `Sign_Box_Face`. §8's priority order puts
navigation fourth but decoration fifth — so the first emissive material we ever
ship should be signage, and it should be brighter than anything else in the
environment and dimmer than anything in the gameplay layer. This reframes the
open signage work: the target is not "make the signs prettier", it is "the sign
is the only environmental thing allowed to glow, so it has to earn it."
§8's shape guidance — *"thin seams, small energy nodes, distinct symbols,
directional strips"* — also rules out the current approach of filling the whole
blade face.

### 3.4 Lot — the §22 review tests are automatable

§22 lists five tests. Three are a few lines of numpy over a frame we already
capture in the walk:

- **Thumbnail** — downsample to 64px, check the focal marker still separates
  from its local background by a value threshold.
- **Grayscale** — drop chroma, re-run the same separation check. Catches
  anything that was surviving on hue alone.
- **Blur** — heavy blur, then measure what fraction of total luminance variance
  falls in the top decile of screen area. Uniform contrast lands near 0.10;
  a scene with a real focal point lands far above it. This is the single number
  that answers *"does the scene have equal contrast everywhere"*.

That becomes a `walktest_contrast` step alongside `walktest_navqa`, and it is
the piece that makes the standard visible in the level rather than in the
material library.

---

## 4. Ordering

1. **P1 + P4** — tier declaration and the audit baseline. Cheap, and everything
   else is judged against them.
2. **P2 + P3** — derived quiet variants and the `quiet` theme block. The
   enabling change.
3. **Z1 + Z2** — quiet wall modules on non-street elevations. First point where
   this is visible in a screenshot.
4. **Pa2** — undressed doorway flanks.
5. **Lot §22 tests** — the blur test first; it is the cheapest and the most
   diagnostic.
6. **Pa3** — signage as the sole environmental emissive.

The `ceiling_tile_delco` and `subway_tile_white` highlight fixes can jump the
queue at any point; they are two grammars and they affect every interior.

---

# Part II — Quake II: texture-authored relief

The contrast standard above says *quiet*. The Quake II technique says *quiet at
the macro level, intentional at the texture level*. Those are the two halves of
the same answer, and the second half is the one that resolves the original
complaint — "it looks boring and too one dimensional" — without reintroducing
the noise Part I is trying to remove.

Measured on the same library, same run.

## 5. What we already do right

**Value economy is present and does not need work.**

```
unique colours per grammar :  min 4   median 14   max 948
occupied L-bins (>2% each) :  min 1   median  4   max  10
```

A median of **14 unique colours and 4 occupied value bins** is already the
"1 shadow / 1 body / 1 light-facing / 1 highlight / 1 accent" discipline, not a
photograph reduced to a small image. Pixelcoat's quantization pass is doing the
job §3 of the Quake II notes asks for. The failure mode described there — "17
slightly different gray values", indistinct noise, muddy surfaces — is not ours.
The seven glass grammars (up to 948 colours) are the exception and they are
gradients by intent.

## 6. What is missing

### 6.1 The values are economical but not *separated* — no painted bevel

A painted bevel is a specific arrangement: bright edge, mid field, dark band,
near-black interior, small highlight. That requires value clusters that are
**separated**, with gaps between them.

**22 of 51 grammars have all their value mass in a single contiguous run.**

A continuous band of four adjacent value bins is a material field. It is not a
bevel, and no amount of it will read as a recessed panel, a seam, or a plate
edge — there is no dark band to be the recess and no bright line to be the
metal edge, because there is no gap. This is why the buildings read as flat:
the palette is disciplined, but the palette has no *depth vocabulary*.

Grammars that do separate (`concrete_sidewalk_street` 4 clusters, `terrazzo` 3)
separate by accident of their generator, not by design.

### 6.2 Pixelcoat generates fields; Quake II textures are compositions

This is the structural one. A Pixelcoat grammar produces a **homogeneous tiling
field** — that is its definition, and `test_material_grammar.py` asserts it with
`_seam_ok` on every material. §3 of the Quake II notes describes the opposite:

```
┌─────────────────────┐
│  quiet metal field  │
│                     │
│  ▓▓ vent ▓▓         │
│                     │
│      [orange light] │
└─────────────────────┘
```

A quiet field, a frame, one or two inserts, one accent. That is a **composition
with internal placement**, and a tiling field generator cannot produce one no
matter how good the generator gets. The missing subsystem is not a better field
— it is a **panel composer** that takes a quiet field from an existing grammar
and lays graphic elements onto it at authored positions.

Everything else in the Quake II notes (§6 texture inserts as virtual props, §8
rhythm through repetition, §14 one graphic idea per prop) is downstream of that
one capability.

### 6.3 Texel density is 3× inconsistent, and 4–8× too fine for the aesthetic

```
meters_per_tile 1.00  ->  512 px/m   (11 grammars: all glass, canvas)
meters_per_tile 1.50  ->  341 px/m   ( 7 metals, gravel)
meters_per_tile 2.00  ->  256 px/m   (22 brick, tile, cinderblock, ceiling)
meters_per_tile 2.50  ->  205 px/m   ( 4 concrete, plaster, flagstone)
meters_per_tile 3.00  ->  171 px/m   ( 6 asphalt, drywall, concrete)
                              spread   3.0x
```

Two problems in one table. §9 of the notes names the failure exactly — *"A
one-meter metal panel should not have 32 pixels on one wall and 256 pixels on an
adjacent wall"* — and a window (512 px/m) set into a concrete wall (171 px/m) is
that case, on every building we ship.

And the absolute numbers are not pixel-art numbers. The notes offer 32 / 64 /
128 px/m; the *coarsest* material we own is 171. The whole library is authored
1.3–16× finer than the aesthetic calls for.

Both fix with one change: **stop passing a fixed `--size` and derive it from
`meters_per_tile × target_density`, rounded to a power of two.** At a 128 px/m
target:

```
brick_delco     mpt 2.00   512px/m now -> size 256 -> 128 px/m   1.00x
concrete_delco  mpt 2.50   205px/m now -> size 256 -> 102 px/m   1.25x
glass_circles   mpt 1.00   512px/m now -> size 128 -> 128 px/m   1.00x
metal_rusted    mpt 1.50   341px/m now -> size 256 -> 171 px/m   1.33x

spread 1.67x (from 3.00x)   worst deviation from target 1.33x
```

*Correction:* an earlier draft of this section said "spread cut from 3.0× to
1.33×". That conflates two different quantities and overstates the result. The
power-of-two rounding caps each pack's **deviation from target** at √2; the
**spread between two packs** is therefore bounded by 2×, because two packs can
miss in opposite directions — which is what happens (flagstone mpt 2.5 lands at
102 px/m, metal at mpt 1.5 lands at 171). Measured: spread **3.00× → 1.67×**,
worst deviation 1.33×. The test that pins this caught the error; the claim was
wrong, not the code.

Power-of-two preserved, spread nearly halved, and the library lands in
pixel-art territory instead of near-photographic.

*Caveat resolved — Zoo does honour it.* `bpylayer/materials.py:207` reads
`mpt = pack.get("meters_per_tile") or 1.0` and drives a Mapping node at
`1/meters_per_tile`, over UVs that `geometry.cube_project_uv` lays down as
world-metres × `texel` (default 1.0). So on-screen density is
`size × texel / meters_per_tile` — the 3.0× spread above is real on the mesh,
not just in the manifest, and deriving `size` from `meters_per_tile` fixes it
at the source.

One thing that audit turned up: `texel` is a live per-part multiplier, and
`recipes/dress_cover.py` sets `texel=1.2`. Every dressing cover therefore sits
at 20% higher density than the wall behind it — a texel-density break at exactly
the mid-frequency props §9 of the notes warns about. Worth sweeping for other
non-1.0 `texel` values once the pack sizes are consistent, or the fix above will
be partly undone downstream.

## 7. This changes the Zoo relief verdict

Part I said relief should be tier-gated. The mesh/texture division test in the
Quake II notes is sharper than that:

> *Would the detail alter the silhouette, collision, or shadow in a meaningful
> way? When the answer is no, it may be better represented in the texture.*

Our current constants:

```python
RELIEF = {"bay": 2.4, "pier": 0.14, "reveal": 0.05, "base": 0.45, "cap": 0.12}
```

*Correction to an earlier draft, which read these as five depths.* They are not.
`base`, `pier` and `cap` all span the **full** authored depth; only `Field_*` is
pulled back, by `reveal` on each face. Measured on a 4.8 m module at d 0.35:

```
Base   d = 0.350      Pier   d = 0.350
Cap    d = 0.350      Field  d = 0.250    -> every step is 0.05 m per face
```

So there is exactly **one** relief depth in the whole system, and it is 5 cm.
The other four constants are the *graphic proportions* of the bands — how wide
a pier is, how tall a plinth is, how often a bay repeats.

That makes the verdict cleaner rather than weaker:

- **The 5 cm step fails the test outright.** It does not alter silhouette. It
  cannot alter collision — the collider comes from `slab`, never from `visual`,
  so the relief is invisible to physics by design. At 3 m eye height it casts no
  contact shadow worth the seven boxes it costs.
- **`base` 0.45 m survives as a proportion** — a plinth reads at a distance
  because of its *height*, not its 5 cm projection, and a painted band gives the
  same read.
- **bay 2.4 m** — not depth at all, it is *rhythm*. §7 and §8 of the notes put
  rhythm in the texture, carried by alignment: `support – panel – vent – panel –
  support`.

So the recommendation upgrades from *tier the relief* to **stop paying for the
5 cm in geometry and repay the whole articulation in texture**. The bands are
worth keeping; their depth is not. That is simultaneously cheaper geometry and a
richer surface — the two things that looked like a trade-off in Part I are the
same move here.

And it is nearly free to try, because the switch already exists: `relief:
{reveal: 0}` in a style block collapses a wall to one plain `Panel` through
`relief_parts`' own degenerate path. 56 parts to 8 across eight authored widths,
no Zoo code change, collision untouched. That makes this the cheapest experiment
on the list, not the most expensive — set `reveal: 0` on one archetype's style,
rebuild, and look at it.

The 2.4 m bay is worth keeping as a *number* even after the geometry goes,
because our modules are already width-keyed (`_w<cm>` in the module stem). §7 of
the notes — *"make repeated motifs land on architectural divisions"* — wants a
grid to align to, and the kit already quantizes wall widths to one. That grid
exists and is currently unused by the art.

## 8. Revised ordering

Part I's list still holds, reordered now that the relief switch turns out to be
free rather than expensive:

0. **`relief: {reveal: 0}` on one archetype's style, rebuild, look at it.**
   Zero code. It is the A/B that tells us whether "quiet geometry, loud texture"
   is the right direction *before* we build anything to support it. If the plain
   walls look worse, everything below changes.
1. **P1 + P4** — tier declaration, audit baseline.
2. **Texel density from `meters_per_tile`.** One change in
   `build_theme_library`, fixes the 3× spread and the aesthetic target together.
   Verify Zoo honours `meters_per_tile` first.
3. **Separated value clusters.** Extend the grammar with an explicit bevel band
   set (edge / field / seam / recess / highlight) so a surface can express depth.
   This is what pays back step 0's geometry, and without it step 0 just produces
   flatter flat walls.
4. **P2 + P3** — derived quiet variants, `quiet` theme block.
5. **Z2** — street-facing vs. rear elevations pick different styles, via
   `slots.outward_sign`.
6. **The panel composer.** Quiet field + frame + inserts + one accent.
   The largest new subsystem, and the one that makes 6.2 possible.
7. **Pa2** — undressed doorway flanks.
8. **Lot §22 tests** — blur test first.
9. **Pa3** — signage as the sole environmental emissive, now with the notes'
   §13 emissive guidance: exact graphic masks, hard edges, small lit areas.
