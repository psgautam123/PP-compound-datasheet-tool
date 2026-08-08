"""Integration tests for engine.predictor against the real extracted
datasheet fixtures (backend/data/datasheets.json, 18 SABIC PP grades).

Strategy: rather than hand-deriving expected blend values for every
property (error-prone for the more involved formulas), each test computes
its "expected" values by calling the same underlying blend_rules functions
directly against real datasheet numbers pulled straight off the loaded
Grade objects. This cross-checks predictor.py's orchestration (dict-key
routing, anchor lookup, condition filtering, primary-property solving)
against the formulas it's supposed to be wiring together, using real
(not synthetic) data.
"""
from __future__ import annotations

import pytest

from engine import blend_rules as br
from engine.data_loader import load_grades
from engine.predictor import find_unfilled_anchor, predict_blend, screen_candidate_pairs


@pytest.fixture(scope="module")
def all_grades():
    return load_grades()


@pytest.fixture(scope="module")
def by_id(all_grades):
    return {g.grade_id: g for g in all_grades}


# ---------------------------------------------------------------------------
# Data sanity (guards against the fixture file silently changing shape)
# ---------------------------------------------------------------------------


def test_loads_18_unique_grades(all_grades):
    assert len(all_grades) == 18
    assert len({g.grade_id for g in all_grades}) == 18


def test_h1015_matches_hand_read_reference(by_id):
    h1015 = by_id["H1015"]
    assert h1015.family == "homopolymer"
    assert h1015.filler_type == "glass_fiber_short"
    assert h1015.filler_content_pct == 15
    assert h1015.density_kg_m3 == 1100
    assert h1015.get_one("mfr").value == 15
    assert h1015.get_one("tensile_modulus").value == 4700
    assert h1015.get_one("flexural_modulus").value == 4500
    assert h1015.get_one("izod_notched", temp_C=23).value == 6.3
    assert h1015.get_one("hdt_a").value == 140
    assert h1015.get_one("hdt_b").value == 155


def test_no_yield_rows_are_dropped_not_zeroed(by_id):
    # H1015's tensile_stress_yield is reported as "No Yield" -> should be
    # absent entirely, not silently coerced to 0.
    assert by_id["H1015"].get("tensile_stress_yield") == []


# ---------------------------------------------------------------------------
# Candidate pair screening
# ---------------------------------------------------------------------------


def test_screen_candidate_pairs_brackets_target(all_grades):
    pairs = screen_candidate_pairs(all_grades, "mfr", target_value=12)
    assert pairs, "expected at least one bracketing pair for mfr=12"
    for grade_a, grade_b, val_a, val_b in pairs:
        assert val_a <= 12 <= val_b
    # sorted tightest-bracket-first
    spans = [vb - va for _, _, va, vb in pairs]
    assert spans == sorted(spans)


def test_screen_candidate_pairs_within_compatible_subset_is_deterministic(by_id):
    subset = [by_id[g] for g in ("H1015", "H1020", "H1025", "H1090", "G3230A")]
    pairs = screen_candidate_pairs(subset, "mfr", target_value=12)
    # H1015 (mfr=15) is the only subset grade at/above the target, so every
    # lower-mfr grade pairs with it; the tightest bracket (smallest span)
    # must sort first.
    assert len(pairs) == 4
    grade_a, grade_b, val_a, val_b = pairs[0]
    assert (grade_a.grade_id, grade_b.grade_id) == ("G3230A", "H1015")
    assert (val_a, val_b) == (11, 15)


# ---------------------------------------------------------------------------
# Full predict_blend orchestration, cross-checked against direct blend_rules
# calls on the same real datasheet numbers (G3230A / H1015 pair, target
# mfr=12 -- see test above for why this pair is the deterministic bracket
# within the glass-fiber-short homopolymer family).
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def g3230a_h1015_subset(by_id):
    return [by_id[g] for g in ("H1015", "H1020", "H1025", "H1090", "G3230A")]


def test_predict_blend_self_consistent_mfr_and_flexural_modulus(g3230a_h1015_subset, by_id):
    g3230a, h1015 = by_id["G3230A"], by_id["H1015"]
    phi_a = br.solve_phi_a_log_additive(12, 11, 15)  # grade_a=G3230A(11), grade_b=H1015(15)
    expected_flex = br.linear_rule_of_mixtures(
        g3230a.get_one("flexural_modulus").value, h1015.get_one("flexural_modulus").value, phi_a
    )

    result = predict_blend({"mfr": 12, "flexural_modulus": expected_flex}, g3230a_h1015_subset)

    assert result is not None
    assert (result.grade_a.grade_id, result.grade_b.grade_id) == ("G3230A", "H1015")
    assert result.phi_a == pytest.approx(phi_a, rel=1e-6)
    assert result.within_tolerance
    by_key = {p.key: p for p in result.predictions}
    assert by_key["mfr"].predicted == pytest.approx(12, rel=1e-6)
    assert by_key["flexural_modulus"].predicted == pytest.approx(expected_flex, rel=1e-6)
    assert by_key["flexural_modulus"].method == "linear_rom"


def test_predict_blend_self_consistent_multi_property(g3230a_h1015_subset, by_id):
    g3230a, h1015 = by_id["G3230A"], by_id["H1015"]
    phi_a = br.solve_phi_a_log_additive(12, 11, 15)

    expected_flex = br.linear_rule_of_mixtures(
        g3230a.get_one("flexural_modulus").value, h1015.get_one("flexural_modulus").value, phi_a
    )
    expected_tsb = br.linear_rule_of_mixtures(
        g3230a.get_one("tensile_stress_break").value, h1015.get_one("tensile_stress_break").value, phi_a
    )
    expected_clte = br.linear_rule_of_mixtures(
        g3230a.get_one("clte").value, h1015.get_one("clte").value, phi_a
    )
    n = br.calibrate_hdt_exponent(
        g3230a.get_one("flexural_modulus").value,
        g3230a.get_one("hdt_a").value,
        h1015.get_one("flexural_modulus").value,
        h1015.get_one("hdt_a").value,
    )
    expected_hdt = br.hdt_power_law(g3230a.get_one("hdt_a").value, g3230a.get_one("flexural_modulus").value, expected_flex, n)

    targets = {
        "mfr": 12,
        "flexural_modulus": expected_flex,
        "hdt_a": expected_hdt,
        "tensile_stress_break": expected_tsb,
        "clte": expected_clte,
    }
    result = predict_blend(targets, g3230a_h1015_subset)

    assert result is not None
    assert result.within_tolerance
    by_key = {p.key: p for p in result.predictions}
    assert by_key["hdt_a"].predicted == pytest.approx(expected_hdt, rel=1e-6)
    assert by_key["hdt_a"].method == "hdt_power_law_calibrated"
    assert by_key["tensile_stress_break"].predicted == pytest.approx(expected_tsb, rel=1e-6)
    assert by_key["clte"].predicted == pytest.approx(expected_clte, rel=1e-6)


def test_predict_blend_mismatched_impact_type_fails_gracefully(g3230a_h1015_subset):
    # G3230A reports Charpy, H1015 reports Izod -- the pair can't produce a
    # like-for-like impact prediction, so this must not silently mix them.
    result = predict_blend({"mfr": 12, "izod_notched": 5.0}, g3230a_h1015_subset)
    assert result is None


def test_predict_blend_infeasible_target_returns_none(by_id):
    # tensile_modulus isn't reported for G3230A at all, and it's the only
    # other grade to pair with H1015 here, so no pair can satisfy a
    # tensile_modulus target -> Step 3 trigger.
    subset = [by_id["G3230A"], by_id["H1015"]]
    result = predict_blend({"mfr": 12, "tensile_modulus": 5000}, subset)
    assert result is None


def test_predict_blend_no_bracket_returns_none(by_id):
    # H1090 (mfr=2) is the lowest MFR in the whole dataset -- nothing brackets
    # a target below it.
    result = predict_blend({"mfr": 0.5}, [by_id["H1090"], by_id["H1015"]])
    assert result is None


# ---------------------------------------------------------------------------
# Unfilled-anchor lookup (used by exponential-decay impact/strain properties)
# ---------------------------------------------------------------------------


def test_find_unfilled_anchor_prefers_same_family(all_grades, by_id):
    anchor = find_unfilled_anchor(all_grades, family="copolymer", target_mfr=13)
    assert anchor is not None
    assert anchor.filler_type == "none"
    assert anchor.family == "copolymer"
    assert anchor.grade_id == "H1200"  # only unfilled copolymer, mfr=13 exact match


def test_find_unfilled_anchor_falls_back_across_family_when_none_available(all_grades):
    # no unfilled homopolymer exists in this dataset (see extraction_notes.md)
    anchor = find_unfilled_anchor(all_grades, family="homopolymer", target_mfr=12)
    assert anchor is not None
    assert anchor.filler_type == "none"
    assert anchor.family != "homopolymer"
