"""A house's own brick (0.57.0): brown and orange beside the red.

The walker's South Philly photograph (the factory root's
`docs/reference/EMPTIES_COMPS.md`, "Window comps"): "every house a different
brick: brown, red, orange". A theme holds one grammar per kind, so a second
brick in one level needs a kind of its own -- the carpet note in
`test_theme_profiles.py` says the same of `carpet_tournament`. `brick_brown`
and `brick_orange` are those kinds; their grammars are `brick_delco` with
their own palette and mortar.
"""
import colorsys
import json
import os

from pixelcoat.cli import main as cli

HERE = os.path.dirname(os.path.abspath(__file__))
PROFILES = os.path.join(HERE, "..", "profiles")


def _load(*parts):
    with open(os.path.join(PROFILES, *parts), encoding="utf-8") as fh:
        return json.load(fh)


def _hls(hexes):
    rgb = [tuple(int(h[i:i + 2], 16) / 255.0 for i in (1, 3, 5)) for h in hexes]
    hls = [colorsys.rgb_to_hls(*c) for c in rgb]
    return (sum(x[0] for x in hls) / len(hls), sum(x[1] for x in hls) / len(hls),
            sum(x[2] for x in hls) / len(hls))


def test_both_level_themes_map_both_bricks():
    """FAILS ON 0.56.0: neither kind was mapped anywhere."""
    for theme in ("delco", "delco_1997"):
        m = _load("themes", f"{theme}.json")["materials"]
        assert m.get("brick_brown") == "brick_brown_delco", theme
        assert m.get("brick_orange") == "brick_orange_delco", theme


def test_they_are_brick_with_their_own_kind_and_palette():
    """A theme slot's grammar is of the slot's own kind
    (`test_theme_grammars_exist_and_match_their_slot`); the masonry is the
    red's."""
    red = _load("materials", "brick_delco.json")
    for pid, kind in (("brick_brown_delco", "brick_brown"), ("brick_orange_delco", "brick_orange")):
        g = _load("materials", f"{pid}.json")
        assert g["id"] == pid and g["kind"] == kind
        assert g["masonry"]["rows"] == red["masonry"]["rows"]
        assert g["base_colors"] != red["base_colors"]


def test_brown_is_darker_than_the_red_and_orange_is_yellower():
    red_h, red_l, _ = _hls(_load("materials", "brick_delco.json")["base_colors"])
    _bh, brown_l, _ = _hls(_load("materials", "brick_brown_delco.json")["base_colors"])
    orange_h, _ol, _ = _hls(_load("materials", "brick_orange_delco.json")["base_colors"])
    assert brown_l < red_l
    assert orange_h > red_h


def test_zoo_s_vocabulary_lists_them():
    for kind in ("brick_brown", "brick_orange"):
        assert kind in cli._ZOO_KINDS
