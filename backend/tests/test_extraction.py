"""Tests for the extraction agent and the human-review queue.

No ANTHROPIC_API_KEY / ant profile is configured in this dev environment,
so extraction/extractor.py's actual Claude API call is never exercised
live here -- it's tested by monkeypatching the Anthropic client (unit
level) and by monkeypatching extract_grade_from_pdf itself (API level).
The schema and the whole submit -> review -> approve/reject -> promote
pipeline around it are tested for real against an isolated in-memory
SQLite DB, same pattern as test_api.py.
"""
from __future__ import annotations

import io

import anthropic
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.models import Base
from db.repository import seed_correlation_library, seed_grades_from_json
from db.session import get_session
from extraction.extractor import SYSTEM_PROMPT, extract_grade_from_pdf
from extraction.schema import ExtractedGrade, ExtractedProperty

SAMPLE_GRADE = {
    "grade_id": "TEST1",
    "product_name": "SABIC PPcompound TEST1",
    "source_pdf": "TEST1.pdf",
    "family": "homopolymer",
    "filler_type": "glass_fiber_short",
    "filler_content_pct": 20.0,
    "density_kg_m3": 1180.0,
    "mould_shrinkage_pct": 0.7,
    "properties": [
        {"key": "mfr", "cls": "rheological", "value": 10.0, "unit": "dg/min", "condition": {"temp_C": 230, "load_kg": 2.16}, "test_method": "ISO 1133"},
        {"key": "tensile_modulus", "cls": "modulus", "value": 6350.0, "unit": "MPa", "condition": {}, "test_method": "ISO 527/1A"},
    ],
    "extraction_notes": "Family inferred by analogy to sibling grades; not stated explicitly.",
}


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def test_extracted_grade_validates_real_shape():
    grade = ExtractedGrade.model_validate(SAMPLE_GRADE)
    assert grade.grade_id == "TEST1"
    assert len(grade.properties) == 2
    assert grade.properties[0].condition.temp_C == 230


def test_extracted_property_accepts_null_value_for_no_yield():
    prop = ExtractedProperty(key="tensile_stress_yield", cls="strength", value=None, unit="MPa")
    assert prop.value is None


# ---------------------------------------------------------------------------
# extractor.py, with the Anthropic client mocked
# ---------------------------------------------------------------------------


class _FakeParseResponse:
    def __init__(self, parsed_output: ExtractedGrade):
        self.parsed_output = parsed_output


class _FakeMessages:
    def __init__(self, parsed_output: ExtractedGrade):
        self._parsed_output = parsed_output
        self.calls: list[dict] = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeParseResponse(self._parsed_output)


class _FakeAnthropicClient:
    def __init__(self, parsed_output: ExtractedGrade):
        self.messages = _FakeMessages(parsed_output)


def test_extract_grade_from_pdf_calls_claude_opus_5_with_document_and_schema(tmp_path, monkeypatch):
    fake_grade = ExtractedGrade.model_validate(SAMPLE_GRADE)
    fake_client = _FakeAnthropicClient(fake_grade)
    monkeypatch.setattr(anthropic, "Anthropic", lambda: fake_client)

    pdf_path = tmp_path / "TEST1.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake pdf bytes for testing")

    result = extract_grade_from_pdf(pdf_path, source_pdf_filename="TEST1.pdf")

    assert result.grade_id == "TEST1"
    assert len(fake_client.messages.calls) == 1
    call = fake_client.messages.calls[0]
    assert call["model"] == "claude-opus-5"
    assert call["output_format"] is ExtractedGrade
    assert call["system"] == SYSTEM_PROMPT
    assert call["thinking"] == {"type": "adaptive"}
    content = call["messages"][0]["content"]
    assert content[0]["type"] == "document"
    assert content[0]["source"]["media_type"] == "application/pdf"
    assert "\n" not in content[0]["source"]["data"]  # base64 must not contain newlines


def test_extract_grade_from_pdf_overrides_mismatched_source_pdf(tmp_path, monkeypatch):
    # Model returned a different source_pdf than the actual uploaded filename
    # (e.g. it read a filename mentioned inside the PDF body) -- the caller's
    # filename must win, since that's what raw_pdf_files will reference.
    fake_grade = ExtractedGrade.model_validate({**SAMPLE_GRADE, "source_pdf": "wrong-name.pdf"})
    fake_client = _FakeAnthropicClient(fake_grade)
    monkeypatch.setattr(anthropic, "Anthropic", lambda: fake_client)

    pdf_path = tmp_path / "actual-upload.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake pdf bytes")

    result = extract_grade_from_pdf(pdf_path, source_pdf_filename="actual-upload.pdf")
    assert result.source_pdf == "actual-upload.pdf"


# ---------------------------------------------------------------------------
# API: submit -> review -> approve/reject -> promote, extraction call mocked
# ---------------------------------------------------------------------------


@pytest.fixture()
def test_session_factory():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    session = factory()
    seed_grades_from_json(session)
    seed_correlation_library(session)
    session.close()

    return factory


@pytest.fixture()
def client(test_session_factory, tmp_path, monkeypatch):
    import db.repository as repo

    monkeypatch.setattr(repo, "UPLOADED_PDF_DIR", tmp_path / "uploaded_datasheets")

    def override_get_session():
        session = test_session_factory()
        try:
            yield session
        finally:
            session.close()

    from api.main import app

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _upload(client, filename="TEST1.pdf"):
    return client.post(
        "/extractions",
        files={"file": (filename, io.BytesIO(b"%PDF-1.4 fake pdf content"), "application/pdf")},
    )


def test_submit_extraction_success(client, monkeypatch):
    fake_grade = ExtractedGrade.model_validate(SAMPLE_GRADE)
    monkeypatch.setattr("api.main.extract_grade_from_pdf", lambda path, source_pdf_filename=None: fake_grade)

    r = _upload(client)
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "pending_review"
    assert body["extracted_json"]["grade_id"] == "TEST1"
    assert body["extraction_notes"] == SAMPLE_GRADE["extraction_notes"]


def test_submit_extraction_rejects_non_pdf(client):
    r = client.post("/extractions", files={"file": ("notes.txt", io.BytesIO(b"hi"), "text/plain")})
    assert r.status_code == 400


def test_submit_extraction_surfaces_claude_api_error_as_502(client, monkeypatch):
    def boom(path, source_pdf_filename=None):
        raise anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))

    monkeypatch.setattr("api.main.extract_grade_from_pdf", boom)
    r = _upload(client)
    assert r.status_code == 502


def test_submit_extraction_surfaces_missing_credentials_as_502(client, monkeypatch):
    # anthropic.Anthropic() raises a plain TypeError (not anthropic.APIError)
    # when no credential resolves at all -- reproduces the real failure seen
    # with no ANTHROPIC_API_KEY / ant auth profile configured.
    def boom(path, source_pdf_filename=None):
        raise TypeError(
            "Could not resolve authentication method. Expected one of api_key, "
            "auth_token, or credentials to be set."
        )

    monkeypatch.setattr("api.main.extract_grade_from_pdf", boom)
    r = _upload(client)
    assert r.status_code == 502
    assert "resolve authentication" in r.json()["detail"]


def test_list_and_get_extraction(client, monkeypatch):
    fake_grade = ExtractedGrade.model_validate(SAMPLE_GRADE)
    monkeypatch.setattr("api.main.extract_grade_from_pdf", lambda path, source_pdf_filename=None: fake_grade)

    submitted = _upload(client).json()
    r = client.get("/extractions", params={"status": "pending_review"})
    assert r.status_code == 200
    assert any(e["id"] == submitted["id"] for e in r.json())

    r = client.get(f"/extractions/{submitted['id']}")
    assert r.status_code == 200
    assert r.json()["extracted_json"]["grade_id"] == "TEST1"

    assert client.get("/extractions/999999").status_code == 404


def test_patch_extraction_applies_reviewer_correction(client, monkeypatch):
    fake_grade = ExtractedGrade.model_validate(SAMPLE_GRADE)
    monkeypatch.setattr("api.main.extract_grade_from_pdf", lambda path, source_pdf_filename=None: fake_grade)
    submitted = _upload(client).json()

    corrected = dict(submitted["extracted_json"])
    corrected["family"] = "impact_copolymer"

    r = client.patch(f"/extractions/{submitted['id']}", json={"extracted_json": corrected})
    assert r.status_code == 200
    assert r.json()["extracted_json"]["family"] == "impact_copolymer"


def test_patch_extraction_rejects_malformed_correction(client, monkeypatch):
    # approve_pending_extraction dict-indexes extracted_json's required
    # fields with no .get() fallback, so a reviewer correction missing one
    # (e.g. a typo'd/removed key) must be rejected here at PATCH time with a
    # clear 422 -- not accepted and left to blow up as a raw 500 (KeyError)
    # when the reviewer later clicks approve.
    fake_grade = ExtractedGrade.model_validate(SAMPLE_GRADE)
    monkeypatch.setattr("api.main.extract_grade_from_pdf", lambda path, source_pdf_filename=None: fake_grade)
    submitted = _upload(client).json()

    malformed = dict(submitted["extracted_json"])
    del malformed["grade_id"]

    r = client.patch(f"/extractions/{submitted['id']}", json={"extracted_json": malformed})
    assert r.status_code == 422

    # The original, valid data must still be there -- the bad PATCH didn't partially apply.
    assert client.get(f"/extractions/{submitted['id']}").json()["extracted_json"]["grade_id"] == "TEST1"


def test_approve_extraction_promotes_grade_and_is_then_searchable(client, monkeypatch):
    fake_grade = ExtractedGrade.model_validate(SAMPLE_GRADE)
    monkeypatch.setattr("api.main.extract_grade_from_pdf", lambda path, source_pdf_filename=None: fake_grade)
    submitted = _upload(client).json()

    r = client.post(f"/extractions/{submitted['id']}/approve", json={"reviewed_by": "test-reviewer"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "approved"
    assert body["reviewed_by"] == "test-reviewer"
    assert body["promoted_grade_pk"] is not None

    grade_resp = client.get("/grades/TEST1")
    assert grade_resp.status_code == 200
    assert grade_resp.json()["family"] == "homopolymer"

    search_resp = client.post("/search", json={"target_properties": {"mfr": 10, "tensile_modulus": 6350}})
    assert any(m["grade"]["grade_id"] == "TEST1" for m in search_resp.json()["matches"])

    # Already decided -- can't approve/patch/reject again.
    assert client.post(f"/extractions/{submitted['id']}/approve", json={"reviewed_by": "x"}).status_code == 404
    assert client.patch(f"/extractions/{submitted['id']}", json={"extracted_json": submitted["extracted_json"]}).status_code == 404


def test_reject_extraction_does_not_create_grade(client, monkeypatch):
    fake_grade = ExtractedGrade.model_validate(SAMPLE_GRADE)
    monkeypatch.setattr("api.main.extract_grade_from_pdf", lambda path, source_pdf_filename=None: fake_grade)
    submitted = _upload(client).json()

    r = client.post(
        f"/extractions/{submitted['id']}/reject",
        json={"reviewed_by": "test-reviewer", "reviewer_notes": "MFR looks OCR-garbled, resubmit a clearer scan."},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"

    assert client.get("/grades/TEST1").status_code == 404


def test_approve_upserts_existing_grade_on_resubmission(client, monkeypatch):
    fake_grade = ExtractedGrade.model_validate(SAMPLE_GRADE)
    monkeypatch.setattr("api.main.extract_grade_from_pdf", lambda path, source_pdf_filename=None: fake_grade)

    first = _upload(client).json()
    client.post(f"/extractions/{first['id']}/approve", json={"reviewed_by": "reviewer-1"})

    corrected_grade = ExtractedGrade.model_validate({**SAMPLE_GRADE, "density_kg_m3": 1190.0})
    monkeypatch.setattr("api.main.extract_grade_from_pdf", lambda path, source_pdf_filename=None: corrected_grade)
    second = _upload(client, filename="TEST1-corrected.pdf").json()
    client.post(f"/extractions/{second['id']}/approve", json={"reviewed_by": "reviewer-2"})

    grade_resp = client.get("/grades/TEST1")
    assert grade_resp.json()["density_kg_m3"] == 1190.0

    all_grades = client.get("/grades").json()
    assert sum(1 for g in all_grades if g["grade_id"] == "TEST1") == 1
