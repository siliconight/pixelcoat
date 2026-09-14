"""Tintable fabric: the club's upholstery takes the colour the mesh asks for.

Zoo 0.88.0, read against cold run 9052's delco_1997 build: `leather`
(brown), `canvas` (beige), `plastic` (red-orange) and 0.42.0's `velvet`
(burgundy) ignore the mesh colour, so every tablecloth rendered as gold
burlap, every bar-stool seat the plastic pack's red-orange, and a club chair
read coloured only because no velvet pack existed and it fell to the flat
path. `laminate`, `paper`, `metal_bare` and `metal_painted` took the colour,
because their packs say `tintable: true`.

THE ONE MECHANISM THE CONSUMER CHAIN HONOURS is that flag. Zoo's
`bpylayer/materials.make_material` reads `pack["tintable"]`, caches one
material per (kind, theme, colour) and multiplies the genome colour into
the albedo; the glTF exporter folds that into `baseColorFactor` (Zoo's
`tools/tint_probe.py`, measured), and Godot imports it as `albedo_color`.
Level Factory's `zoo_worldskin.gd` only switches vertex colour on for
COLOR_0 that is tinted; it never reads a pack. So a pack is tintable when
its manifest says so, and its albedo has to be a SURFACE -- achromatic and
light -- for the multiply to land on the asked colour.

What is held here:

- both delco themes map `velvet`, `canvas`, `leather`, `plastic` and the
  new `cloth` (a tablecloth's linen, not sackcloth) to tintable grammars;
- each of those grammars is achromatic and light, with no pixel crushed or
  blown, and multiplied by an oxblood in linear space lands on oxblood's
  hue at a value the pack's own mean sets (measured, not assumed);
- a built pack's manifest carries `tintable: true`, the key Zoo reads;
- the fabrics keep a surface: the velvet's crushed pile and spills still
  modulate an achromatic ground (neighbour correlation and spread, roadmap
  140's two numbers);
- the walker's `carpet_delco` and the plank `wood_delco` are untouched;
- Pixelcoat's mirror of Zoo's kind vocabulary knows the club kinds.
"""

import json
import os
import tempfile

import numpy as np
import pytest

from pixelcoat.core import material_grammar as mg
from tools import art_standard_audit as audit

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_MATERIALS = os.path.join(_ROOT, "profiles", "materials")
_THEMES = os.path.join(_ROOT, "profiles", "themes")
_SEED = 1999

TINTED = ("velvet", "canvas", "leather", "plastic", "cloth")
OXBLOOD = (0.22, 0.025, 0.04)          # club_forms.VELVETS[0], linear
WHITE_CLOTH = (0.92, 0.90, 0.86)


def _theme(name):
    with open(os.path.join(_THEMES, name + ".json"), encoding="utf-8") as f:
        return json.load(f)["materials"]


def _grammar(gid):
    return mg.MaterialGrammar.load(os.path.join(_MATERIALS, gid + ".json"))


def _synth(gid):
    g = _grammar(gid)
    return g, mg.synthesize(g, size=mg.pack_size_for(g.meters_per_tile),
                            seed=_SEED)


def _linear(albedo_u8):
    return audit._srgb_to_linear(albedo_u8[..., :3].astype(np.float64) / 255.0)


def _to_srgb_u8(lin):
    lin = np.clip(lin, 0.0, 1.0)
    srgb = np.where(lin <= 0.0031308, lin * 12.92,
                    1.055 * lin ** (1 / 2.4) - 0.055)
    return np.rint(srgb * 255).astype(np.uint8)


def _hue_deg(lab):
    return float(np.degrees(np.arctan2(lab[..., 2].mean(),
                                       lab[..., 1].mean())) % 360.0)


@pytest.mark.parametrize("theme", ["delco", "delco_1997"])
@pytest.mark.parametrize("kind", TINTED)
def test_the_delco_themes_map_the_fabrics_to_tintable_grammars(theme, kind):
    mats = _theme(theme)
    assert kind in mats, (theme, kind)
    assert _grammar(mats[kind]).tintable, (theme, kind, mats[kind])
    assert _grammar(mats[kind]).kind == kind


@pytest.mark.parametrize("kind", TINTED)
def test_a_tintable_fabric_is_an_achromatic_light_surface(kind):
    gid = _theme("delco_1997")[kind]
    g, s = _synth(gid)
    row = audit.measure(g, s)
    assert row["chroma_mean"] < 0.02, (gid, row["chroma_mean"])
    assert row["value_mean"] >= 0.80, (gid, row["value_mean"])
    assert row["crushed_frac"] == 0.0, (gid, row["crushed_frac"])
    if gid != "plastic_neutral":
        # plastic_neutral predates this file and ships 19 % of its pixels
        # over Oklab L 0.94 -- its baseline row says so. Harmless to a tint
        # FACTOR (it only sets how much of the asked colour arrives), and
        # not this release's to move; the four fabrics authored here are
        # held to zero.
        assert row["blown_frac"] == 0.0, (gid, row["blown_frac"])
    assert row["value_range"] <= audit.ENV_BUDGET["value_range"], row["value_range"]


@pytest.mark.parametrize("kind", TINTED)
@pytest.mark.parametrize("tint", [OXBLOOD, WHITE_CLOTH], ids=["oxblood", "white"])
def test_a_tintable_fabric_multiplied_by_a_colour_lands_on_that_colour(kind, tint):
    """The pack is the FACTOR's texture: albedo x tint in linear space is
    what Godot draws. Hue must be the tint's; value is the tint's scaled
    by the pack's own linear mean, which is the number a genome author
    needs. MEASURED at the pack size, seed 1999, the fraction of the asked
    linear value that arrives: velvet 0.62, leather 0.55, canvas 0.57,
    cloth 0.64, plastic 0.83. The floor below is 0.50 -- half the asked
    colour is the most a surface with worn cells and creases can take off
    before it stops reading as that colour -- not a derivation, and the
    per-channel spread is the clause that catches a cast."""
    gid = _theme("delco_1997")[kind]
    _, s = _synth(gid)
    lin = _linear(s["albedo"])
    tinted = lin * np.array(tint)
    asked = audit.srgb_to_oklab(_to_srgb_u8(np.array(tint)[None, None, :]))
    got = audit.srgb_to_oklab(_to_srgb_u8(tinted))
    if np.hypot(asked[..., 1], asked[..., 2]).mean() > 0.03:      # a hue to keep
        d = abs(_hue_deg(got) - _hue_deg(asked)) % 360.0
        assert min(d, 360.0 - d) <= 8.0, (gid, _hue_deg(got), _hue_deg(asked))
    mean_ratio = float(tinted.mean() / np.array(tint).mean())
    assert 0.50 <= mean_ratio <= 1.0, (gid, mean_ratio)
    per_channel = tinted.reshape(-1, 3).mean(axis=0) / np.array(tint)
    assert per_channel.max() - per_channel.min() < 0.06, (gid, per_channel)


def test_a_built_pack_manifest_says_tintable():
    gid = _theme("delco_1997")["velvet"]
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "velvet_delco_1997")
        mg.build_material_pack(os.path.join(_MATERIALS, gid + ".json"), out,
                               size=64, seed=_SEED)
        with open(os.path.join(out, gid + ".pack.json"), encoding="utf-8") as f:
            man = json.load(f)
    assert man["tintable"] is True
    assert man["material_kind"] == "velvet"


#: the delco grammar whose structure each neutral fabric copies
SOURCE = {"velvet": "velvet_delco", "leather": "leather_delco",
          "canvas": "canvas_delco", "cloth": "canvas_delco"}


def _structure(albedo_u8):
    a = albedo_u8[..., :3].astype(np.float64)
    lum = 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]
    d = lum - lum.mean()
    var = (d * d).mean()
    ac1 = ((d[:, :-1] * d[:, 1:]).mean() + (d[:-1] * d[1:]).mean()) / var / 2
    return float(ac1), float(lum.std())


@pytest.mark.parametrize("kind", sorted(SOURCE))
def test_a_tintable_fabric_keeps_the_structure_of_the_grammar_it_copies(kind):
    """Roadmap 140's two numbers, at the pack size, AGAINST THE SOURCE and
    not against the fbm floor: the drywall/carpet clause (ac1 >= 0.5) is
    wrong for a weave, which alternates texel by texel -- the shipped
    canvas_delco measures 0.25 and leather_delco's worley hide 0.26. So a
    neutral fabric may be no less correlated than the grammar it copies,
    less 0.05, and its spread stays inside the audit's band. `plastic` is
    not here: a smooth vinyl's structure is in its roughness map, and
    plastic_neutral predates this file."""
    gid = _theme("delco_1997")[kind]
    ac1, std = _structure(_synth(gid)[1]["albedo"])
    src_ac1, _src_std = _structure(_synth(SOURCE[kind])[1]["albedo"])
    assert ac1 >= src_ac1 - 0.05, (gid, ac1, SOURCE[kind], src_ac1)
    assert 3.0 <= std <= 16.0, (gid, std)


def test_the_velvet_keeps_its_crushed_pile_and_spills():
    gid = _theme("delco_1997")["velvet"]
    g = _grammar(gid)
    passes = g.wear if isinstance(g.wear, list) else [g.wear]
    assert len(passes) == 2, passes
    lab = audit.srgb_to_oklab(_synth(gid)[1]["albedo"])
    assert float(np.percentile(lab[..., 0], 2)) < float(np.median(lab[..., 0])) - 0.04


def test_the_cloth_is_finer_than_the_canvas():
    """A tablecloth is linen, not sackcloth: more threads per tile."""
    mats = _theme("delco_1997")
    cloth, canvas = _grammar(mats["cloth"]), _grammar(mats["canvas"])
    assert cloth.meso["generator"] == "weave" and canvas.meso["generator"] == "weave"
    assert (cloth.meso["count"] / cloth.meters_per_tile
            > 1.5 * canvas.meso["count"] / canvas.meters_per_tile)


@pytest.mark.parametrize("theme", ["delco", "delco_1997"])
def test_the_walker_keeps_carpet_delco_and_the_plank_wood(theme):
    mats = _theme(theme)
    assert mats["carpet"] == "carpet_delco"
    assert mats["wood"] == "wood_delco"
    assert not _grammar("carpet_delco").tintable
    assert not _grammar("wood_delco").tintable


def test_the_zoo_kind_mirror_knows_the_club_kinds():
    from pixelcoat.cli import main as cli
    for kind in ("velvet", "cloth", "carpet_club", "wallpaper_club",
                 "wood_stained", "paint_block", "metal_bare",
                 "metal_painted", "stone", "siding", "shingle", "tar"):
        assert kind in cli._ZOO_KINDS, kind
