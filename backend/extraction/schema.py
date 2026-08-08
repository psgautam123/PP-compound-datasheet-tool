"""Structured-output schema for the PDF extraction agent. Mirrors the shape
of backend/data/datasheets.json (same fields db/repository.seed_grades_from_json
expects) plus an `extraction_notes` field so the model can flag anything it
was unsure about -- surfaced to the human reviewer rather than silently
guessed. See architecture plan §2: extracted records land in a pending
review queue and a human confirms/corrects before the grade is searchable.

Property `key` is intentionally a free string, not a fixed enum: the 18
sample datasheets alone produced several keys beyond the original canonical
list (flexural_strength, vicat_softening_temp_a/b, tensile_strain_yield --
see backend/data/extraction_notes.md), because real datasheets don't share
one fixed property set. A hard enum would force misclassification whenever
a grade reports something new. Consistency of naming across submissions is
exactly the kind of thing a human reviewer should be checking.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ExtractedPropertyCondition(BaseModel):
    """Free-form condition qualifiers (temperature, load, test thickness,
    etc.) -- kept as a flat string->string map since conditions vary too
    much across datasheets for a fixed schema (see PropertyValue.condition
    in engine/models.py, which this mirrors)."""

    temp_C: float | None = None
    load_kg: float | None = None
    load_MPa: float | None = None
    load_N: float | None = None
    range_C: str | None = None
    rating: str | None = None
    note: str | None = None


class ExtractedProperty(BaseModel):
    key: str = Field(description="Canonical snake_case property key, e.g. 'mfr', 'tensile_modulus', 'izod_notched'.")
    cls: str = Field(
        description="Property class: rheological, modulus, strength, strain, impact_notched, impact_unnotched, thermal, or flammability."
    )
    value: float | None = Field(
        description="Numeric value, or null if the datasheet reports a non-numeric result like 'No Yield' or 'No Break'."
    )
    unit: str
    condition: ExtractedPropertyCondition = Field(default_factory=ExtractedPropertyCondition)
    test_method: str | None = None


class ExtractedGrade(BaseModel):
    grade_id: str = Field(description="Short unique identifier derived from the product name, e.g. 'H1015'.")
    product_name: str = Field(description="Full product name as stated on the datasheet.")
    source_pdf: str = Field(description="Original PDF filename.")
    family: str = Field(description="One of: homopolymer, copolymer, impact_copolymer.")
    filler_type: str = Field(description="One of: none, glass_fiber_short, glass_fiber_long, talc.")
    filler_content_pct: float | None = None
    density_kg_m3: float | None = None
    mould_shrinkage_pct: float | None = None
    properties: list[ExtractedProperty] = Field(default_factory=list)
    extraction_notes: str | None = Field(
        default=None,
        description=(
            "Anything a human reviewer should double-check: ambiguous family/filler classification, "
            "garbled or low-confidence OCR values, non-standard property labels, or properties this "
            "schema doesn't have a clean key for."
        ),
    )
