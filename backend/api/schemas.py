"""Pydantic request/response models for the API layer, plus conversion
functions from the deterministic engine's plain dataclasses (engine/*.py)
into JSON-serializable shapes. Keeping this mapping here (rather than
teaching the engine about pydantic) keeps engine/* framework-agnostic.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from engine.models import Grade
from engine.predictor import BlendResult, PropertyPrediction
from engine.search import GradeMatch, PropertyMatch
from engine.visbreaking import DoeRun, VisbreakingProposal

# ---------------------------------------------------------------------------
# Grades
# ---------------------------------------------------------------------------


class PropertyOut(BaseModel):
    key: str
    cls: str
    value: float
    unit: str
    condition: dict[str, Any]
    test_method: str | None = None


class GradeSummary(BaseModel):
    grade_id: str
    product_name: str
    family: str
    filler_type: str
    filler_content_pct: float | None = None
    density_kg_m3: float | None = None
    mfr: float | None = None
    tensile_modulus: float | None = None


class GradeDetail(GradeSummary):
    source_pdf: str
    mould_shrinkage_pct: float | None = None
    properties: list[PropertyOut] = []


def to_grade_summary(g: Grade) -> GradeSummary:
    mfr = g.get_one("mfr")
    tm = g.get_one("tensile_modulus") or g.get_one("tensile_modulus", temp_C=23)
    return GradeSummary(
        grade_id=g.grade_id,
        product_name=g.product_name,
        family=g.family,
        filler_type=g.filler_type,
        filler_content_pct=g.filler_content_pct,
        density_kg_m3=g.density_kg_m3,
        mfr=mfr.value if mfr else None,
        tensile_modulus=tm.value if tm else None,
    )


def to_grade_detail(g: Grade) -> GradeDetail:
    summary = to_grade_summary(g)
    return GradeDetail(
        **summary.model_dump(),
        source_pdf=g.source_pdf,
        mould_shrinkage_pct=g.mould_shrinkage_pct,
        properties=[
            PropertyOut(key=p.key, cls=p.cls, value=p.value, unit=p.unit, condition=p.condition, test_method=p.test_method)
            for p in g.properties
        ],
    )


# ---------------------------------------------------------------------------
# Step 1: search
# ---------------------------------------------------------------------------


class SearchRequest(BaseModel):
    target_properties: dict[str, float]
    conditions: dict[str, dict[str, Any]] | None = None
    tolerance_fraction: float | None = None


class PropertyMatchOut(BaseModel):
    key: str
    target: float
    actual: float
    relative_error: float
    within_margin: bool


class GradeMatchOut(BaseModel):
    grade: GradeSummary
    source_pdf: str
    matches: list[PropertyMatchOut]
    max_relative_error: float


class SearchResponse(BaseModel):
    matches: list[GradeMatchOut]


def to_property_match_out(m: PropertyMatch) -> PropertyMatchOut:
    return PropertyMatchOut(key=m.key, target=m.target, actual=m.actual, relative_error=m.relative_error, within_margin=m.within_margin)


def to_grade_match_out(gm: GradeMatch) -> GradeMatchOut:
    return GradeMatchOut(
        grade=to_grade_summary(gm.grade),
        source_pdf=gm.source_pdf,
        matches=[to_property_match_out(m) for m in gm.matches],
        max_relative_error=gm.max_relative_error,
    )


# ---------------------------------------------------------------------------
# Step 2: blend
# ---------------------------------------------------------------------------


class BlendRequest(BaseModel):
    target_properties: dict[str, float]
    primary_key: str | None = None


class PropertyPredictionOut(BaseModel):
    key: str
    target: float
    predicted: float
    relative_error: float
    within_margin: bool
    method: str


class BlendResultOut(BaseModel):
    grade_a: GradeSummary
    grade_b: GradeSummary
    phi_a: float
    wt_pct_a: float
    predictions: list[PropertyPredictionOut]
    within_tolerance: bool
    max_relative_error: float


class BlendResponse(BaseModel):
    solution_found: bool
    result: BlendResultOut | None = None
    visbreaking_prompt: str | None = None


def to_property_prediction_out(p: PropertyPrediction) -> PropertyPredictionOut:
    return PropertyPredictionOut(
        key=p.key, target=p.target, predicted=p.predicted, relative_error=p.relative_error, within_margin=p.within_margin, method=p.method
    )


def to_blend_result_out(br: BlendResult) -> BlendResultOut:
    return BlendResultOut(
        grade_a=to_grade_summary(br.grade_a),
        grade_b=to_grade_summary(br.grade_b),
        phi_a=br.phi_a,
        wt_pct_a=br.wt_pct_a,
        predictions=[to_property_prediction_out(p) for p in br.predictions],
        within_tolerance=br.within_tolerance,
        max_relative_error=br.max_relative_error,
    )


# ---------------------------------------------------------------------------
# Step 3: visbreaking
# ---------------------------------------------------------------------------


class VisbreakingRequest(BaseModel):
    target_properties: dict[str, float]
    process: str = "reactive_extrusion"
    temp_C: float | None = None
    residence_time_min: float | None = None
    overshoot_fraction: float = 0.05


class DoeRunOut(BaseModel):
    dose_wt_pct: float
    temp_C: float
    residence_time_min: float
    predicted_mfi: float


class VisbreakingResultOut(BaseModel):
    base_grade: GradeSummary
    target_mfr: float
    final_mfi_design_point: float
    peroxide_dose_wt_pct: float
    process: str
    temp_C: float
    residence_time_min: float
    peroxide_family_key: str
    correlation_source_citation: str | None = None
    doe: list[DoeRunOut]


class VisbreakingResponse(BaseModel):
    solution_found: bool
    result: VisbreakingResultOut | None = None


def to_doe_run_out(r: DoeRun) -> DoeRunOut:
    return DoeRunOut(dose_wt_pct=r.dose_wt_pct, temp_C=r.temp_C, residence_time_min=r.residence_time_min, predicted_mfi=r.predicted_mfi)


def to_visbreaking_result_out(vp: VisbreakingProposal, citation: str | None) -> VisbreakingResultOut:
    return VisbreakingResultOut(
        base_grade=to_grade_summary(vp.base_grade),
        target_mfr=vp.target_mfr,
        final_mfi_design_point=vp.final_mfi_design_point,
        peroxide_dose_wt_pct=vp.peroxide_dose_wt_pct,
        process=vp.process,
        temp_C=vp.temp_C,
        residence_time_min=vp.residence_time_min,
        peroxide_family_key=vp.peroxide_family_key,
        correlation_source_citation=citation,
        doe=[to_doe_run_out(r) for r in vp.doe],
    )


# ---------------------------------------------------------------------------
# Extraction review queue
# ---------------------------------------------------------------------------


class PendingExtractionSummary(BaseModel):
    id: int
    source_pdf_filename: str
    status: str
    submitted_at: str
    reviewed_at: str | None = None
    reviewed_by: str | None = None
    grade_id: str | None = None
    family: str | None = None


class PendingExtractionDetail(PendingExtractionSummary):
    extracted_json: dict[str, Any]
    extraction_notes: str | None = None
    reviewer_notes: str | None = None
    promoted_grade_pk: int | None = None


class UpdateExtractionRequest(BaseModel):
    extracted_json: dict[str, Any]


class ApproveExtractionRequest(BaseModel):
    reviewed_by: str


class RejectExtractionRequest(BaseModel):
    reviewed_by: str
    reviewer_notes: str


def to_pending_extraction_summary(row) -> PendingExtractionSummary:
    extracted = row.extracted_json or {}
    return PendingExtractionSummary(
        id=row.id,
        source_pdf_filename=row.source_pdf_filename,
        status=row.status,
        submitted_at=row.submitted_at.isoformat(),
        reviewed_at=row.reviewed_at.isoformat() if row.reviewed_at else None,
        reviewed_by=row.reviewed_by,
        grade_id=extracted.get("grade_id"),
        family=extracted.get("family"),
    )


def to_pending_extraction_detail(row) -> PendingExtractionDetail:
    return PendingExtractionDetail(
        **to_pending_extraction_summary(row).model_dump(),
        extracted_json=row.extracted_json,
        extraction_notes=row.extraction_notes,
        reviewer_notes=row.reviewer_notes,
        promoted_grade_pk=row.promoted_grade_pk,
    )


# ---------------------------------------------------------------------------
# Correlation research queue (architecture plan §6)
# ---------------------------------------------------------------------------


class ResearchCorrelationRequest(BaseModel):
    family_key: str


class ResearchCorrelationResponse(BaseModel):
    family_key: str
    update_recommended: bool
    search_summary: str
    pending_correlation_id: int | None = None


class PendingCorrelationSummary(BaseModel):
    id: int
    family_key: str
    status: str
    submitted_at: str
    reviewed_at: str | None = None
    reviewed_by: str | None = None
    proposed_name: str | None = None


class PendingCorrelationDetail(PendingCorrelationSummary):
    proposed_json: dict[str, Any]
    search_summary: str
    reviewer_notes: str | None = None
    promoted_correlation_pk: int | None = None


class UpdatePendingCorrelationRequest(BaseModel):
    proposed_json: dict[str, Any]


class ApproveCorrelationRequest(BaseModel):
    reviewed_by: str


class RejectCorrelationRequest(BaseModel):
    reviewed_by: str
    reviewer_notes: str


def to_pending_correlation_summary(row) -> PendingCorrelationSummary:
    return PendingCorrelationSummary(
        id=row.id,
        family_key=row.family_key,
        status=row.status,
        submitted_at=row.submitted_at.isoformat(),
        reviewed_at=row.reviewed_at.isoformat() if row.reviewed_at else None,
        reviewed_by=row.reviewed_by,
        proposed_name=(row.proposed_json or {}).get("name"),
    )


def to_pending_correlation_detail(row) -> PendingCorrelationDetail:
    return PendingCorrelationDetail(
        **to_pending_correlation_summary(row).model_dump(),
        proposed_json=row.proposed_json,
        search_summary=row.search_summary,
        reviewer_notes=row.reviewer_notes,
        promoted_correlation_pk=row.promoted_correlation_pk,
    )
