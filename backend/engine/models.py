"""Core data model for grades and their reported properties.

Mirrors the `properties`/`grades` shape described in the architecture plan:
one row per reported value (so multi-temperature entries and sparse property
sets are handled naturally) rather than a fixed-column schema.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PropertyValue:
    key: str
    cls: str
    value: float
    unit: str
    condition: dict[str, Any] = field(default_factory=dict)
    test_method: str | None = None

    def condition_matches(self, **filters: Any) -> bool:
        return all(self.condition.get(k) == v for k, v in filters.items())


@dataclass(frozen=True)
class Grade:
    grade_id: str
    product_name: str
    source_pdf: str
    family: str
    filler_type: str
    filler_content_pct: float | None
    density_kg_m3: float | None
    mould_shrinkage_pct: float | None
    properties: tuple[PropertyValue, ...]

    def get(self, key: str, **condition_filters: Any) -> list[PropertyValue]:
        """All reported values for `key`, optionally narrowed by condition
        (e.g. get("tensile_modulus", temp_C=23))."""
        return [
            p
            for p in self.properties
            if p.key == key and p.condition_matches(**condition_filters)
        ]

    def get_one(self, key: str, **condition_filters: Any) -> PropertyValue | None:
        matches = self.get(key, **condition_filters)
        return matches[0] if matches else None

    def volume_fraction_filler(self, filler_density_kg_m3: float) -> float | None:
        """Convert reported filler wt% to volume fraction using this grade's
        bulk density and an assumed/known filler density."""
        if self.filler_content_pct is None or self.density_kg_m3 is None:
            return None
        wt_frac = self.filler_content_pct / 100.0
        matrix_density = _pp_matrix_density_kg_m3(self.family)
        # Blend density mixing rule inverted for volume fraction of filler:
        # 1/rho_blend = wf/rho_f + (1-wf)/rho_m  =>  rearranged for vf directly
        # via vf = wf * rho_blend / rho_f (definition of volume fraction).
        return wt_frac * self.density_kg_m3 / filler_density_kg_m3


def _pp_matrix_density_kg_m3(family: str) -> float:
    """Typical unfilled-PP matrix density by family, used only as a fallback
    when a matching unfilled datasheet isn't available."""
    return 905.0 if family == "homopolymer" else 900.0
