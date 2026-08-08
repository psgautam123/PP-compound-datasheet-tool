"""Step 1: exact-grade search (Workflow2.txt §6).

Deterministic property-filter search over already-parsed grades -- no PDF
scanning or LLM calls at request time (see architecture plan §3). A grade
"matches" when every user-specified property is within the acceptable
margin of the target value. If the caller gets zero matches back, that is
the trigger to fall through to Step 2 (predictor.predict_blend).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import Grade, PropertyValue
from .property_taxonomy import ACCEPTABLE_MARGIN_FRACTION

# Default condition used to disambiguate properties reported at multiple
# temperatures (e.g. tensile_modulus at 23°C and 80°C on STAMAX grades)
# when the caller doesn't specify one -- room temperature is what a vendor
# means by an unqualified spec in the overwhelming majority of cases.
DEFAULT_CONDITION: dict[str, Any] = {"temp_C": 23}


@dataclass
class PropertyMatch:
    key: str
    target: float
    actual: float
    relative_error: float
    within_margin: bool


@dataclass
class GradeMatch:
    grade: Grade
    matches: list[PropertyMatch]
    max_relative_error: float = field(init=False)

    def __post_init__(self) -> None:
        self.max_relative_error = max((m.relative_error for m in self.matches), default=0.0)

    @property
    def source_pdf(self) -> str:
        return self.grade.source_pdf


def _resolve_property(grade: Grade, key: str, condition: dict[str, Any] | None) -> PropertyValue | None:
    """Pick the single reported value for `key` to compare against, given an
    optional explicit condition override. Falls back to the 23°C reading
    when a property has multiple temperature entries and none was
    requested; if it's genuinely ambiguous (multiple entries, no 23°C
    reading, no override), refuses to guess and returns None.
    """
    if condition:
        return grade.get_one(key, **condition)

    all_values = grade.get(key)
    if not all_values:
        return None
    if len(all_values) == 1:
        return all_values[0]

    at_room_temp = grade.get_one(key, **DEFAULT_CONDITION)
    return at_room_temp  # None if ambiguous and no 23°C reading exists


def search_grades(
    target_properties: dict[str, float],
    grades: list[Grade],
    conditions: dict[str, dict[str, Any]] | None = None,
    tolerance_fraction: float = ACCEPTABLE_MARGIN_FRACTION,
) -> list[GradeMatch]:
    """Return every grade whose reported values for ALL of
    `target_properties` fall within `tolerance_fraction` of the target,
    best match (lowest max relative error) first. Empty list means no
    exact-grade match was found -> Step 2.

    `conditions` optionally maps a property key to an explicit condition
    filter (e.g. {"tensile_modulus": {"temp_C": 80}}) to disambiguate
    multi-temperature properties instead of the 23°C default.
    """
    conditions = conditions or {}
    results: list[GradeMatch] = []

    for grade in grades:
        matches: list[PropertyMatch] = []
        disqualified = False

        for key, target in target_properties.items():
            prop = _resolve_property(grade, key, conditions.get(key))
            if prop is None:
                disqualified = True
                break

            rel_err = abs(prop.value - target) / target if target else 0.0
            within = rel_err <= tolerance_fraction
            if not within:
                disqualified = True
                break

            matches.append(
                PropertyMatch(key=key, target=target, actual=prop.value, relative_error=rel_err, within_margin=within)
            )

        if not disqualified and matches:
            results.append(GradeMatch(grade=grade, matches=matches))

    results.sort(key=lambda gm: gm.max_relative_error)
    return results


def find_best_match(
    target_properties: dict[str, float],
    grades: list[Grade],
    conditions: dict[str, dict[str, Any]] | None = None,
    tolerance_fraction: float = ACCEPTABLE_MARGIN_FRACTION,
) -> GradeMatch | None:
    matches = search_grades(target_properties, grades, conditions, tolerance_fraction)
    return matches[0] if matches else None
