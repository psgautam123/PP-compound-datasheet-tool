"""SQLAlchemy ORM models for the Postgres schema described in the
architecture plan (`grades` / `properties` / `correlation_library` /
`raw_pdf_files`). These are storage models only -- the deterministic
engine (engine/*.py) never imports this module; db/repository.py is the
sole adapter that converts these rows into engine.models.Grade objects, so
the blend/search/visbreaking math stays fully DB-agnostic and unit
testable without a database.

JSON columns use a Postgres-JSONB variant with a plain-JSON fallback so the
same models work against SQLite in tests/dev without a running Postgres
server (none is available in this environment -- see backend/db/session.py).
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

PortableJSON = JSON().with_variant(JSONB, "postgresql")


class Base(DeclarativeBase):
    pass


class GradeRow(Base):
    __tablename__ = "grades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    grade_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_pdf: Mapped[str] = mapped_column(String(255), nullable=False)
    family: Mapped[str] = mapped_column(String(32), nullable=False)
    filler_type: Mapped[str] = mapped_column(String(32), nullable=False)
    filler_content_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    density_kg_m3: Mapped[float | None] = mapped_column(Float, nullable=True)
    mould_shrinkage_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    properties: Mapped[list["PropertyRow"]] = relationship(
        back_populates="grade", cascade="all, delete-orphan", order_by="PropertyRow.id"
    )
    raw_pdf: Mapped["RawPdfFileRow | None"] = relationship(back_populates="grade", cascade="all, delete-orphan")


class PropertyRow(Base):
    __tablename__ = "properties"
    __table_args__ = (UniqueConstraint("grade_pk", "key", "condition", name="uq_property_grade_key_condition"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    grade_pk: Mapped[int] = mapped_column(ForeignKey("grades.id", ondelete="CASCADE"), index=True, nullable=False)
    key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    property_class: Mapped[str] = mapped_column(String(32), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    condition: Mapped[dict] = mapped_column(PortableJSON, nullable=False, default=dict)
    test_method: Mapped[str | None] = mapped_column(String(64), nullable=True)

    grade: Mapped["GradeRow"] = relationship(back_populates="properties")


class RawPdfFileRow(Base):
    """Reference to the source PDF on disk (see architecture plan §1: blob
    storage or local disk with a DB reference -- local disk for this
    project, since the datasheets already live under "Technical data
    sheets/" in the repo).
    """

    __tablename__ = "raw_pdf_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    grade_pk: Mapped[int] = mapped_column(
        ForeignKey("grades.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)

    grade: Mapped["GradeRow"] = relationship(back_populates="raw_pdf")


class CorrelationLibraryRow(Base):
    """Curated, versioned peroxide-visbreaking correlations (architecture
    plan §6). Seeded from Workflow2.txt's cited references; the
    correlation-research agent proposes new *pending* versions here for
    human approval -- engine.visbreaking never has DB access itself, it
    just accepts coefficient/ea overrides resolved by the repository layer
    from whichever row is currently `is_active`.
    """

    __tablename__ = "correlation_library"
    __table_args__ = (UniqueConstraint("family_key", "version", name="uq_correlation_family_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    family_key: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # "homopolymer" | "impact_pp"
    ln_mfi_coefficient: Mapped[float] = mapped_column(Float, nullable=False)
    ea_kj_mol: Mapped[float] = mapped_column(Float, nullable=False)
    reference_temp_C: Mapped[float] = mapped_column(Float, nullable=False)
    reference_residence_time_min: Mapped[float] = mapped_column(Float, nullable=False)
    source_citation: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approved_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    approved_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("correlation_library.id"), nullable=True
    )


class PendingExtractionRow(Base):
    """Human-review queue for the PDF extraction agent (architecture plan
    §2). A submission here is NOT searchable data -- extraction/extractor.py
    (an offline, one-shot Claude API call) proposes `extracted_json`, a
    reviewer edits it if needed via PATCH, and only `approve` promotes it
    into the live `grades`/`properties`/`raw_pdf_files` tables via
    db/repository.approve_pending_extraction.
    """

    __tablename__ = "pending_extractions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_pdf_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending_review", index=True)
    extracted_json: Mapped[dict] = mapped_column(PortableJSON, nullable=False)
    extraction_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reviewed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    promoted_grade_pk: Mapped[int | None] = mapped_column(ForeignKey("grades.id"), nullable=True)


class PendingCorrelationRow(Base):
    """Human-review queue for the correlation-research agent (architecture
    plan §6). A submission here is NOT used by engine.visbreaking --
    correlation_research/researcher.py (an offline Claude + web-search call,
    run periodically/on-demand, not per-request) proposes `proposed_json`
    plus a `search_summary` a human can sanity-check, and only `approve`
    creates a new version in correlation_library and marks it active via
    db/repository.approve_pending_correlation. Mirrors PendingExtractionRow's
    review-queue pattern for the second bounded LLM touchpoint.
    """

    __tablename__ = "pending_correlations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    family_key: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending_review", index=True)
    proposed_json: Mapped[dict] = mapped_column(PortableJSON, nullable=False)
    search_summary: Mapped[str] = mapped_column(Text, nullable=False)
    reviewer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reviewed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    promoted_correlation_pk: Mapped[int | None] = mapped_column(ForeignKey("correlation_library.id"), nullable=True)
