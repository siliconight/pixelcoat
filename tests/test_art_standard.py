"""The Controlled Contrast standard, as a regression gate.

`tools/art_standard_audit.py` measures every shipped grammar against the
standard's environment-tier budget: chroma, value range, crushed and blown
pixels, edge density, roughness, emissive. Thirty of fifty-one grammars are over
budget today, and asserting the budget itself would put main permanently red --
which is how a check stops being read.

So these tests assert NO REGRESSION against `tools/art_standard_baseline.json`
instead. The budget is what you burn the baseline down toward; the baseline is
what stops it drifting back up while you do. Improving a grammar is always
allowed and never fails; making one louder, glossier, wider-ranged or emissive
fails and names the metric.

To accept a deliberate regression, re-snapshot:

    python -m tools.art_standard_audit --size 256 \\
        --write-baseline tools/art_standard_baseline.json

...and say why in the commit message. That is the whole ceremony, and it is
meant to be visible in review rather than silent.
"""

import json
import os

import pytest

from tools import art_standard_audit as audit

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_BASELINE = os.path.join(_ROOT, "tools", "art_standard_baseline.json")
_MATERIALS = os.path.join(_ROOT, "profiles", "materials")
_THEMES = os.path.join(_ROOT, "profiles", "themes")


@pytest.fixture(scope="module")
def baseline():
    if not os.path.isfile(_BASELINE):
        pytest.skip("no committed baseline")
    with open(_BASELINE, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def result(baseline):
    # Run at the baseline's own size and seed -- synthesis is deterministic, but
    # only at the same resolution. `regressions` raises if they disagree; this
    # fixture makes sure they cannot.
    return audit.audit(_MATERIALS, _THEMES,
                       size=baseline["size"], seed=baseline["seed"])


def test_no_grammar_got_louder(result, baseline):
    regs = audit.regressions(result, baseline)
    assert not regs, "\n  " + "\n  ".join(regs)


def test_no_grammar_silently_disappeared(result, baseline):
    """A grammar the baseline covers and this run does not is a deletion or a
    rename. Either is fine -- but it should be a decision, not a diff nobody
    noticed."""
    gone = audit.dropped(result, baseline)
    assert not gone, f"in the baseline but not measured: {gone}"


def test_baseline_size_mismatch_is_an_error_not_a_pass(result, baseline):
    """The failure mode this guards: re-run at a different --size, every
    number moves, and a naive comparison reads it as a library-wide
    regression -- or worse, as a pass."""
    wrong = dict(baseline, size=baseline["size"] * 2)
    with pytest.raises(ValueError, match="not comparable"):
        audit.regressions(result, wrong)


def test_the_gate_actually_fires():
    """Prove the detector, on a synthetic row -- so a refactor that quietly
    stops comparing anything fails here instead of passing everywhere."""
    base = {"size": 256, "seed": 1999,
            "materials": {"x": {"chroma_mean": 0.010, "hf_energy": 0.010,
                                "rough_mean": 0.90, "emissive": False}}}
    worse = {"size": 256, "seed": 1999, "materials": [
        {"id": "x", "kind": "brick", "chroma_mean": 0.200, "chroma_p95": 0.0,
         "value_range": 0.0, "crushed_frac": 0.0, "blown_frac": 0.0,
         "hf_energy": 0.300, "rough_mean": 0.10, "emissive": True}]}
    regs = audit.regressions(worse, base)
    assert len(regs) == 4, regs                  # chroma, hf, roughness, emissive
    assert any("chroma_mean" in r for r in regs)
    assert any("glossier" in r for r in regs)
    assert any("emissive" in r for r in regs)


def test_improving_a_grammar_never_fails():
    base = {"size": 256, "seed": 1999,
            "materials": {"x": {"chroma_mean": 0.200, "hf_energy": 0.300,
                                "rough_mean": 0.10, "emissive": True}}}
    better = {"size": 256, "seed": 1999, "materials": [
        {"id": "x", "kind": "brick", "chroma_mean": 0.010, "chroma_p95": 0.0,
         "value_range": 0.0, "crushed_frac": 0.0, "blown_frac": 0.0,
         "hf_energy": 0.010, "rough_mean": 0.90, "emissive": False}]}
    assert audit.regressions(better, base) == []


def test_a_new_grammar_is_not_a_regression():
    """New materials are judged by the budget (the report), not by a baseline
    that has never seen them."""
    base = {"size": 256, "seed": 1999, "materials": {}}
    fresh = {"size": 256, "seed": 1999, "materials": [
        {"id": "brand_new", "kind": "brick", "chroma_mean": 0.9,
         "chroma_p95": 0.9, "value_range": 0.9, "crushed_frac": 0.9,
         "blown_frac": 0.9, "hf_energy": 0.9, "rough_mean": 0.0,
         "emissive": True}]}
    assert audit.regressions(fresh, base) == []
