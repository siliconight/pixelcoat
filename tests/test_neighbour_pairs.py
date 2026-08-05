"""Neighbour pairs: a value step needs a reason the eye can see.

`judge` scores one grammar at a time, and every metric it owns can pass while
two surfaces that MEET on a wall read wrong together. The case that prompted
this, off the rockay contact sheet:

    concrete_polished_casino  vs  drywall_delco      dV 0.208  dHF 0.001
    concrete_polished_casino  vs  brick_glazed_green dV 0.220  dHF 0.089

Practically the same lightness step. The first reads as a texture that failed
to load; the second reads as a decision. The difference is entirely whether
anything ELSE changed across the boundary.

Two layers, tested separately. `neighbour_pairs` MEASURES and returns no
verdict; `pair_faults` judges. That split is deliberate: the thresholds in
`pair_faults` were calibrated from the measured distribution over all 387
environment-tier pairs in the shipped themes -- p10/p50/p90 of each gap --
and not from the standard's prose. The prose route was tried once for the
chroma budget, set it at 0.060, shipped, and passed a material that renders
bright green; it took a contact sheet to find 0.030.

The calibration is itself under test, so retuning into the noise floor or
past the median fails rather than quietly widening the net.

Run:  python -m pytest tests/test_neighbour_pairs.py
"""
import pytest

from tools import art_standard_audit as audit


def _row(gid, kind, value, hf, chroma=0.01, hue=90.0, strength=0.009):
    return {"id": gid, "kind": kind, "value_mean": value, "hf_energy": hf,
            "chroma_mean": chroma, "hue_deg": hue, "hue_strength": strength}


# --- hue distance -------------------------------------------------------

def test_hue_distance_wraps_the_short_way():
    """10 deg and 350 deg are 20 apart, not 340. Getting this backwards would
    call every pair of near-identical warm greys a hue contrast."""
    assert audit._hue_delta(10, 350) == 20.0
    assert audit._hue_delta(350, 10) == 20.0


def test_hue_distance_is_bounded_at_180():
    assert audit._hue_delta(0, 180) == 180.0
    assert audit._hue_delta(10, 200) == 170.0


# --- scope --------------------------------------------------------------

def test_only_environment_tier_surfaces_are_paired():
    """Glass is secondary and accents are exempt; neither forms the bulk read
    of a room, so pairing them against a wall would generate noise."""
    rows = [_row("wall_a", "concrete", 0.6, 0.03),
            _row("wall_b", "drywall", 0.8, 0.03),
            _row("a_window", "glass", 0.9, 0.20)]
    pairs = audit.neighbour_pairs(
        rows, {"concrete": "wall_a", "drywall": "wall_b", "glass": "a_window"})
    assert len(pairs) == 1
    assert {pairs[0]["a"], pairs[0]["b"]} == {"wall_a", "wall_b"}


def test_a_material_used_twice_in_a_theme_is_not_paired_with_itself():
    """A theme may name the same grammar for two kinds. That is one surface,
    not two that meet."""
    rows = [_row("shared", "concrete", 0.6, 0.03)]
    pairs = audit.neighbour_pairs(rows, {"concrete": "shared",
                                         "plaster": "shared"})
    assert pairs == []


def test_a_theme_naming_an_unknown_grammar_is_skipped_not_fatal():
    rows = [_row("wall_a", "concrete", 0.6, 0.03)]
    assert audit.neighbour_pairs(rows, {"concrete": "wall_a",
                                        "brick": "does_not_exist"}) == []


def test_no_theme_materials_is_no_pairs():
    assert audit.neighbour_pairs([], {}) == []
    assert audit.neighbour_pairs([], None) == []


# --- the measurement itself --------------------------------------------

def test_the_near_miss_pair_is_a_big_value_gap_across_no_structure():
    """The measured case. Not asserted as a FAILURE -- asserted as the shape
    the numbers must be able to express."""
    rows = [_row("concrete_polished_casino", "concrete", 0.620, 0.031,
                 chroma=0.010, hue=95.0),
            _row("drywall_delco", "drywall", 0.828, 0.030,
                 chroma=0.008, hue=92.0)]
    p, = audit.neighbour_pairs(rows, {"concrete": "concrete_polished_casino",
                                      "drywall": "drywall_delco"})
    assert p["d_value"] == pytest.approx(0.208, abs=0.001)
    assert p["d_hf"] < 0.005
    assert p["d_chroma"] < 0.005
    assert p["d_hue"] < 10.0


def test_the_same_value_gap_with_structure_is_a_different_animal():
    """The control. If this did not separate from the case above, the metric
    would be measuring nothing useful."""
    rows = [_row("concrete_polished_casino", "concrete", 0.620, 0.031,
                 chroma=0.010, hue=95.0),
            _row("brick_glazed_green", "brick", 0.400, 0.120,
                 chroma=0.028, hue=150.0, strength=0.027)]
    p, = audit.neighbour_pairs(rows, {"concrete": "concrete_polished_casino",
                                      "brick": "brick_glazed_green"})
    assert p["d_value"] == pytest.approx(0.220, abs=0.001)   # same step
    assert p["d_hf"] > 0.05                                   # different grain
    assert p["d_hue"] > 40.0                                  # different colour


# --- hue is not always meaningful --------------------------------------

def test_a_neutral_material_reports_no_hue_rather_than_a_wrong_one():
    """The hue ANGLE of a grey surface is noise. Reporting it as a number
    would let two greys look like a deliberate colour contrast. `None` says
    'not applicable', which a threshold can handle honestly."""
    rows = [_row("grey_a", "concrete", 0.5, 0.03, chroma=0.001,
                 hue=10.0, strength=0.0005),
            _row("wall_b", "drywall", 0.8, 0.03, chroma=0.010,
                 hue=95.0, strength=0.009)]
    p, = audit.neighbour_pairs(rows, {"concrete": "grey_a",
                                      "drywall": "wall_b"})
    assert p["d_hue"] is None


def test_hue_is_reported_when_both_sides_carry_colour():
    rows = [_row("a", "concrete", 0.5, 0.03, hue=20.0, strength=0.02),
            _row("b", "brick", 0.5, 0.03, hue=200.0, strength=0.02)]
    p, = audit.neighbour_pairs(rows, {"concrete": "a", "brick": "b"})
    assert p["d_hue"] == pytest.approx(180.0)


# --- the tool still reports rather than judges -------------------------

def test_neighbour_pairs_never_returns_a_verdict():
    """No `ok`, no `fault`, no threshold. If a later change adds one, it
    should have to come past this test and its reasoning."""
    rows = [_row("a", "concrete", 0.1, 0.03), _row("b", "drywall", 0.9, 0.03)]
    p, = audit.neighbour_pairs(rows, {"concrete": "a", "drywall": "b"})
    assert set(p) == {"a", "b", "d_value", "d_hf", "d_chroma", "d_hue"}


# --- the calibrated fault ----------------------------------------------

def test_a_value_step_with_no_reason_faults():
    """The pair a human spotted on a contact sheet, now caught by a number."""
    p = {"a": "concrete_polished_casino", "b": "drywall_delco",
         "d_value": 0.216, "d_hf": 0.001, "d_chroma": 0.007, "d_hue": 25.0}
    faults = audit.pair_faults([p])
    assert len(faults) == 1
    assert "value step 0.216 with no reason" in faults[0]


@pytest.mark.parametrize("channel,value", [
    ("d_hf", 0.090),        # different grain
    ("d_chroma", 0.075),    # different colour intensity
    ("d_hue", 121.0),       # different hue
])
def test_any_single_reason_excuses_the_step(channel, value):
    """One visible difference is enough. The eye does not need all three to
    read a boundary as intentional -- `brick_delco` / `tile_delco` carries the
    same 0.355 step as several flagged pairs and is obviously deliberate."""
    p = {"a": "x", "b": "y", "d_value": 0.355, "d_hf": 0.001,
         "d_chroma": 0.007, "d_hue": 5.0}
    p[channel] = value
    assert audit.pair_faults([p]) == []


def test_two_near_identical_materials_are_not_a_step():
    """Below the step threshold there is nothing to justify. Two surfaces that
    read as the same material are fine; it is the near-MISS that looks broken."""
    p = {"a": "x", "b": "y", "d_value": 0.012, "d_hf": 0.000,
         "d_chroma": 0.016, "d_hue": 15.0}
    assert audit.pair_faults([p]) == []


def test_an_unusable_hue_cannot_excuse_a_step():
    """`d_hue is None` means one side is too neutral for its angle to mean
    anything -- so hue is not available as a justification. Treating None as
    'differs' would let every pair of greys off."""
    p = {"a": "x", "b": "y", "d_value": 0.30, "d_hf": 0.001,
         "d_chroma": 0.002, "d_hue": None}
    assert len(audit.pair_faults([p])) == 1


def test_thresholds_sit_between_the_measured_p10_and_p50():
    """Calibration guard. These numbers came from the distribution over 387
    real pairs, not from the standard's prose -- the way the chroma budget was
    first set, which shipped a bright green wall. If someone retunes them into
    the noise floor (p10) or past the median, this says so."""
    assert 0.018 < audit.PAIR_VALUE_STEP < 0.217      # d_value  p10 .. p50
    assert 0.004 < audit.PAIR_HF_DIFF < 0.027         # d_hf     p10 .. p50
    assert 0.005 < audit.PAIR_CHROMA_DIFF < 0.024     # d_chroma p10 .. p50


def test_no_pairs_is_no_faults():
    assert audit.pair_faults([]) == []
    assert audit.pair_faults(None) == []
