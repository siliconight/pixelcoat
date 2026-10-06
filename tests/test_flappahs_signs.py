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
