"""Adapter between the Postgres-backed ORM rows (db/models.py) and the
deterministic engine's plain dataclasses (engine/models.py). This is the
only module that both packages depend on; engine/* stays DB-agnostic and
directly unit-testable (see backend/tests), and db/* stays free of
blend-math concerns.
"""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from engine.models import Grade, PropertyValue

from .models import (
    CorrelationLibraryRow,
    GradeRow,
    PendingCorrelationRow,
    PendingExtractionRow,
    PropertyRow,
    RawPdfFileRow,
)

DEFAULT_DATASHEETS_JSON = Path(__file__).resolve().parent.parent / "data" / "datasheets.json"
DEFAULT_PDF_DIR = Path(__file__).resolve().parent.parent.parent / "Technical data sheets"
UPLOADED_PDF_DIR = Path(__file__).resolve().parent.parent / "data" / "uploaded_datasheets"


# ---------------------------------------------------------------------------
# ORM row -> engine dataclass
# ---------------------------------------------------------------------------


def _to_engine_grade(row: GradeRow) -> Grade:
    return Grade(
        grade_id=row.grade_id,
        product_name=row.product_name,
        source_pdf=row.source_pdf,
        family=row.family,
        filler_type=row.filler_type,
        filler_content_pct=row.filler_content_pct,
        density_kg_m3=row.density_kg_m3,
        mould_shrinkage_pct=row.mould_shrinkage_pct,
        properties=tuple(
            PropertyValue(
                key=p.key,
                cls=p.property_class,
                value=p.value,
                unit=p.unit,
                condition=p.condition or {},
                test_method=p.test_method,
            )
            for p in row.properties
        ),
    )


def get_all_grades(session: Session) -> list[Grade]:
    rows = session.scalars(select(GradeRow).options(selectinload(GradeRow.properties))).all()
    return [_to_engine_grade(r) for r in rows]


def get_grade(session: Session, grade_id: str) -> Grade | None:
    row = session.scalar(
        select(GradeRow).options(selectinload(GradeRow.properties)).where(GradeRow.grade_id == grade_id)
    )
    return _to_engine_grade(row) if row else None


def get_source_pdf_path(session: Session, grade_id: str) -> Path | None:
    row = session.scalar(
        select(RawPdfFileRow).join(GradeRow).where(GradeRow.grade_id == grade_id)
    )
    if row is None:
        return None
    # Seeded sample grades live under DEFAULT_PDF_DIR; grades promoted from
    # the extraction review queue live under UPLOADED_PDF_DIR -- check both
    # rather than encoding which source a grade came from in the schema.
    for base in (DEFAULT_PDF_DIR, UPLOADED_PDF_DIR):
        candidate = base / row.storage_path
        if candidate.exists():
            return candidate
    return DEFAULT_PDF_DIR / row.storage_path


# ---------------------------------------------------------------------------
# Correlation library lookup
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CorrelationParams:
    ln_mfi_coefficient: float
    ea_kj_mol: float
    reference_temp_C: float
    reference_residence_time_min: float
    source_citation: str
    version: int


def get_active_correlation(session: Session, family_key: str) -> CorrelationParams | None:
    row = session.scalar(
        select(CorrelationLibraryRow).where(
            CorrelationLibraryRow.family_key == family_key, CorrelationLibraryRow.is_active.is_(True)
        )
    )
    if row is None:
        return None
    return CorrelationParams(
        ln_mfi_coefficient=row.ln_mfi_coefficient,
        ea_kj_mol=row.ea_kj_mol,
        reference_temp_C=row.reference_temp_C,
        reference_residence_time_min=row.reference_residence_time_min,
        source_citation=row.source_citation,
        version=row.version,
    )


# ---------------------------------------------------------------------------
# Seeding (stands in for the human-reviewed extraction pipeline landing
# approved records in the DB -- see architecture plan §2 and §6)
# ---------------------------------------------------------------------------


def seed_grades_from_json(session: Session, path: Path = DEFAULT_DATASHEETS_JSON, pdf_dir: Path = DEFAULT_PDF_DIR) -> int:
    """Insert grades/properties/raw_pdf_files from the extracted JSON.
    Idempotent: grades already present (by grade_id) are left untouched.
    Returns the number of newly inserted grades.
    """
    existing_ids = set(session.scalars(select(GradeRow.grade_id)).all())
    entries = json.loads(path.read_text(encoding="utf-8"))

    inserted = 0
    for entry in entries:
        if entry["grade_id"] in existing_ids:
            continue

        grade_row = GradeRow(
            grade_id=entry["grade_id"],
            product_name=entry["product_name"],
            source_pdf=entry["source_pdf"],
            family=entry["family"],
            filler_type=entry["filler_type"],
            filler_content_pct=entry.get("filler_content_pct"),
            density_kg_m3=entry.get("density_kg_m3"),
            mould_shrinkage_pct=entry.get("mould_shrinkage_pct"),
        )
        for p in entry["properties"]:
            if p["value"] is None:
                continue  # "No Yield"/"No Break"/unreported rows -- see data_loader.py
            grade_row.properties.append(
                PropertyRow(
                    key=p["key"],
                    property_class=p["class"],
                    value=p["value"],
                    unit=p["unit"],
                    condition=p.get("condition") or {},
                    test_method=p.get("test_method"),
                )
            )

        source_pdf_path = pdf_dir / entry["source_pdf"]
        if source_pdf_path.exists():
            grade_row.raw_pdf = RawPdfFileRow(filename=entry["source_pdf"], storage_path=entry["source_pdf"])

        session.add(grade_row)
        inserted += 1

    session.commit()
    return inserted


# Seeded from Workflow2.txt §27-34's cited references. Peer-reviewed
# journal articles per the sourcing hierarchy; the ExxonMobil/LyondellBasell
# bulletins are Tier-5 company disclosures included only as corroborating
# industrial context, not as the primary basis for the numeric coefficients.
_DEFAULT_CORRELATION_CITATION = (
    "Tzoganakis, C. Polym. Eng. Sci. 28(24), 1706-1714 (1988); "
    "Rocha, M.C.G. et al. Polym. Degrad. Stab. 47, 113-118 (1995); "
    "Azizi, H. et al. Polym. Degrad. Stab. 83, 395-401 (2004); "
    "Iedema, P.D. et al. Chem. Eng. Sci. 56, 3659-3671 (2001); "
    "Berzin, F. et al. Polymers 14, 484 (2022); "
    "Stanic, V. et al. Polymers 14, 2728 (2022); "
    "corroborated by ExxonMobil and LyondellBasell technical bulletins on "
    "Controlled Rheology PP (CR-PP) and peroxide masterbatches."
)


def seed_correlation_library(session: Session) -> int:
    """Insert the two built-in peroxide-visbreaking correlations as
    version-1, active entries, if not already present. Returns the number
    inserted.
    """
    existing = set(session.scalars(select(CorrelationLibraryRow.family_key)))
    to_seed = [
        ("homopolymer", "Homopolymer PP DCP visbreaking (base)", 9.5),
        ("impact_pp", "Impact PP (heterophasic) DCP visbreaking (base)", 7.0),
    ]
    inserted = 0
    for family_key, name, coeff in to_seed:
        if family_key in existing:
            continue
        session.add(
            CorrelationLibraryRow(
                name=name,
                family_key=family_key,
                ln_mfi_coefficient=coeff,
                ea_kj_mol=117.5,
                reference_temp_C=220.0,
                reference_residence_time_min=2.0,
                source_citation=_DEFAULT_CORRELATION_CITATION,
                version=1,
                is_active=True,
                approved_by="workflow_seed",
                approved_at=dt.datetime.now(dt.timezone.utc),
            )
        )
        inserted += 1
    session.commit()
    return inserted


# ---------------------------------------------------------------------------
# Pending extractions (human-review queue -- architecture plan §2)
# ---------------------------------------------------------------------------


def create_pending_extraction(
    session: Session, source_pdf_filename: str, storage_path: str, extracted_json: dict, extraction_notes: str | None
) -> PendingExtractionRow:
    row = PendingExtractionRow(
        source_pdf_filename=source_pdf_filename,
        storage_path=storage_path,
        status="pending_review",
        extracted_json=extracted_json,
        extraction_notes=extraction_notes,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def list_pending_extractions(session: Session, status: str | None = None) -> list[PendingExtractionRow]:
    stmt = select(PendingExtractionRow).order_by(PendingExtractionRow.submitted_at.desc())
    if status:
        stmt = stmt.where(PendingExtractionRow.status == status)
    return list(session.scalars(stmt).all())


def get_pending_extraction(session: Session, extraction_id: int) -> PendingExtractionRow | None:
    return session.get(PendingExtractionRow, extraction_id)


def update_pending_extraction(
    session: Session, extraction_id: int, extracted_json: dict
) -> PendingExtractionRow | None:
    """Reviewer correction of the extracted fields before approval. Only
    valid while still pending_review -- once approved/rejected, the record
    is a decided outcome, not a draft.
    """
    row = session.get(PendingExtractionRow, extraction_id)
    if row is None or row.status != "pending_review":
        return None
    row.extracted_json = extracted_json
    session.commit()
    session.refresh(row)
    return row


def approve_pending_extraction(
    session: Session, extraction_id: int, reviewed_by: str
) -> PendingExtractionRow | None:
    """Promote a reviewed extraction into the live grades/properties tables
    and mark it approved. Upserts by grade_id: if the grade already exists
    (a correction/resubmission), its properties are replaced wholesale
    rather than duplicated.
    """
    row = session.get(PendingExtractionRow, extraction_id)
    if row is None or row.status != "pending_review":
        return None

    entry = row.extracted_json
    existing = session.scalar(
        select(GradeRow).options(selectinload(GradeRow.properties)).where(GradeRow.grade_id == entry["grade_id"])
    )
    grade_row = existing or GradeRow(grade_id=entry["grade_id"])
    grade_row.product_name = entry["product_name"]
    grade_row.source_pdf = entry["source_pdf"]
    grade_row.family = entry["family"]
    grade_row.filler_type = entry["filler_type"]
    grade_row.filler_content_pct = entry.get("filler_content_pct")
    grade_row.density_kg_m3 = entry.get("density_kg_m3")
    grade_row.mould_shrinkage_pct = entry.get("mould_shrinkage_pct")

    if existing is not None:
        # Delete-then-flush before inserting the replacements: assigning a
        # new list straight to grade_row.properties relies on the ORM
        # ordering deletes of the old rows before inserts of the new ones,
        # which it does not guarantee when a new row's (grade_pk, key,
        # condition) matches a row still pending deletion -- exactly the
        # common case here (an unchanged property on a corrected resubmit).
        for old_prop in list(grade_row.properties):
            session.delete(old_prop)
        session.flush()

    grade_row.properties = [
        PropertyRow(
            key=p["key"],
            property_class=p["cls"],
            value=p["value"],
            unit=p["unit"],
            condition={k: v for k, v in (p.get("condition") or {}).items() if v is not None},
            test_method=p.get("test_method"),
        )
        for p in entry["properties"]
        if p["value"] is not None
    ]
    if grade_row.raw_pdf is None:
        grade_row.raw_pdf = RawPdfFileRow(filename=row.source_pdf_filename, storage_path=row.storage_path)
    else:
        grade_row.raw_pdf.filename = row.source_pdf_filename
        grade_row.raw_pdf.storage_path = row.storage_path

    if existing is None:
        session.add(grade_row)
    session.flush()

    row.status = "approved"
    row.reviewed_by = reviewed_by
    row.reviewed_at = dt.datetime.now(dt.timezone.utc)
    row.promoted_grade_pk = grade_row.id
    session.commit()
    session.refresh(row)
    return row


def reject_pending_extraction(
    session: Session, extraction_id: int, reviewed_by: str, reviewer_notes: str
) -> PendingExtractionRow | None:
    row = session.get(PendingExtractionRow, extraction_id)
    if row is None or row.status != "pending_review":
        return None
    row.status = "rejected"
    row.reviewed_by = reviewed_by
    row.reviewer_notes = reviewer_notes
    row.reviewed_at = dt.datetime.now(dt.timezone.utc)
    session.commit()
    session.refresh(row)
    return row


# ---------------------------------------------------------------------------
# Pending correlations (human-review queue -- architecture plan §6)
# ---------------------------------------------------------------------------


def create_pending_correlation(
    session: Session, family_key: str, proposed_json: dict, search_summary: str
) -> PendingCorrelationRow:
    row = PendingCorrelationRow(
        family_key=family_key,
        status="pending_review",
        proposed_json=proposed_json,
        search_summary=search_summary,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def list_pending_correlations(session: Session, status: str | None = None) -> list[PendingCorrelationRow]:
    stmt = select(PendingCorrelationRow).order_by(PendingCorrelationRow.submitted_at.desc())
    if status:
        stmt = stmt.where(PendingCorrelationRow.status == status)
    return list(session.scalars(stmt).all())


def get_pending_correlation(session: Session, pending_id: int) -> PendingCorrelationRow | None:
    return session.get(PendingCorrelationRow, pending_id)


def update_pending_correlation(
    session: Session, pending_id: int, proposed_json: dict
) -> PendingCorrelationRow | None:
    """Reviewer correction of the proposed coefficients/citation before
    approval. Only valid while still pending_review.
    """
    row = session.get(PendingCorrelationRow, pending_id)
    if row is None or row.status != "pending_review":
        return None
    row.proposed_json = proposed_json
    session.commit()
    session.refresh(row)
    return row


def approve_pending_correlation(
    session: Session, pending_id: int, reviewed_by: str
) -> PendingCorrelationRow | None:
    """Promote a reviewed correlation proposal into correlation_library as a
    new version, active for its family_key. The previously active row (if
    any) for that family is deactivated and linked via superseded_by_id --
    old versions are kept, never deleted, so engine.visbreaking results are
    always reproducible against the version that was active at the time.
    """
    row = session.get(PendingCorrelationRow, pending_id)
    if row is None or row.status != "pending_review":
        return None

    proposal = row.proposed_json
    current_active = session.scalar(
        select(CorrelationLibraryRow).where(
            CorrelationLibraryRow.family_key == row.family_key, CorrelationLibraryRow.is_active.is_(True)
        )
    )
    latest_version = session.scalar(
        select(func.max(CorrelationLibraryRow.version)).where(CorrelationLibraryRow.family_key == row.family_key)
    )
    next_version = (latest_version or 0) + 1

    new_row = CorrelationLibraryRow(
        name=proposal["name"],
        family_key=row.family_key,
        ln_mfi_coefficient=proposal["ln_mfi_coefficient"],
        ea_kj_mol=proposal["ea_kj_mol"],
        reference_temp_C=proposal["reference_temp_C"],
        reference_residence_time_min=proposal["reference_residence_time_min"],
        source_citation=proposal["source_citation"],
        version=next_version,
        is_active=True,
        approved_by=reviewed_by,
        approved_at=dt.datetime.now(dt.timezone.utc),
    )
    session.add(new_row)
    session.flush()

    if current_active is not None:
        current_active.is_active = False
        current_active.superseded_by_id = new_row.id

    row.status = "approved"
    row.reviewed_by = reviewed_by
    row.reviewed_at = dt.datetime.now(dt.timezone.utc)
    row.promoted_correlation_pk = new_row.id
    session.commit()
    session.refresh(row)
    return row


def reject_pending_correlation(
    session: Session, pending_id: int, reviewed_by: str, reviewer_notes: str
) -> PendingCorrelationRow | None:
    row = session.get(PendingCorrelationRow, pending_id)
    if row is None or row.status != "pending_review":
        return None
    row.status = "rejected"
    row.reviewed_by = reviewed_by
    row.reviewer_notes = reviewer_notes
    row.reviewed_at = dt.datetime.now(dt.timezone.utc)
    session.commit()
    session.refresh(row)
    return row
