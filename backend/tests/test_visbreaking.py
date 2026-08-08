"""Tests for Step 3 reactive-extrusion/visbreaking (engine.visbreaking),
against both hand-computed formula checks and the real datasheet fixtures.
"""
from __future__ import annotations

import math

import pytest

from engine.data_loader import load_grades
from engine import visbreaking as vb


@pytest.fixture(scope="module")
def all_grades():
    return load_grades()


@pytest.fixture(scope="module")
def by_id(all_grades):
    return {g.grade_id: g for g in all_grades}


# ---------------------------------------------------------------------------
# Dose scaling formulas
# ---------------------------------------------------------------------------


def test_scale_factor_is_unity_at_reference_conditions():
    assert vb._dose_scale_factor(vb.REFERENCE_TEMP_C, vb.REFERENCE_RESIDENCE_TIME_MIN) == pytest.approx(1.0)


def test_ten_degree_rise_roughly_doubles_effective_dose():
    # Workflow2.txt §52: "10 C rise roughly doubles effective dose."
    s1 = vb._dose_scale_factor(220, 2.0)
    s2 = vb._dose_scale_factor(230, 2.0)
    assert 1.5 <= (s2 / s1) <= 2.5


def test_injection_molding_needs_two_to_three_times_the_dose():
    # Workflow2.txt §56: injection molding (short residence) needs ~2-3x
    # the reactive-extrusion dose for the same MFI shift.
    dose_re = vb.solve_peroxide_dose(15, 21, "homopolymer", **vb.PROCESS_PRESETS["reactive_extrusion"])
    dose_im = vb.solve_peroxide_dose(15, 21, "homopolymer", **vb.PROCESS_PRESETS["injection_molding"])
    assert 2.0 <= (dose_im / dose_re) <= 3.0


def test_predict_and_solve_round_trip():
    dose = vb.solve_peroxide_dose(15, 21, "homopolymer", temp_C=225, residence_time_min=1.5)
    mfi = vb.predict_mfi_after_visbreaking(15, dose, "homopolymer", temp_C=225, residence_time_min=1.5)
    assert mfi == pytest.approx(21, rel=1e-9)


def test_solve_peroxide_dose_rejects_target_at_or_below_baseline():
    with pytest.raises(ValueError):
        vb.solve_peroxide_dose(15, 15, "homopolymer")
    with pytest.raises(ValueError):
        vb.solve_peroxide_dose(15, 10, "homopolymer")


def test_homopolymer_shifts_mfi_more_than_impact_pp_at_same_dose():
    # coefficient 9.5 (homopolymer) vs 7.0 (impact PP), Workflow2.txt §38, §46
    homo = vb.predict_mfi_after_visbreaking(15, 0.1, "homopolymer")
    impact = vb.predict_mfi_after_visbreaking(15, 0.1, "impact_copolymer")
    assert homo > impact > 15


def test_unknown_family_raises():
    with pytest.raises(ValueError):
        vb.peroxide_coefficient_for_family("unobtainium")


# ---------------------------------------------------------------------------
# Base-grade screening against real datasheet data
# ---------------------------------------------------------------------------


def test_screen_finds_lower_mfr_higher_modulus_grades_only(all_grades):
    candidates = vb.screen_visbreaking_base_grades({"mfr": 20, "tensile_modulus": 4000}, all_grades)
    assert [g.grade_id for g in candidates] == ["H1015", "H1020", "H1025", "H1090"]
    for g in candidates:
        assert g.get_one("mfr").value < 20
        assert g.get_one("tensile_modulus").value >= 4000


def test_screen_sorted_by_smallest_mfr_gap_first(all_grades):
    candidates = vb.screen_visbreaking_base_grades({"mfr": 20, "tensile_modulus": 4000}, all_grades)
    gaps = [20 - g.get_one("mfr").value for g in candidates]
    assert gaps == sorted(gaps)
    assert candidates[0].grade_id == "H1015"  # mfr=15, smallest gap to 20


def test_screen_excludes_grade_missing_modulus_data(all_grades):
    # G3230A (mfr=11) would otherwise qualify on MFR alone against a high
    # target, but reports no tensile_modulus -- must be excluded rather
    # than assumed to pass, when a modulus target is specified.
    candidates = vb.screen_visbreaking_base_grades({"mfr": 30, "tensile_modulus": 1}, all_grades)
    assert "G3230A" not in [g.grade_id for g in candidates]


def test_screen_without_modulus_target_ignores_modulus(all_grades):
    candidates = vb.screen_visbreaking_base_grades({"mfr": 12}, all_grades)
    assert "G3230A" in [g.grade_id for g in candidates]  # mfr=11 < 12, no modulus filter applied


def test_screen_requires_mfr_target():
    with pytest.raises(ValueError):
        vb.screen_visbreaking_base_grades({"tensile_modulus": 4000}, [])


# ---------------------------------------------------------------------------
# End-to-end proposal
# ---------------------------------------------------------------------------


def test_propose_visbreaking_end_to_end_matches_manual_calc(all_grades, by_id):
    result = vb.propose_visbreaking({"mfr": 20, "tensile_modulus": 4000}, all_grades)
    assert result is not None
    assert result.base_grade.grade_id == "H1015"
    assert result.final_mfi_design_point == pytest.approx(20 * 1.05)

    expected_dose = vb.solve_peroxide_dose(
        by_id["H1015"].get_one("mfr").value, 21.0, "homopolymer", temp_C=220.0, residence_time_min=2.0
    )
    assert result.peroxide_dose_wt_pct == pytest.approx(expected_dose)


def test_propose_visbreaking_returns_none_when_no_base_grade_qualifies(all_grades):
    # nothing in the dataset has mfr below 1
    result = vb.propose_visbreaking({"mfr": 1}, all_grades)
    assert result is None


def test_propose_visbreaking_rejects_overshoot_outside_workflow_band(all_grades):
    with pytest.raises(ValueError):
        vb.propose_visbreaking({"mfr": 20}, all_grades, overshoot_fraction=0.25)


def test_propose_visbreaking_rejects_unknown_process(all_grades):
    with pytest.raises(ValueError):
        vb.propose_visbreaking({"mfr": 20}, all_grades, process="blow_molding")


# ---------------------------------------------------------------------------
# DOE generation
# ---------------------------------------------------------------------------


def test_doe_is_a_full_factorial_of_dose_and_residence_time(all_grades):
    result = vb.propose_visbreaking({"mfr": 20, "tensile_modulus": 4000}, all_grades)
    assert len(result.doe) == len(vb.DOE_FACTOR_LEVELS) ** 2

    doses = sorted({round(r.dose_wt_pct, 6) for r in result.doe})
    times = sorted({round(r.residence_time_min, 6) for r in result.doe})
    assert len(doses) == len(vb.DOE_FACTOR_LEVELS)
    assert len(times) == len(vb.DOE_FACTOR_LEVELS)

    # center point (nominal dose AND nominal residence time) matches the
    # base proposal exactly
    center = [
        r
        for r in result.doe
        if r.dose_wt_pct == pytest.approx(result.peroxide_dose_wt_pct)
        and r.residence_time_min == pytest.approx(result.residence_time_min)
    ]
    assert len(center) == 1
    assert center[0].predicted_mfi == pytest.approx(result.final_mfi_design_point, rel=1e-6)


def test_doe_temperature_held_fixed_not_percentage_scaled(all_grades):
    # Percentage-scaling Celsius is physically unsound (arbitrary zero) and
    # can exceed a grade's processing ceiling -- temperature must be
    # constant across every DOE run.
    result = vb.propose_visbreaking({"mfr": 20, "tensile_modulus": 4000}, all_grades)
    temps = {r.temp_C for r in result.doe}
    assert temps == {result.temp_C}


def test_doe_dose_and_time_bounds_are_within_20_percent(all_grades):
    result = vb.propose_visbreaking({"mfr": 20, "tensile_modulus": 4000}, all_grades)
    for r in result.doe:
        assert r.dose_wt_pct == pytest.approx(result.peroxide_dose_wt_pct, rel=0.20 + 1e-9) or \
            0.80 * result.peroxide_dose_wt_pct <= r.dose_wt_pct <= 1.20 * result.peroxide_dose_wt_pct
        assert 0.80 * result.residence_time_min <= r.residence_time_min <= 1.20 * result.residence_time_min


def test_no_solution_prompt_text_matches_workflow():
    assert vb.NO_SOLUTION_PROMPT.startswith("No solution was found.")
    assert "peroxides" in vb.NO_SOLUTION_PROMPT
    assert "visbreaking" in vb.NO_SOLUTION_PROMPT
