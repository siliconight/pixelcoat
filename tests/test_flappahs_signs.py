"""A gas station's and a convenience store's fascia always read FLAPPAHS
(0.58.0).

The walker, 2026-10-06: "Flappahs store always Flappahs". Zoo builds every
station's pumps, pylon, coffee island and slush machine in the brand, so one
brand per site means the fascia says it too. `delco_1997`, the theme nearly
every brief names, had no FLAPPAHS sign at all: cold run 9165 dealt the
Flappahs store, then `gas_station_a03`, LUBE-N-GO (`b0=lube_n_go`).
"""
import json
from pathlib import Path

import pytest

SIGNS = Path(__file__).resolve().parents[1] / "profiles" / "signs"
PROFILES = sorted(SIGNS.glob("*.json"))


def _named(profile, family):
    data = json.loads(profile.read_text(encoding="utf-8"))
    return sorted(s["text"] for s in data["signs"]
                  if family in (s.get("families") or []) and s.get("text"))


@pytest.mark.parametrize("profile", PROFILES, ids=lambda p: p.stem)
@pytest.mark.parametrize("family", ["gas_station", "convenience"])
def test_a_station_and_a_store_name_only_flappahs(profile, family):
    named = _named(profile, family)
    assert named in ([], ["FLAPPAHS"]), (profile.stem, family, named)


def test_the_theme_briefs_use_has_the_brand():
    assert _named(SIGNS / "delco_1997.json", "gas_station") == ["FLAPPAHS"]
    assert _named(SIGNS / "delco_1997.json", "convenience") == ["FLAPPAHS"]


def _zoo_colourway_0():
    """Zoo's `price_pylon_forms.COLOURWAYS[0]` -- (field, rule, ink) -- read
    as source from a Zoo checkout above this repo, or None."""
    import ast
    for parent in Path(__file__).resolve().parents:
        src = parent / "zoo" / "zoo_keeper" / "core" / "price_pylon_forms.py"
        if src.is_file():
            tree = ast.parse(src.read_text(encoding="utf-8"))
            for n in tree.body:
                if isinstance(n, ast.Assign) and any(getattr(t, "id", None) == "COLOURWAYS"
                                                     for t in n.targets):
                    return ast.literal_eval(n.value)[0]
    return None


@pytest.mark.parametrize("profile", PROFILES, ids=lambda p: p.stem)
def test_the_brand_is_cream_on_green_as_zoo_draws_it(profile):
    """0.60.0. The walker, 2026-10-06: "We can do the green and cream".
    The band draws in the colours Zoo gives the pylon, the pumps and the door
    box, read from Zoo rather than copied, so the two cannot drift."""
    cw = _zoo_colourway_0()
    if cw is None:
        pytest.skip("no Zoo checkout above this repo")
    hexed = ["#%02x%02x%02x" % tuple(c) for c in cw]
    data = json.loads(profile.read_text(encoding="utf-8"))
    flap = [s for s in data["signs"] if s.get("slug") == "flappahs"]
    if not flap:
        pytest.skip(f"{profile.stem} names no FLAPPAHS")
    s = flap[0]
    assert [s["panel"].lower(), s["border"].lower(), s["text_color"].lower()] == hexed, s
    assert (SIGNS / s["mark"]).is_file()
