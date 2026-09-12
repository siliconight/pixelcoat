# Changelog

## [0.30.0] - 2026-09-12

The ground has kinds now: `asphalt` and `sidewalk`.

Roadmap 152. The exterior ground plate in every cold package was one
untextured grey (`gb_floor`, 0.52, no image), because Lot's plate is not a
Zoo module and nothing had ever handed it a skin. The theme library builds
one pack per kind a theme names, and a theme slot must carry a grammar of
that kind (`test_theme_profiles`), so two grammars are minted with the kinds
Lot will ask for: `asphalt_delco` (from `asphalt_street`, 3 m tile) and
`sidewalk_delco` (from `concrete_sidewalk_street`, 2 m). `delco` and
`delco_1997` map `asphalt` and `sidewalk` to them; `theme-library` now emits
`asphalt_<theme>/` and `sidewalk_<theme>/` beside the 24 kinds it built
before. The two kinds are Lot's vocabulary, not Zoo's (`_LOT_KINDS`), so the
unknown-kind warning does not fire on them. The existing street grammars
keep their `concrete` kind: `center_city` maps `concrete` to the sidewalk
one and would have failed its own test otherwise.

## [0.29.0] - a new person can mint a material

### Added
- `tools/new_material.py` (roadmap 150, the texture half). `report` lists,
  per theme, the kinds Zoo's species can wear that the theme has no profile
  for -- a species wearing one renders flat. `new <profile> --kind --like
  --colors [--meters-per-tile] [--theme]` writes a grammar from a template
  profile, synthesizes it at 64 px and prints the two numbers item 140
  measures a skin by (albedo std and neighbour correlation, with a warning
  under 0.3), maps the kind into the theme so `theme-library` builds it
  (`--replace` to take a mapped slot), refuses to overwrite, and says when
  the kind is one Zoo does not know yet. A grammar copied with new colours
  is the template's surface in new colours, which is the honest state of a
  material nobody has authored; the profile file is where the authoring
  goes. `tests/test_new_material.py`.

## [0.28.0] - the drywall reads as a wall, not as static

### Changed
- `drywall_orangepeel_delco` and `carpet_delco` lose most of their per-texel
  grain. Roadmap 140, walked 2026-09-11 on cold run 9005: the ward walls
  read as "fizzy, too much digital noise". Two numbers over the albedo's
  luminance say what that is -- spread (std, 0-255) and the correlation
  between a texel and its neighbour (1.0 smooth, 0.0 every texel on its
  own). The shipped delco_1997 packs, 256 px at 2.0 m:

      drywall_orangepeel   std 23.9   ac1 0.12
      carpet               std 10.0   ac1 0.08
      plaster              std 12.1   ac1 0.34
      ceiling_tile         std 15.6   ac1 0.51
      concrete             std 28.2   ac1 0.75
      brick                std 31.5   ac1 0.80

  Drywall had brick's amplitude at carpet's correlation: a large random term
  with no spatial structure, which at 128 texels per metre is static rather
  than orange peel. THE DIAL WAS `detail_strength`, the hash grain: dropping
  it alone took drywall from 23.9 / 0.12 to 10.7 / 0.61. The micro band was
  not the dial -- its weight (0.30 x 0.12 of a +-0.5 field) sits under one
  step of `posterize: 16` and quantises away; changing its cells or octaves
  moved nothing at one decimal, which is the null-result rule's case. What
  ships: drywall meso worley 24 (a mottle at 8 cm, the roller's scale, not
  the peel's -- the peel is sub-texel at this density), micro 40/2, grain
  0.04 -> std 11.6 / ac1 0.70, concrete's correlation at plaster's
  amplitude. Carpet: grain 0.05, meso fbm 48/2 at band 0.7 so the amplitude
  comes from pile structure rather than noise -> std 7.5 / ac1 0.66.
- `tests/test_theme_profiles.py` synthesises delco_1997's drywall, carpet
  and plaster at their pack size and holds correlation >= 0.5 (0.3 for
  plaster) inside a spread band. Orange peel as RELIEF -- a normal map --
  is the honest version of this material and is not emitted yet
  (`emit.normal: false`); this change is the albedo reading right at the
  distance a person stands from a wall.

## [0.27.0] - delco_1997, a theme the briefs have asked for since cold run 7002

### Added
- `profiles/themes/delco_1997.json`. Delaware County, 1997: a commercial strip
  at dusk.

  WHY IT WAS MISSING FOR SO LONG. `level_factory/packages/tools/themes.py`
  records cold run 7002 putting three candidates through Blender, Lot, Laser
  Tag and walktest -- tens of minutes -- and then `pixelcoat_build` exiting 1
  in two seconds on `no theme profile for 'delco_1997'`. Roadmap 72 responded
  by adding a PRE-FLIGHT CHECK, which was the right call for the defect it
  named ("the absence of the check was the defect") and left the content gap
  standing. Cold run 9003 hit the same wall from the other side: the check
  fired early and correctly, and there was still no profile behind it.

  NOT AN ALIAS TO `delco`, and not a copy of it. An alias resolves the error
  and leaves the next consumer naming a period theme with nothing behind it.
  A copy duplicates 24 mappings that then drift apart. This is a real profile
  built only from grammars already in the library, differing from `delco`
  exactly where 1997 differs:

        glass_facade   mirror blue   -> bronze anodized shopfront
        glass          frosted       -> plain storefront glazing
        tile           tile_delco    -> beige VCT
        drywall        scuffed       -> orange peel
        plastic        neutral       -> delco

  Every grammar's declared `kind` was checked against the slot before it was
  authored. `tests/test_theme_profiles.py` exists because two shipped
  `rockay_*` profiles mis-slotted `cinderblock_delco` and `travertine_warm`,
  and that check only fires at build time otherwise. 39 profile tests pass,
  224 in the suite.

### Known
- Zoo carries no `delco_1997` style across its 56 species, so the prop kit
  still falls back to flat colour on this theme. That is the other half of the
  same gap and is not closed here; `themes.py` reports it as a warning rather
  than a wall, which is the correct severity -- a missing Pixelcoat profile
  stops the art pass, a missing Zoo style disappoints it.

## [0.26.0] - the panel grammar earns its name

### Changed
- `concrete_panel_delco` takes `form_lines.cross: {count: 3}`. Three joints
  each way on a 4 m tile is roughly 1.33 m square panels, and the surface now
  reads as discrete precast units instead of horizontal bands. That closes the
  operator's original verdict on it -- "reads as stripes, not intentional
  architecture" -- which turned out to be a capability report: `form_lines`
  could only draw one direction until 0.25.0.
- `industrial_flats` points its `concrete` at `concrete_boardform_delco`
  rather than `concrete_boardform_stadium`. Same look, honest name. 0.22.0
  routed around it only because the grammar was uncommitted at the time.

### A line is not texture interest
Counted while making this change, because "lines everywhere" is a real way for
a library to go wrong: 5 of 65 grammars use `form_lines` at all, and 1 uses
`cross`.

```
concrete_boardform_delco     count 7            board courses
concrete_boardform_stadium   count 7            board courses
concrete_interior_delco      count 5            formwork
concrete_panel_delco         count 3 + cross 3  panel joints
drywall_taped_delco          count 1  str 0.12  one taped seam
```

Every one is a surface whose real-world subject IS the joint. The rule worth
keeping: a seam goes in when the surface is made of units or courses and the
joint would read at gameplay distance -- not to break up a flat area. The
other 60 grammars have no lines and render byte-identically to before 0.25.0,
verified by hash.

## [0.25.0] - form_lines can draw the other direction

`form_lines` drew horizontal seams and only horizontal seams: `axis="y"` was
hardcoded at the call site and the field's own comment said "horizontal
form-board seams". So `concrete_panel_delco` could not read as precast panels
at ANY `count` -- a panel wall needs joints both ways, and it could only make
bands. The operator's verdict on that grammar, "reads as stripes, not
intentional architecture", was a capability report rather than a taste note,
and this is the capability.

### Added
- `form_lines.axis` -- `"y"` (default, horizontal board courses) or `"x"`.
- `form_lines.cross` -- an optional second pass on the perpendicular axis,
  which is what turns bands into a GRID. It inherits the primary's `seam`,
  `jitter` and `strength` unless it overrides them, because a panel wall's two
  joint directions are usually the same joint seen twice. `{"count": 3}` is
  enough to get square panels out of a 4 m tile.

Both passes go through one `_apply_form_lines` helper: two spellings of a seam
is how one direction ends up with a jitter the other does not.

### Unchanged
- BYTE-IDENTICAL for every grammar that does not use the new keys, verified by
  hash rather than by the suite passing: `concrete_boardform_delco`,
  `concrete_panel_delco` and `concrete_boardform_stadium` all re-render to the
  same md5 as before the change. A grammar with no `axis` and no `cross` takes
  exactly the path it took before.
- `concrete_panel_delco` is NOT wired to use `cross` here. The capability is a
  tool change; how big a precast panel should be is an art call, and the
  contact sheet for counts 2, 3 and 4 goes to the operator rather than being
  decided in a changelog.

## [0.24.0] - the macro-structure concretes stop being aggregate

One field. Both grammars were `concrete_delco` plus `form_lines`, and both
inherited its `edges` (`cells 9, thr 0.7, strength 0.35`) -- which is what
draws the exposed-aggregate cell boundaries that were burying the structure.
`concrete_boardform_stadium` has always set `edges: null`, and that alone was
why it was the only concrete in the library reading as genuinely board-formed.

### Changed
- `concrete_boardform_delco`: `edges` -> null. It now reads as board-formed
  concrete -- seven board courses with vertical grain between them -- instead
  of aggregate with faint lines over it. This is the grammar
  `industrial_flats` wanted; 0.22.0 routed around it to
  `concrete_boardform_stadium` only because it was uncommitted at the time.
- `concrete_panel_delco`: `edges` -> null, `form_lines.count` 2 -> 3. Cleaner
  cast concrete, and three seams give a panel rhythm where two read as a slab
  cut in half.

### Known: `concrete_panel_delco` still cannot read as PANELS
`form_lines` draws horizontal seams only -- `axis="y"` is hardcoded at
`material_grammar.py:284`, and the field's own comment says "horizontal
form-board seams". A precast panel wall needs vertical joints as well, so at
any `count` this grammar produces horizontal BANDS rather than a panel grid.
That is the residue of the operator's original verdict on it, "reads as
stripes, not intentional architecture", and raising the count improves the
rhythm without addressing the cause.

`ps.stripes` already takes an `axis`, so the capability is one parameter away:
`form_lines` would need to accept an axis (or a second cross-axis block) and
pass it through. Not done here -- it is a grammar-schema change and this
release is a tuning pass.

## [0.23.0] - the two macro-structure concretes join the repo

`concrete_boardform_delco` and `concrete_panel_delco` were authored on
2026-09-06 in the macro-structure skin pass, shown, and left UNTRACKED in the
working tree. Untracked art is art the repo does not have: a profile may not
reference it, a clean checkout does not build it, and a test can go red
against it while every fresh clone reports green.

### Added
- `profiles/materials/concrete_boardform_delco.json` (`meters_per_tile` 2.0,
  7 form lines) and `profiles/materials/concrete_panel_delco.json`
  (`meters_per_tile` 4.0, 2 panel seams, streaking). Committed as authored and
  as reviewed -- no art changed here.

### Fixed
- `test_fixed_size_reproduces_the_old_three_times_spread` -> `..._four_times_`,
  asserting 4.0. It pinned a historical 3.0x fixed-tile spread and went stale
  the day `concrete_panel_delco` was written at `meters_per_tile` 4.0 against
  a library floor of 1.0. Because that grammar was untracked, the test was RED
  on this machine and GREEN on every clean clone -- the worst of both. It is a
  foil for the derived-size path (which holds 1.667x), so a wider library
  making the foil worse is the argument working, not a regression.

### Known, unchanged, and now precisely attributed
- BOTH NEW GRAMMARS READ AS EXPOSED AGGREGATE WITH FAINT LINES rather than as
  board-formed or panelised concrete, and the cause is ONE FIELD. Each is
  `concrete_delco` plus `form_lines` and a `cavity` colour; every other field
  -- `base_colors`, `macro`, `meso`, `micro`, `posterize`, `roughness`, and
  crucially `edges` -- is byte-identical to it. `edges`
  (`cells 9, thr 0.7, strength 0.35`) is what draws the aggregate cell
  boundaries, and `concrete_boardform_stadium` sets `edges: null`, which is
  the whole reason that one reads as genuine board-formed concrete.

  Not changed here, because that is an art judgement and the operator has
  already given one on the panel variant ("reads as stripes, not intentional
  architecture"). The one-field experiment is cheap and is worth running
  before either grammar is wired into a theme.

## [0.22.0] - the Philadelphia half of the setting becomes buildable

`USING_THE_FACTORY.md` now records the game's setting: 1990s Pennsylvania,
weighted to Philadelphia urban and Delaware County. Measured against that,
the sharpest gap in the toolset was not missing art -- it was two missing
files. Zoo already carries species styles for `center_city` at 54 of 56
species and `industrial_flats` at 54 of 56, better coverage than `delco`'s
39, and neither could be built because Pixelcoat had no theme profile for
either. This adds both.

### Added
- `profiles/themes/center_city.json` -- Philadelphia rowhouse and storefront
  blocks. Painted brick over a subway-tiled shopfront, wavy old glass in the
  upper sash, bronze curtain wall on whatever went up in the eighties, city
  sidewalk underfoot. Distinct from `delco` on brick, glass, glass_facade,
  metal, tile and wood: older, denser, more finished -- the same city with
  another eighty years on it.
- `profiles/themes/industrial_flats.json` -- the low industrial ground. Mill
  brick and board-formed concrete, corrugated siding, factory sash with panes
  out of it, taped drywall in the office somebody partitioned off the floor,
  VCT in the break room. Reads as working stock rather than ruin.

Both carry all 24 material slots, pass `tests/test_theme_profiles.py` (every
grammar exists and its declared `kind` IS the slot it fills), and were BUILT
rather than only statically checked -- that test's own docstring says it
exists so nobody pays for synthesis, so a new profile should pay once.
`themes.resolve` now reports both `ok` with Zoo at 54/56.

### Known, and not addressed here
- FIVE OF THE FOURTEEN `concrete` GRAMMARS RENDER AS ONE EXPOSED-AGGREGATE
  PATTERN at different scales -- `concrete_delco`, `concrete_sidewalk_street`,
  `concrete_panel_delco`, `concrete_boardform_delco` and `asphalt_street`.
  Those are the names a profile reaches for first, and concrete is the most
  referenced material in the Deli Counter library at 194 uses. Meanwhile
  `concrete_boardform_stadium` reads as genuine board-formed concrete and
  `concrete_interior_delco` as plain cast concrete.

  `center_city` keeps the semantically correct `concrete_sidewalk_street` and
  the gap is filed rather than dodged. `industrial_flats` uses
  `concrete_boardform_stadium`, whose name records where it was first authored
  and not where it belongs -- it is the only grammar in the library that reads
  as genuinely board-formed. That choice was forced rather than preferred: the
  obvious pick, `concrete_boardform_delco`, IS NOT COMMITTED. It and
  `concrete_panel_delco` have sat untracked in the working tree since
  2026-09-06, from the macro-structure skin pass, awaiting a judgement that
  was given for the panel one ("reads as stripes, not intentional
  architecture") and never acted on. A shipped profile may not reference a
  grammar that is not in the repo: the static test would pass on the machine
  that has the file and fail on every clean checkout.

- `tests/test_texel_density.py::test_fixed_size_reproduces_the_old_three_times_spread`
  is RED and was red before this change (verified by removing both new
  profiles and re-running). It pins a historical 3.0x spread; the library now
  spreads 4.0x because `concrete_panel_delco` carries `meters_per_tile` 4.0
  against a floor of 1.0. Stale baseline, not a regression -- but a red test
  nobody has decided about is how `test_pvp_heist.py` stayed red for twelve
  days.

## [0.21.0] - delco wears the drywall somebody actually looked at

0.20.0 shipped three drywall grammars and wired `delco` to
`drywall_orangepeel_delco` WITHOUT anyone having seen one on a wall, because
no instrument in the toolchain photographed an interior. That gap is now
closed (`look_shots --interiors N`), so the choice was made on evidence.

### Changed
- `delco:drywall` `drywall_orangepeel_delco` -> `drywall_scuffed_delco`.
  Chosen by the reporter from the interior station on `int_1_1_seg0`, the same
  wall in three builds differing only in this field.

  IT IS ALSO WHAT THE NUMBERS SAID, which is worth recording because they were
  available before the walk and were not trusted on their own. Scuffed
  measures contrast 15.70, between the plain base's 9.88 and the library
  median of 13.7. Orange peel measures 23.88 -- close to `concrete_delco`'s
  28.2, and a walk report had already singled that skin out as the one that
  "sticks out". Putting the library's second-loudest grammar on every interior
  wall a player stands next to was the risk flagged when it was wired, and the
  eye agreed.

`drywall_orangepeel_delco` and `drywall_taped_delco` stay in the library and
stay wired where 0.20.0 put them -- taped on `rockay_service`, scuffed now on
both `bank` and `delco`. Neither of those two themes has been built, because a
mission carries one theme and the only mission available is on `delco`.

## [0.20.0] - drywall stops being one material

Every interior wall in every theme was the same grammar. Measured across the
nine shipped themes: 15 of 24 material slots have exactly ONE grammar in the
whole 60-grammar library, and `drywall` is the one that costs the most --
210 kit surfaces on `precinct_yard_001`, identical in all nine.

### Added
- `drywall_taped_delco` -- a butt joint with compound feathered over it. ONE
  `form_lines` seam per tile, not two: a 2.0 m tile repeats every 1.67 m in
  world space, so a single line lands about where a sheet joint does, and two
  read as stripes rather than as architecture. Strength 0.12, because joint
  compound is nearly the colour of the board. Measured row/col 4.38 against
  the base's 1.23 -- directional structure, contrast barely moved.
- `drywall_orangepeel_delco` -- the sprayed commercial finish, and the wall a
  player stands closest to. Stipple in meso/micro (`worley_f1` 64, fbm 200),
  `detail_strength` 0.18. Contrast 23.88 and fine detail 23.72 against the
  base's 9.88 and 8.55, direction-free at 1.02.
- `drywall_scuffed_delco` -- painted board knocked about, with `chips`
  exposing an `undercoat` set to paper colour, so the damage reveals what is
  actually under the paint. Contrast 15.70.

`drywall_delco` is unchanged and stays the neutral. It was never wrong; it was
only ever alone.

### Changed
- `delco:drywall` -> `drywall_orangepeel_delco`
- `bank:drywall` -> `drywall_scuffed_delco`
- `rockay_service:drywall` -> `drywall_taped_delco`

### NOT VISUALLY VERIFIED IN PLACE, and the reason is structural
All three were built through the full pipeline on `precinct_yard_001` --
structural checks passed, and the three packages carry three distinct drywall
albedos by hash, so the change reaches a shipped export. But the difference
between them is invisible to `look_shots`: across eight cameras the largest
delta between variants is 0.06% of pixels. The rig derives an overview, four
orthographic elevations and spawn/objective/extraction, and none of them
stands in a room facing a wall. Drywall is an interior material and nothing in
this toolchain photographs interiors -- Level Factory roadmap item 18.

So these were judged on the texture at matched scale, not on a lit wall at
2 m, which is the distance that decides whether the orange peel reads as
finish or as noise. Its contrast (23.88) is close to `concrete_delco`'s (28.2),
which is the skin a walk report singled out as too loud.

`bank` and `rockay_service` are wired on the same reasoning and have not been
built at all: a mission carries one theme, and the only mission available here
is on `delco`.

## [0.19.0] - metal and drywall tile with the walls too

0.18.0 did concrete. The same arithmetic applied to the other two skins on the
same walls, and both were named there as the obvious next candidates.

### Changed
- `metal_rusted_street` `meters_per_tile` 1.5 -> 2.0, `drywall_delco` 3.0 ->
  2.0. Same mechanism as 0.18.0: a 2.0 m wall module consumes exactly one
  whole tile and ends where it began, so its neighbour continues the pattern
  instead of restarting it. Benched across the six real module widths, seam
  step against the step elsewhere: metal 17.09/12.41 (1.38) -> 15.51/12.31
  (1.26); drywall 10.10/6.92 (1.46) -> 8.03/6.89 (1.17). Both started well
  below concrete's 2.13, which matches the report that concrete was the skin
  that stuck out.

  DENSITY, and 2.0 is derived rather than picked. `pack_size_for` rounds to a
  power of two, and both 1.5 and 3.0 round badly: each landed on 170.7 px/m
  against the library's `DEFAULT_DENSITY` of 128. At 2.0 the rounding is
  exact -- 256 px / 2.0 m = 128 px/m -- so all three skins now sit on the
  intended density instead of 33% over or 20% under. `drywall_delco`'s pack
  drops 512 -> 256 px as a consequence; the density is unchanged in intent and
  normalized in fact, but a tile carries a quarter of the pixels it used to.

  SCOPE IS WIDER THAN DELCO, unlike 0.18.0. `metal_rusted_street` serves
  `delco:metal` and `street:metal`. `drywall_delco` serves NINE theme slots --
  bank, casino, delco, rockay, rockay_civic, rockay_retail, rockay_service,
  stadium and street -- so this changes drywall in every theme that has any.

### Known: world projection currently overrides all of this
`meters_per_tile` reaches a shipped package as the glTF
`KHR_texture_transform` scale, which Godot imports as the material's
`uv1_scale`. Level Factory 0.57.0 made every exported package run
`zoo_worldskin.gd` at import, and that script REPLACES `uv1_scale` with the
density it measures off the mesh -- Zoo's own texel constant, 1.2, which does
not vary with this field. Measured on a build carrying four different tile
periods (concrete 2.5, metal 1.5, drywall 3.0, glass 1.0, so `uv1_scale` 0.4,
0.6667, 0.3333 and 1.0): all four came out at 1.2000.

So in a package with world projection on, every skin repeats every 0.833 m and
this field changes nothing. The seam numbers above, and 0.18.0's, were
measured and approved on walk builds WITHOUT projection, where the field is
live. Both changes are still right -- they normalize density onto the
library's target and they are correct for any consumer that does not
world-project -- but neither is currently visible in a shipped export. The
fix belongs in `zoo_worldskin.gd`, which should carry the material's authored
`uv1_scale` into the world-space density rather than discarding it; its own
docstring claims it "reproduces the old density exactly", and it does not.
Tracked as Level Factory roadmap 104.

## [0.18.0] - concrete that tiles with the walls it is on

Reported from a walk of `precinct_yard_001`: the stone "looks stretched out
and not good against the other texture next to it", and one skin "sticks out
the most when we have seams showing". The seams are at every wall module
boundary, the whole length of a facade.

### Changed
- `concrete_delco` `meters_per_tile` 2.5 -> 2.0. THE SEAM IS ARITHMETIC, not
  art: Deli Counter's wall modules are 2.0, 1.6, 1.4, 1.3, 1.2 and 0.3 m wide,
  and a 2.5 m tile divides none of them, so every module box-projects a
  fraction of a tile, ends mid-pattern, and its neighbour restarts at zero.
  The break lands at EVERY boundary and is identical each time, which is why
  it reads as a deliberate architectural line rather than as noise. At a 2.0 m
  tile a 2.0 m module consumes exactly one whole tile and ends where it began,
  so the next module continues it -- the seam is not hidden, it stops
  existing.

  MEASURED on a bench that simulates box projection across the six real module
  widths, scoring the mean luminance step AT a boundary against the step
  everywhere else. Continuous projection scores 1.05 and box projection 2.13,
  so the bench reports "no seam" for the case that has none. Current skin
  30.04 at the boundary against 14.09 elsewhere; at `meters_per_tile` 2.0,
  20.55 against 13.99. Per boundary, in the order 2.0|1.4, 1.4|2.0, 2.0|1.3,
  1.3|2.0, 2.0|1.6: 27.7, 33.5, 27.7, 33.5, 27.7 becomes 14.4, 28.4, 14.4,
  32.9, 12.7 -- the three boundaries whose left module is 2.0 m wide fall to
  the texture's own step and the rest do not move.

  TWO CHEAPER EXPLANATIONS REFUTED FIRST. `concrete_delco` is the
  highest-contrast grammar in the library (28.2 against a 13.7 median) and is
  on roughly two thirds of a delco level's surfaces, so contrast looked like
  the culprit. Lowering it to 25.1 moved the seam 12% and made the
  seam-to-surroundings ratio WORSE, because the surrounding texture quieted
  faster than the boundary did. Removing the macro band outright moved it 4%.
  The boundary step is the difference between two arbitrary PHASES of the
  texture and is set by the tile period, not by how loud or how coarse it is.

  DENSITY, and it is the reason this is an art decision and not only a fix.
  `pack_size_for` rounds both 2.5 and 2.0 to a 256 px pack, so the resolution
  is unchanged and the on-mesh density rises 102.4 -> 128 px/m: the concrete
  reads about 25% finer. Verified through a real build of
  `precinct_yard_001` -- the whole art layer re-run, structural checks passed,
  and the `KHR_texture_transform` scale in the shipped GLBs moved concrete
  0.4 -> 0.5 with metal, drywall, carpet and ceiling untouched -- then walked
  and approved by the person who reported the defect.

  SCOPE is narrow: `delco` is the only theme that resolves `concrete` to this
  grammar. 2.0 is also the library's MEDIAN `meters_per_tile` across 60
  grammars, so this moves an outlier onto the norm rather than inventing a
  value.

### Noted, not changed
The same arithmetic applies to the other skins on those walls, and neither is
fixed here because each is its own art call: `metal_delco` tiles every 1.5 m
and `drywall_delco` every 3.0 m, so both still end mid-pattern on every
module width. They are the obvious next candidates.

This does NOT address stretched `wallEnd` filler modules, which are a
different defect with a different cause. A filler is a unit box scaled onto a
slot remainder -- measured up to (0.1, 4.7, 0.3) -- so its texture density is
`uv1_scale / node_scale` and changing the tile period scales both sides and
cancels. Measured on the shipped build, concrete world density spans 0.106 to
5.000, a 47x mismatch between surfaces and 47x stretch within one surface,
identical before and after this change. Only world-space projection makes
density independent of node scale; with it, every concrete surface measures
1.200. That is Level Factory roadmap item 88 and it is not Pixelcoat's to fix.

## [0.17.0] - frosted glass you can see through

Reported from a walk of `precinct_yard_001`: "we need to turn up the window
transparency, it's a bit too flat and you can't see through very well." A
screenshot of the shipped level shows the glazing reading as a flat panel
rather than a window.

### Changed
- `glass_frosted` `transparency.opacity` 0.68 -> 0.34. At 0.68 the pane is 68%
  opaque, and the frosted noise sits on top of that -- so the interior behind
  it never resolves and the window reads as a lighter wall. The value reaches
  a shipped build as the glTF `baseColorFactor` alpha on the skinned material:
  verified on `LF_precinct_yard_001.portable-godot`, where
  `M_Skin_glass_delco` carries `alphaMode: BLEND` and
  `baseColorFactor [1, 1, 1, 0.68]` on every `window_delco_*.glb`. `ior`
  is unchanged.

  SCOPE, and it is wider than the report. `glass_frosted` is the `glass` kind
  for THREE themes -- `delco`, `rockay_service` and `stadium` -- so all three
  get the more transparent pane. That is deliberate: 0.68 was too opaque for
  the material's own description ("frosted glass"), not just for delco's use
  of it. If a theme later wants its own glazing, `profiles/materials/` already
  carries nine other glass grammars.

### Noted, not changed
`glass_delco.json` exists in `profiles/materials/` -- dark teal, roughness
0.10, and NO transparency block at all -- and is referenced by no theme. It is
orphaned content, and `delco` resolves `glass` to `glass_frosted` instead. Not
touched here because adopting it would change colour and gloss as well as
transparency, which is not what was asked for.

## [0.16.0] - 2026-08-21

### Added
- Five material grammars for kinds that had none: `laminate_neutral`,
  `paper_neutral`, `carbon_neutral`, `tar_neutral`, `vegetation_neutral`.
  `laminate` and `paper` are `tintable` with achromatic bases; the other three
  carry their own colour. All five use only `fbm` and `worley_f1`, the two
  generators with worked examples in the existing profiles.

### Changed
- `pebble_gravel` declared `kind: dirt` while `gravel` had no profile at all.
  Retagged to `kind: gravel` on the evidence of its own content -- an aggregate
  block of six stone colours with a gap colour, at roughness 0.9. `dirt` keeps
  `dirt_delco`, which is soil: browns, an undercoat, and a chips block.
- All nine theme profiles now list ten previously unmapped kinds. `canvas`,
  `dirt`, `leather` and `rubber` already had `_delco` profiles that no theme
  referenced, so they had never been built.

### Notes
- The theme profile is the gate: a kind is built only if a theme names a
  profile for it. Libraries went from 68 packs to 118, `MISMATCHES=0`.
- `bank`, `casino`, `delco` and `stadium` are wired but still have no built
  library. `carpet` is themed by 7 of 9 by design -- a service alley and a
  street have no carpet.

## [0.15.0] - prop metal splits from architectural metal

`metal` was doing two jobs. A rusted storefront facade and a corrugated wall
belong to the BUILDING, and the theme should own their look. A vending machine
and a car body belong to the OBJECT, and the genome should own their colour.
One kind cannot serve both: making it tintable would repaint the architecture
by its greybox colour, and leaving it fixed is what put a galvanized spangle on
a red vending machine.

Measured before splitting anything: of the 42 Zoo species that can wear
`metal`, only 12 declare a style colour with chroma >= 0.10. The other 30 --
including all ten architectural species -- are already near-grey and correctly
keep `metal`. This is a 12-species change, not a 42-species one.

### Added
- `metal_painted_neutral` (tintable) -- semi-gloss enamel over sheet steel.
  Fine orange-peel at meso, tight grain at micro, roughness 0.42.
- `metal_bare_neutral` (tintable) -- brushed stock. Directional grain along x,
  hash grain at micro, roughness 0.28.

Two profiles and not one because Zoo looks up METALLIC per kind: paint is a
dielectric and bare metal is a conductor. A single shared profile would have
made every painted prop render with a metallic sheen.

### Changed
- All nine themes map `metal_painted` and `metal_bare`.

### Note
Nothing renders differently. No Zoo genome names either kind yet; that is the
next change and it is deliberately separate so each batch of species can be
looked at before the next one starts.

## [0.14.0] - plastic joins the vocabulary

Every theme mapped the same 11 architectural kinds. Zoo's `KNOWN_KINDS` has
22, and the gap was not evenly distributed: `plastic` is named by 17 of the 53
species and hard-coded as a literal in 6 recipe bodies, so it was the largest
single hole in the library by a wide margin. It stayed open because the only
plastic profile was `plastic_delco`, a dark red -- and Zoo shares one material
per kind, so mapping it would have turned every ATM shroud, vending machine
trim, CRT bezel, condiment bottle and car bumper the same red in all nine
themes. Worse than flat.

0.13.0 gave a grammar a way to say its albedo is a surface and not a paint
job. Zoo 0.42.0 reads it, and `tools/tint_probe.py` measured that the tint
reaches the exported GLB intact. So the mapping is now safe to make.

### Changed
- All nine themes map `plastic -> plastic_neutral`. Because that pack is
  tintable, this does NOT make 17 species share a colour: each mesh keeps the
  hue its genome or style declares and gains the pack's grain, sheen and
  roughness response.

### Note
`plastic_delco` is untouched and unmapped. It is a red plastic, correct for a
specific object and wrong for a shared kind slot; it stays available for a
theme that wants exactly that.

Still unmapped, in demand order: laminate (6 species, no profile), paper (5,
no profile), leather (3, profile exists), dirt (3, profile exists), gravel (2,
no profile), rubber (1 genome + hard-coded in simple_car and boots, profile
exists), tar (1 -- the `roof` species, no profile, unmapped since it shipped),
canvas, carbon, vegetation.

## [0.13.0] - a pack can now say it wants to be painted

Zoo's `make_material` drops the genome's per-specimen colour the moment a
pack resolves: every object of a kind shares one cached material named for
the pack, and the only thing modulating it is COLOR_0, which carries
greyscale wear. That is right for a brick wall and wrong for a bumper. The
fix cannot key on material KIND, because `metal` serves both a rusted
storefront facade and 42 prop species. So it keys on the PACK.

### Added
- **`tintable` on the material grammar**, written into the pack manifest. A
  grammar sets it when its albedo is deliberately achromatic and the
  consumer is expected to supply the hue. `metal_rusted_street` does not set
  it and never should; `plastic_neutral` does.
- **`plastic_neutral`** - an injection-moulded plastic in near-white, with
  flow-direction grain and a low-variance sheen. It carries the surface and
  nothing else, so a red vending machine and a black ATM shroud can share
  it. This is the first profile authored to be multiplied rather than used.

### Fixed
- **`version.py` still said 0.11.0** while `VERSION` said 0.12.0. The 0.12.0
  release bumped one and not the other, so every pack built since - including
  the five theme libraries rebuilt today - is stamped
  `"tool_version": "0.11.0"`. That file's own docstring calls itself the
  single source of truth "baked into every manifest so output is traceable to
  the exact tool revision"; for one release it was not. Both now read 0.13.0.

### Note
Nothing renders differently yet. No theme maps `plastic`, so no pack resolves
for it and every plastic prop stays on the flat tinted path. Mapping it is a
separate change, deliberately held until Zoo reads `tintable`.

## [0.12.0] - The art standard gets a gate, and the library is calibrated against it

### Added
- **Baseline regression gate over the material library** (`a14fa62`). The
  Controlled Contrast Environment Art Standard was a document; this makes it
  a check the library is measured against, so the standard is enforced rather
  than remembered.
- **Neighbour-pair check** (`dd707fd`): a value step between adjacent
  materials needs a visible reason. A step nobody can see is a step nobody
  chose.
- **The `rockay` profile** (`72a9056`), with retail / service / civic
  variants and profile validation (`2e282af`).
- **`metal_rusted_street`** joins the delco theme (`c3db6c2`).

### Changed
- **Pack size derives from `meters_per_tile` at a target texel density**
  (`8cadc44`) instead of being chosen. Texel density is the thing that has to
  be right; pack size is what falls out of it.
- **Four palettes pulled off the luminance ceiling; baseline re-snapshotted**
  (`19a65e6`). `value_range` widens as the clipping is removed -- the range
  was being compressed by the ceiling, not by the palettes.
- **The bulk metal and the civic floor quieted; civic gets its own brick; the
  chroma budget recalibrated from the contact sheet** (`f01e3fb`).
- **Mortar joints that read**, and polished concrete separated from drywall
  by hue (`0f9772c`).
- **`glass_wavy` ripple calmed**: warp 0.35 -> 0.12, height 0.9 -> 0.45
  (`ca614bb`).

### Docs
- README points at `PIPELINE_MAP.md` and states what this repo owns
  (`531aa2e`).

Assembled on 2026-08-14 from this repo's own commits, eleven of them since
VERSION last moved, after `verify-manifest` reported pixelcoat STALE. Each
bullet names its commit; the numbers are carried through from the subjects
rather than paraphrased, because they are the part worth checking against the
code.

## [0.11.0] - Procedural material library + themed curation + stylized glass

### Added
- Two surface primitives: `voronoi_cells` (filled Voronoi cells with a
  per-cell id, for cobblestone/terrazzo/flagstone aggregates) and `wave`
  (undulating flutes; warp=0 gives straight reeded glass).
- `MaterialGrammar` gains `aggregate` (per-cell palette + mortar), `emissive`,
  `transparency` (an import hint, not lighting -- see below), multi-scale
  `veins` (list of passes), and `albedo_pattern` (albedo-only value mod).
- ~23 new tiling grammars: cinderblock, cobblestone, flagstone, granite,
  travertine, marble, subway/terrazzo/vct tile, hardwood/plywood,
  rusted/brass/galvanized/spandrel metal, stucco, pebble.
- Six textured glasses (circles, cracked_cells, wavy, blobby, frosted,
  reeded) + three opaque `glass_facade` variants (bronze, mirror_blue,
  spandrel_green) for hollow-shell building fronts.
- Themed curation: `build_theme_library()` + `pixelcoat theme-library
  --theme <t> --out <dir>` build one `<kind>_<theme>/` pack per curated
  material from `profiles/themes/<theme>.json`. Profiles shipped:
  street, delco, casino, stadium, bank.

### Changed
- Retuned `ceiling_tile_delco` (coarser acoustic grid) and
  `marble_bank_floor` (sharper veins).

### Notes
- Transparency is authored as a pack hint
  (`import_hints.transparency = {opacity, ior, alpha_mode}`); Pixelcoat never
  sets shader/lighting state itself -- Zoo honors the hint on the material.

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
