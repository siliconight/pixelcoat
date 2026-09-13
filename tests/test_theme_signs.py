"""The businesses a theme names, as signs (roadmap 153, the 1990s street)."""
import json
import os

import pytest

from pixelcoat.core import signage as sgn

_PROFILES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "profiles", "signs")


def _profile(theme="delco_1997"):
    with open(os.path.join(_PROFILES, f"{theme}.json"), encoding="utf-8") as f:
        return json.load(f)


def test_the_theme_names_a_street_of_businesses():
    p = _profile()
    slugs = [s["slug"] for s in p["signs"]]
    assert len(slugs) == len(set(slugs)) >= 12
    families = {f for s in p["signs"] for f in s["families"]}
    # every family a generated street can ask for has somewhere to land,
    # and `default` is the one that always answers
    assert "default" in families
    for need in ("bank", "deli", "liquor", "bar", "retail", "warehouse"):
        assert need in families, need
    for s in p["signs"]:
        assert s["style"] in ("panel", "neon", "price")
        if s["style"] == "price":
            # a price board has rows, not one name
            assert s["rows"] and "derivation" in s
            continue
        assert s["text"] == s["text"].upper()
        assert len(s["text"]) <= 20, s["text"]


def test_every_sign_renders_with_the_built_in_font():
    """A character the font has no glyph for renders as a space, which is a
    silent hole in a shop's name -- so assert the font covers every one."""
    for s in _profile()["signs"]:
        words = ([s["text"]] if s.get("text") else
                 [r["grade"] for r in s.get("rows", [])]
                 + [r["price"] for r in s.get("rows", [])])
        for word in words:
            for ch in word:
                assert ch in sgn._FONT, (s["slug"], ch)


@pytest.mark.parametrize("style", ["panel", "neon"])
def test_a_sign_pack_carries_albedo_and_emissive(tmp_path, style):
    arrays = (sgn.neon_sign("CORNER TAP", 64) if style == "neon"
              else sgn.panel_sign("GOOSE MART", 64, panel="#c8102e",
                                  text_color="#fff6e5", border="#f2c00e"))
    man = sgn.build_sign_pack(str(tmp_path / "s"), arrays, "sign_probe")
    assert "albedo" in man["maps"] and "emissive" in man["maps"]
    assert man["import_hints"]["emissive"] is True
    assert man["tileable"] is None          # a sign is placed, never tiled


def test_the_signs_are_invented_and_say_so():
    """The one claim this file exists to keep true."""
    note = _profile()["description"].lower()
    assert "invented" in note and "not any company" in note


def test_a_price_board_reads_1997_and_carries_the_fraction():
    """The walker asked for 1997 prices specifically, so the profile carries
    the derivation and this asserts the number it derived."""
    price = [s for s in _profile()["signs"] if s.get("style") == "price"]
    assert price, "the theme names no fuel price board"
    board = price[0]
    grades = {r["grade"]: r["price"] for r in board["rows"]}
    assert grades["REGULAR"] == "1.21"
    assert float(grades["PLUS"]) - float(grades["REGULAR"]) == pytest.approx(0.10)
    assert float(grades["SUPER"]) - float(grades["PLUS"]) == pytest.approx(0.10)
    src = board["derivation"]
    assert "0.770" in src and "0.259" in src and "0.184" in src
    arrays = sgn.fuel_price_sign([(g, p) for g, p in grades.items()], (192, 256))
    assert "albedo" in arrays and "emissive" in arrays
    assert sgn.PRICE_FRACTION == "9"
