"""One name list (0.61.0): a band is dealt from the names Zoo paints over the
door, for every kind Zoo names.

The walker, 2026-10-06, option A: one list names a building on both its
signs, and it is the door box's -- Zoo's `storefront_names.KINDS`, read here
as source so the two cannot drift. Level Factory 0.148.0 deals each shell one
business and hands the same pack to its door box (Zoo 1.79.0).
"""
import ast
import json
from pathlib import Path

import pytest

SIGNS = Path(__file__).resolve().parents[1] / "profiles" / "signs"
PROFILES = [SIGNS / "delco.json", SIGNS / "delco_1997.json"]
FAMILY_OF = {"deli": "deli", "pizza": "pizza", "bank": "bank", "pawn": "pawn",
             "market": "supermarket", "pharmacy": "pharmacy", "card": "card",
             "video": "video", "brewery": "brewery"}


def _zoo_kinds():
    for parent in Path(__file__).resolve().parents:
        src = parent / "zoo" / "zoo_keeper" / "core" / "storefront_names.py"
        if src.is_file():
            tree = ast.parse(src.read_text(encoding="utf-8"))
            for n in tree.body:
                if isinstance(n, ast.Assign) and any(getattr(t, "id", None) == "KINDS"
                                                     for t in n.targets):
                    out = {}
                    for el in n.value.elts:
                        try:
                            out[ast.literal_eval(el.elts[0])] = list(ast.literal_eval(el.elts[2]))
                        except (ValueError, TypeError):
                            continue
                    return out
    return None


@pytest.mark.parametrize("profile", PROFILES, ids=lambda p: p.stem)
@pytest.mark.parametrize("kind", sorted(FAMILY_OF))
def test_a_family_zoo_names_holds_exactly_zoos_names(profile, kind):
    kinds = _zoo_kinds()
    if kinds is None:
        pytest.skip("no Zoo checkout above this repo")
    assert kind in kinds, f"Zoo no longer names {kind!r}; this map is stale"
    data = json.loads(profile.read_text(encoding="utf-8"))
    family = FAMILY_OF[kind]
    got = [s["text"] for s in data["signs"] if family in (s.get("families") or [])]
    assert got == kinds[kind], (profile.stem, family, got)


@pytest.mark.parametrize("profile", PROFILES, ids=lambda p: p.stem)
def test_the_brand_green_is_flappahs_alone(profile):
    data = json.loads(profile.read_text(encoding="utf-8"))
    green = [s["slug"] for s in data["signs"] if str(s.get("panel", "")).lower() == "#184e34"]
    assert green == ["flappahs"], green
