"""FastAPI layer wiring the deterministic engine (engine/*.py) to the
Postgres-backed grade data (db/*.py). Mirrors Workflow2.txt's three-step
flow as three endpoints -- /search (Step 1), /blend (Step 2), /visbreaking
(Step 3) -- rather than one combined endpoint, since Step 3 requires an
explicit user "yes" after Step 2 fails (Workflow2.txt §21) and the
frontend needs to render that prompt in between.

Run locally: .venv/Scripts/uvicorn api.main:app --reload --app-dir backend
"""
from __future__ import annotations

import uuid
from pathlib import Path

import anthropic
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from db.repository import (
    UPLOADED_PDF_DIR,
    approve_pending_correlation,
    approve_pending_extraction,
    create_pending_correlation,
    create_pending_extraction,
    get_active_correlation,
    get_all_grades,
    get_grade,
    get_pending_correlation,
    get_pending_extraction,
    get_source_pdf_path,
    list_pending_correlations,
    list_pending_extractions,
    reject_pending_correlation,
    reject_pending_extraction,
    update_pending_correlation,
    update_pending_extraction,
)
from db.session import get_session
from engine.predictor import predict_blend
from engine.search import search_grades
from engine.visbreaking import (
    DEFAULT_EA_KJ_MOL,
    FAMILY_TO_PEROXIDE_KEY,
    NO_SOLUTION_PROMPT,
    propose_visbreaking,
    screen_visbreaking_base_grades,
)
from correlation_research.researcher import research_correlation_update
from correlation_research.schema import CorrelationProposal
from extraction.extractor import extract_grade_from_pdf
from extraction.schema import ExtractedGrade

from .schemas import (
    ApproveCorrelationRequest,
    ApproveExtractionRequest,
    BlendRequest,
    BlendResponse,
    GradeDetail,
    GradeSummary,
    PendingCorrelationDetail,
    PendingCorrelationSummary,
    PendingExtractionDetail,
    PendingExtractionSummary,
    RejectCorrelationRequest,
    RejectExtractionRequest,
    ResearchCorrelationRequest,
    ResearchCorrelationResponse,
    SearchRequest,
    SearchResponse,
    UpdateExtractionRequest,
    UpdatePendingCorrelationRequest,
    VisbreakingRequest,
    VisbreakingResponse,
    to_blend_result_out,
    to_grade_detail,
    to_grade_match_out,
    to_grade_summary,
    to_pending_correlation_detail,
    to_pending_correlation_summary,
    to_pending_extraction_detail,
    to_pending_extraction_summary,
    to_visbreaking_result_out,
)

app = FastAPI(title="PP Compound Search & Blend Tool", version="0.1.0")

# Dev-only permissive CORS; restrict to the actual frontend origin before
# any production deployment.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/grades", response_model=list[GradeSummary])
def list_grades(session: Session = Depends(get_session)) -> list[GradeSummary]:
    return [to_grade_summary(g) for g in get_all_grades(session)]


@app.get("/grades/{grade_id}", response_model=GradeDetail)
def get_grade_detail(grade_id: str, session: Session = Depends(get_session)) -> GradeDetail:
    grade = get_grade(session, grade_id)
    if grade is None:
        raise HTTPException(404, f"grade '{grade_id}' not found")
    return to_grade_detail(grade)


@app.get("/grades/{grade_id}/datasheet")
def get_grade_datasheet(grade_id: str, session: Session = Depends(get_session)) -> FileResponse:
    path = get_source_pdf_path(session, grade_id)
    if path is None or not Path(path).exists():
        raise HTTPException(404, f"source datasheet for grade '{grade_id}' not found")
    return FileResponse(path, media_type="application/pdf", filename=Path(path).name)


@app.post("/search", response_model=SearchResponse)
def search(req: SearchRequest, session: Session = Depends(get_session)) -> SearchResponse:
    grades = get_all_grades(session)
    kwargs = {}
    if req.tolerance_fraction is not None:
        kwargs["tolerance_fraction"] = req.tolerance_fraction
    matches = search_grades(req.target_properties, grades, conditions=req.conditions, **kwargs)
    return SearchResponse(matches=[to_grade_match_out(m) for m in matches])


@app.post("/blend", response_model=BlendResponse)
def blend(req: BlendRequest, session: Session = Depends(get_session)) -> BlendResponse:
    grades = get_all_grades(session)
    try:
        result = predict_blend(req.target_properties, grades, primary_key=req.primary_key)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    if result is None:
        return BlendResponse(solution_found=False, result=None, visbreaking_prompt=NO_SOLUTION_PROMPT)
    return BlendResponse(solution_found=True, result=to_blend_result_out(result))


@app.post("/visbreaking", response_model=VisbreakingResponse)
def visbreaking(req: VisbreakingRequest, session: Session = Depends(get_session)) -> VisbreakingResponse:
    grades = get_all_grades(session)
    try:
        candidates = screen_visbreaking_base_grades(req.target_properties, grades)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    if not candidates:
        return VisbreakingResponse(solution_found=False, result=None)

    peroxide_key = FAMILY_TO_PEROXIDE_KEY.get(candidates[0].family)
    correlation = get_active_correlation(session, peroxide_key) if peroxide_key else None

    try:
        result = propose_visbreaking(
            req.target_properties,
            grades,
            process=req.process,
            temp_C=req.temp_C,
            residence_time_min=req.residence_time_min,
            overshoot_fraction=req.overshoot_fraction,
            ea_kj_mol=correlation.ea_kj_mol if correlation else DEFAULT_EA_KJ_MOL,
            coefficient=correlation.ln_mfi_coefficient if correlation else None,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    if result is None:
        return VisbreakingResponse(solution_found=False, result=None)

    citation = correlation.source_citation if correlation else None
    return VisbreakingResponse(solution_found=True, result=to_visbreaking_result_out(result, citation))


# ---------------------------------------------------------------------------
# Extraction review queue (architecture plan §2)
#
# POST /extractions runs the offline PDF-extraction agent once per upload
# and lands the result in pending_review -- it never touches the live
# grades/properties tables directly. Only POST /extractions/{id}/approve
# does that, after a human has seen (and optionally corrected via PATCH)
# the extracted data.
# ---------------------------------------------------------------------------


@app.post("/extractions", response_model=PendingExtractionDetail, status_code=201)
def submit_extraction(session: Session = Depends(get_session), file: UploadFile = File(...)) -> PendingExtractionDetail:
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "only PDF files are accepted")

    UPLOADED_PDF_DIR.mkdir(parents=True, exist_ok=True)
    original_name = Path(file.filename).name  # strip any client-supplied path components
    storage_name = f"{uuid.uuid4().hex[:8]}_{original_name}"
    storage_path = UPLOADED_PDF_DIR / storage_name
    storage_path.write_bytes(file.file.read())

    try:
        extracted = extract_grade_from_pdf(storage_path, source_pdf_filename=original_name)
    except (anthropic.APIError, TypeError) as exc:
        # anthropic.APIError covers auth/connection/rate-limit/server errors
        # from the Claude API once a request is actually sent; the SDK raises
        # a plain TypeError instead, before any request goes out, when no
        # credential resolves at all (no ANTHROPIC_API_KEY/ANTHROPIC_AUTH_TOKEN
        # and no `ant auth login` profile) -- catch both so a missing/invalid
        # credential surfaces as a clean 502, not a raw 500 traceback. The
        # uploaded PDF stays on disk but no pending_extractions row is
        # created, so the caller can retry without a duplicate submission.
        raise HTTPException(502, f"extraction agent failed: {exc}") from exc

    row = create_pending_extraction(
        session,
        source_pdf_filename=original_name,
        storage_path=storage_name,
        extracted_json=extracted.model_dump(mode="json"),
        extraction_notes=extracted.extraction_notes,
    )
    return to_pending_extraction_detail(row)


@app.get("/extractions", response_model=list[PendingExtractionSummary])
def list_extractions(status: str | None = None, session: Session = Depends(get_session)) -> list[PendingExtractionSummary]:
    return [to_pending_extraction_summary(r) for r in list_pending_extractions(session, status=status)]


@app.get("/extractions/{extraction_id}", response_model=PendingExtractionDetail)
def get_extraction(extraction_id: int, session: Session = Depends(get_session)) -> PendingExtractionDetail:
    row = get_pending_extraction(session, extraction_id)
    if row is None:
        raise HTTPException(404, f"extraction {extraction_id} not found")
    return to_pending_extraction_detail(row)


@app.patch("/extractions/{extraction_id}", response_model=PendingExtractionDetail)
def patch_extraction(
    extraction_id: int, req: UpdateExtractionRequest, session: Session = Depends(get_session)
) -> PendingExtractionDetail:
    # Validate the reviewer's correction against the same schema the
    # extraction agent's output is validated against -- approve_pending_extraction
    # trusts extracted_json's shape (dict indexing, no .get() fallbacks for
    # required fields), so an under-specified correction saved here would
    # otherwise surface as an unhandled 500 (KeyError) at approval time
    # instead of a clear error at the point the reviewer made the mistake.
    try:
        validated = ExtractedGrade.model_validate(req.extracted_json)
    except ValidationError as exc:
        raise HTTPException(422, f"corrected data doesn't match the expected shape: {exc}") from exc

    row = update_pending_extraction(session, extraction_id, validated.model_dump(mode="json"))
    if row is None:
        raise HTTPException(404, f"extraction {extraction_id} not found or not pending review")
    return to_pending_extraction_detail(row)


@app.post("/extractions/{extraction_id}/approve", response_model=PendingExtractionDetail)
def approve_extraction(
    extraction_id: int, req: ApproveExtractionRequest, session: Session = Depends(get_session)
) -> PendingExtractionDetail:
    row = approve_pending_extraction(session, extraction_id, reviewed_by=req.reviewed_by)
    if row is None:
        raise HTTPException(404, f"extraction {extraction_id} not found or not pending review")
    return to_pending_extraction_detail(row)


@app.post("/extractions/{extraction_id}/reject", response_model=PendingExtractionDetail)
def reject_extraction(
    extraction_id: int, req: RejectExtractionRequest, session: Session = Depends(get_session)
) -> PendingExtractionDetail:
    row = reject_pending_extraction(session, extraction_id, reviewed_by=req.reviewed_by, reviewer_notes=req.reviewer_notes)
    if row is None:
        raise HTTPException(404, f"extraction {extraction_id} not found or not pending review")
    return to_pending_extraction_detail(row)


# ---------------------------------------------------------------------------
# Correlation research queue (architecture plan §6)
#
# POST /correlations/research runs the offline correlation-research agent
# (Claude + web_search) once per call for a given PP family and, only when
# it recommends an update, lands the proposal in pending_review -- it never
# touches the live correlation_library directly. Only
# POST /correlations/{id}/approve does that, after a human has seen (and
# optionally corrected via PATCH) the proposed coefficients and citation.
# ---------------------------------------------------------------------------


@app.post("/correlations/research", response_model=ResearchCorrelationResponse)
def research_correlation(req: ResearchCorrelationRequest, session: Session = Depends(get_session)) -> ResearchCorrelationResponse:
    active = get_active_correlation(session, req.family_key)
    try:
        result = research_correlation_update(
            req.family_key,
            current_version=active.version if active else None,
            current_ln_mfi_coefficient=active.ln_mfi_coefficient if active else None,
            current_ea_kj_mol=active.ea_kj_mol if active else None,
            current_reference_temp_C=active.reference_temp_C if active else None,
            current_reference_residence_time_min=active.reference_residence_time_min if active else None,
            current_source_citation=active.source_citation if active else None,
        )
    except (anthropic.APIError, TypeError) as exc:
        # See submit_extraction's except clause -- the SDK raises a plain
        # TypeError, not anthropic.APIError, when no credential resolves at
        # all (missing ANTHROPIC_API_KEY/ANTHROPIC_AUTH_TOKEN and no
        # `ant auth login` profile).
        raise HTTPException(502, f"correlation research agent failed: {exc}") from exc

    pending_id = None
    if result.update_recommended and result.proposal is not None:
        row = create_pending_correlation(
            session,
            family_key=req.family_key,
            proposed_json=result.proposal.model_dump(mode="json"),
            search_summary=result.search_summary,
        )
        pending_id = row.id

    return ResearchCorrelationResponse(
        family_key=req.family_key,
        update_recommended=result.update_recommended,
        search_summary=result.search_summary,
        pending_correlation_id=pending_id,
    )


@app.get("/correlations", response_model=list[PendingCorrelationSummary])
def list_correlations(status: str | None = None, session: Session = Depends(get_session)) -> list[PendingCorrelationSummary]:
    return [to_pending_correlation_summary(r) for r in list_pending_correlations(session, status=status)]


@app.get("/correlations/{pending_id}", response_model=PendingCorrelationDetail)
def get_correlation(pending_id: int, session: Session = Depends(get_session)) -> PendingCorrelationDetail:
    row = get_pending_correlation(session, pending_id)
    if row is None:
        raise HTTPException(404, f"pending correlation {pending_id} not found")
    return to_pending_correlation_detail(row)


@app.patch("/correlations/{pending_id}", response_model=PendingCorrelationDetail)
def patch_correlation(
    pending_id: int, req: UpdatePendingCorrelationRequest, session: Session = Depends(get_session)
) -> PendingCorrelationDetail:
    # See patch_extraction's comment -- approve_pending_correlation trusts
    # proposed_json's shape by dict-indexing it, so validate here rather
    # than let a bad correction surface as a KeyError at approval time.
    try:
        validated = CorrelationProposal.model_validate(req.proposed_json)
    except ValidationError as exc:
        raise HTTPException(422, f"corrected data doesn't match the expected shape: {exc}") from exc

    row = update_pending_correlation(session, pending_id, validated.model_dump(mode="json"))
    if row is None:
        raise HTTPException(404, f"pending correlation {pending_id} not found or not pending review")
    return to_pending_correlation_detail(row)


@app.post("/correlations/{pending_id}/approve", response_model=PendingCorrelationDetail)
def approve_correlation(
    pending_id: int, req: ApproveCorrelationRequest, session: Session = Depends(get_session)
) -> PendingCorrelationDetail:
    row = approve_pending_correlation(session, pending_id, reviewed_by=req.reviewed_by)
    if row is None:
        raise HTTPException(404, f"pending correlation {pending_id} not found or not pending review")
    return to_pending_correlation_detail(row)


@app.post("/correlations/{pending_id}/reject", response_model=PendingCorrelationDetail)
def reject_correlation(
    pending_id: int, req: RejectCorrelationRequest, session: Session = Depends(get_session)
) -> PendingCorrelationDetail:
    row = reject_pending_correlation(session, pending_id, reviewed_by=req.reviewed_by, reviewer_notes=req.reviewer_notes)
    if row is None:
        raise HTTPException(404, f"pending correlation {pending_id} not found or not pending review")
    return to_pending_correlation_detail(row)
