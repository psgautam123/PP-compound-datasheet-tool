"""Tests for Step 1 exact-grade search (engine.search) against the real
extracted datasheet fixtures.
"""
from __future__ import annotations

import pytest

from engine.data_loader import load_grades
from engine.search import find_best_match, search_grades


@pytest.fixture(scope="module")
def all_grades():
    return load_grades()


@pytest.fixture(scope="module")
def by_id(all_grades):
    return {g.grade_id: g for g in all_grades}


def test_exact_match_returns_source_grade(all_grades):
    match = find_best_match({"mfr": 15, "tensile_modulus": 4700}, all_grades)
    assert match is not None
    assert match.grade.grade_id == "H1015"
    assert match.source_pdf == "SABIC-EE-MF15-SGF15-H1015.pdf"
    assert match.max_relative_error == pytest.approx(0.0, abs=1e-9)


def test_within_tolerance_fuzzy_match(all_grades):
    # 3% off H1015's true values (mfr=15, tensile_modulus=4700) -> still a match
    match = find_best_match({"mfr": 15.4, "tensile_modulus": 4830}, all_grades)
    assert match is not None
    assert match.grade.grade_id == "H1015"
    assert match.max_relative_error <= 0.05


def test_outside_tolerance_is_not_a_match(all_grades):
    match = find_best_match({"mfr": 15, "tensile_modulus": 4700 * 1.20}, all_grades)
    assert match is None or match.grade.grade_id != "H1015"


def test_no_grade_satisfies_impossible_combination_returns_empty(all_grades):
    # No single commercial grade combines mfr=15 with an HDT of 300°C
    matches = search_grades({"mfr": 15, "hdt_a": 300}, all_grades)
    assert matches == []


def test_multi_property_intersection_excludes_partial_matches(by_id):
    # H1015 matches mfr+tensile_modulus but NOT hdt_a=48 (H1200's value,
    # not H1015's 140) -- intersection across all three must exclude it.
    grades = [by_id["H1015"], by_id["H1200"]]
    matches = search_grades({"mfr": 15, "tensile_modulus": 4700, "hdt_a": 48}, grades)
    assert matches == []


def test_default_condition_picks_room_temperature_reading(by_id):
    stamax = by_id["30YH530"]
    # tensile_modulus is reported at both 23°C (7400) and 80°C (4500);
    # an unqualified target of 7400 should resolve against the 23°C value.
    match = find_best_match({"tensile_modulus": 7400}, [stamax])
    assert match is not None
    assert match.matches[0].actual == 7400


def test_explicit_condition_overrides_default(by_id):
    stamax = by_id["30YH530"]
    match = find_best_match({"tensile_modulus": 4500}, [stamax], conditions={"tensile_modulus": {"temp_C": 80}})
    assert match is not None
    assert match.matches[0].actual == 4500


def test_unqualified_target_does_not_falsely_match_the_80c_reading(by_id):
    stamax = by_id["30YH530"]
    # Without an explicit condition, 4500 (the 80°C value) must NOT match
    # against the default 23°C resolution (7400) -- that would be a 39% miss.
    matches = search_grades({"tensile_modulus": 4500}, [stamax])
    assert matches == []


def test_property_not_reported_on_grade_disqualifies_it(by_id):
    # 30YH530 (STAMAX LGF) reports no MFR at all.
    matches = search_grades({"mfr": 10}, [by_id["30YH530"]])
    assert matches == []


def test_results_sorted_best_match_first(all_grades):
    # Multiple homopolymer/glass-fiber grades cluster around mfr~10-11;
    # best match (lowest error) must sort first.
    matches = search_grades({"mfr": 10}, all_grades)
    assert len(matches) > 1
    errors = [m.max_relative_error for m in matches]
    assert errors == sorted(errors)
