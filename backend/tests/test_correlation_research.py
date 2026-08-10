"""Tests for the correlation-research agent and its human-review queue
(architecture plan §6, the second bounded LLM touchpoint).

No ANTHROPIC_API_KEY / ant profile is configured in this dev environment,
so correlation_research/researcher.py's actual Claude calls (web_search
research pass + structuring pass) are never exercised live here -- it's
tested by monkeypatching the Anthropic client (unit level) and by
monkeypatching research_correlation_update itself (API level). The whole
research -> review -> approve/reject -> promote pipeline is tested for real
against an isolated in-memory SQLite DB, same pattern as test_extraction.py.
"""
from __future__ import annotations

import anthropic
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from correlation_research.researcher import (
    RESEARCH_SYSTEM_PROMPT,
    STRUCTURE_SYSTEM_PROMPT,
    research_correlation_update,
)
from correlation_research.schema import CorrelationProposal, CorrelationResearchResult
from db.models import Base
from db.session import get_session

SAMPLE_PROPOSAL = {
    "family_key": "homopolymer",
    "name": "Homopolymer PP DCP visbreaking (2026 update)",
    "ln_mfi_coefficient": 9.8,
    "ea_kj_mol": 120.0,
    "reference_temp_C": 220.0,
    "reference_residence_time_min": 2.0,
    "source_citation": "Doe, J. et al. Polym. Eng. Sci. 66(3), 500-510 (2026).",
    "rationale": "Wider validated MFR range (0.3-60 dg/min) than the seeded Tzoganakis (1988) coefficient.",
}

SAMPLE_RESULT_UPDATE = {
    "family_key": "homopolymer",
    "update_recommended": True,
    "proposal": SAMPLE_PROPOSAL,
    "search_summary": "Found Doe et al. (2026) reporting a wider-range DCP coefficient for homopolymer PP.",
}

SAMPLE_RESULT_NO_UPDATE = {
    "family_key": "impact_pp",
    "update_recommended": False,
    "proposal": None,
    "search_summary": "No newer or better-validated peer-reviewed correlation found for impact PP.",
}


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def test_correlation_research_result_validates_update_shape():
    result = CorrelationResearchResult.model_validate(SAMPLE_RESULT_UPDATE)
    assert result.update_recommended is True
    assert result.proposal.family_key == "homopolymer"


def test_correlation_research_result_validates_no_update_shape():
    result = CorrelationResearchResult.model_validate(SAMPLE_RESULT_NO_UPDATE)
    assert result.update_recommended is False
    assert result.proposal is None


# ---------------------------------------------------------------------------
# researcher.py, with the Anthropic client mocked
# ---------------------------------------------------------------------------


class _FakeParseResponse:
    def __init__(self, parsed_output):
        self.parsed_output = parsed_output


class _FakeTextBlock:
    def __init__(self, text: str):
        self.type = "text"
        self.text = text


class _FakeStream:
    def __init__(self, text: str):
        self._text = text

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def get_final_message(self):
        class _Resp:
            pass

        resp = _Resp()
        resp.content = [_FakeTextBlock(self._text)]
        return resp


class _FakeMessages:
    def __init__(self, research_text: str, parsed_output: CorrelationResearchResult):
        self._research_text = research_text
        self._parsed_output = parsed_output
        self.stream_calls: list[dict] = []
        self.parse_calls: list[dict] = []

    def stream(self, **kwargs):
        self.stream_calls.append(kwargs)
        return _FakeStream(self._research_text)

    def parse(self, **kwargs):
        self.parse_calls.append(kwargs)
        return _FakeParseResponse(self._parsed_output)


class _FakeAnthropicClient:
    def __init__(self, research_text: str, parsed_output: CorrelationResearchResult):
        self.messages = _FakeMessages(research_text, parsed_output)


def test_research_correlation_update_runs_research_then_structure_pass(monkeypatch):
    fake_result = CorrelationResearchResult.model_validate(SAMPLE_RESULT_UPDATE)
    fake_client = _FakeAnthropicClient("Found Doe et al. (2026)...", fake_result)
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kwargs: fake_client)

    result = research_correlation_update(
        "homopolymer",
        current_version=1,
        current_ln_mfi_coefficient=9.5,
        current_ea_kj_mol=117.5,
        current_reference_temp_C=220.0,
        current_reference_residence_time_min=2.0,
        current_source_citation="Tzoganakis, C. Polym. Eng. Sci. 28(24), 1706-1714 (1988).",
    )

    assert result.update_recommended is True
    assert result.proposal.name == SAMPLE_PROPOSAL["name"]

    # Research pass: web_search tool, no structured output, sees the current correlation.
    assert len(fake_client.messages.stream_calls) == 1
    research_call = fake_client.messages.stream_calls[0]
    assert research_call["model"] == "claude-opus-5"
    assert research_call["system"] == RESEARCH_SYSTEM_PROMPT
    assert research_call["tools"] == [{"type": "web_search_20260209", "name": "web_search"}]
    assert "output_config" not in research_call
    assert "Tzoganakis" in research_call["messages"][0]["content"]

    # Structure pass: no tools, structured output, fed the research pass's text.
    assert len(fake_client.messages.parse_calls) == 1
    structure_call = fake_client.messages.parse_calls[0]
    assert structure_call["model"] == "claude-opus-5"
    assert structure_call["system"] == STRUCTURE_SYSTEM_PROMPT
    assert structure_call["output_format"] is CorrelationResearchResult
    assert "tools" not in structure_call
    assert "Found Doe et al." in structure_call["messages"][0]["content"]


def test_research_correlation_update_no_active_correlation_on_file(monkeypatch):
    fake_result = CorrelationResearchResult.model_validate(SAMPLE_RESULT_NO_UPDATE)
    fake_client = _FakeAnthropicClient("No newer correlation found.", fake_result)
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kwargs: fake_client)

    result = research_correlation_update("impact_pp")

    assert result.update_recommended is False
    research_call = fake_client.messages.stream_calls[0]
    assert "No active correlation currently on file" in research_call["messages"][0]["content"]


def test_research_correlation_update_overrides_mismatched_family_key(monkeypatch):
    mismatched = CorrelationResearchResult.model_validate({**SAMPLE_RESULT_UPDATE, "family_key": "impact_pp"})
    fake_client = _FakeAnthropicClient("...", mismatched)
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kwargs: fake_client)

    result = research_correlation_update("homopolymer")
    assert result.family_key == "homopolymer"


# ---------------------------------------------------------------------------
# API: research -> review -> approve/reject -> promote, agent call mocked
# ---------------------------------------------------------------------------


@pytest.fixture()
def test_session_factory():
    from db.repository import seed_correlation_library, seed_grades_from_json

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
def client(test_session_factory):
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


def test_research_endpoint_creates_pending_row_when_update_recommended(client, monkeypatch):
    fake_result = CorrelationResearchResult.model_validate(SAMPLE_RESULT_UPDATE)
    monkeypatch.setattr("api.main.research_correlation_update", lambda family_key, **kwargs: fake_result)

    r = client.post("/correlations/research", json={"family_key": "homopolymer"})
    assert r.status_code == 200
    body = r.json()
    assert body["update_recommended"] is True
    assert body["pending_correlation_id"] is not None

    list_resp = client.get("/correlations", params={"status": "pending_review"})
    assert any(e["id"] == body["pending_correlation_id"] for e in list_resp.json())


def test_research_endpoint_does_not_create_pending_row_when_no_update(client, monkeypatch):
    fake_result = CorrelationResearchResult.model_validate(SAMPLE_RESULT_NO_UPDATE)
    monkeypatch.setattr("api.main.research_correlation_update", lambda family_key, **kwargs: fake_result)

    r = client.post("/correlations/research", json={"family_key": "impact_pp"})
    assert r.status_code == 200
    body = r.json()
    assert body["update_recommended"] is False
    assert body["pending_correlation_id"] is None


def test_research_endpoint_surfaces_claude_api_error_as_502(client, monkeypatch):
    def boom(family_key, **kwargs):
        raise anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))

    monkeypatch.setattr("api.main.research_correlation_update", boom)
    r = client.post("/correlations/research", json={"family_key": "homopolymer"})
    assert r.status_code == 502


def test_research_endpoint_surfaces_missing_credentials_as_502(client, monkeypatch):
    # anthropic.Anthropic() raises a plain TypeError (not anthropic.APIError)
    # when no credential resolves at all -- reproduces the real failure seen
    # with no ANTHROPIC_API_KEY / ant auth profile configured.
    def boom(family_key, **kwargs):
        raise TypeError(
            "Could not resolve authentication method. Expected one of api_key, "
            "auth_token, or credentials to be set."
        )

    monkeypatch.setattr("api.main.research_correlation_update", boom)
    r = client.post("/correlations/research", json={"family_key": "homopolymer"})
    assert r.status_code == 502
    assert "resolve authentication" in r.json()["detail"]


def test_patch_correlation_applies_reviewer_correction(client, monkeypatch):
    fake_result = CorrelationResearchResult.model_validate(SAMPLE_RESULT_UPDATE)
    monkeypatch.setattr("api.main.research_correlation_update", lambda family_key, **kwargs: fake_result)
    submitted = client.post("/correlations/research", json={"family_key": "homopolymer"}).json()
    pending_id = submitted["pending_correlation_id"]

    detail = client.get(f"/correlations/{pending_id}").json()
    corrected = dict(detail["proposed_json"])
    corrected["ln_mfi_coefficient"] = 10.1

    r = client.patch(f"/correlations/{pending_id}", json={"proposed_json": corrected})
    assert r.status_code == 200
    assert r.json()["proposed_json"]["ln_mfi_coefficient"] == 10.1


def test_patch_correlation_rejects_malformed_correction(client, monkeypatch):
    # approve_pending_correlation dict-indexes proposed_json's required
    # fields with no .get() fallback, so a reviewer correction missing one
    # must be rejected here at PATCH time with a clear 422 -- not accepted
    # and left to blow up as a raw 500 (KeyError) at approval time.
    fake_result = CorrelationResearchResult.model_validate(SAMPLE_RESULT_UPDATE)
    monkeypatch.setattr("api.main.research_correlation_update", lambda family_key, **kwargs: fake_result)
    submitted = client.post("/correlations/research", json={"family_key": "homopolymer"}).json()
    pending_id = submitted["pending_correlation_id"]

    detail = client.get(f"/correlations/{pending_id}").json()
    malformed = dict(detail["proposed_json"])
    del malformed["source_citation"]

    r = client.patch(f"/correlations/{pending_id}", json={"proposed_json": malformed})
    assert r.status_code == 422

    # The original, valid data must still be there -- the bad PATCH didn't partially apply.
    assert client.get(f"/correlations/{pending_id}").json()["proposed_json"]["source_citation"] == SAMPLE_PROPOSAL["source_citation"]


def test_approve_correlation_creates_new_active_version_and_supersedes_old(client, monkeypatch):
    fake_result = CorrelationResearchResult.model_validate(SAMPLE_RESULT_UPDATE)
    monkeypatch.setattr("api.main.research_correlation_update", lambda family_key, **kwargs: fake_result)
    submitted = client.post("/correlations/research", json={"family_key": "homopolymer"}).json()
    pending_id = submitted["pending_correlation_id"]

    r = client.post(f"/correlations/{pending_id}/approve", json={"reviewed_by": "test-reviewer"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "approved"
    assert body["promoted_correlation_pk"] is not None

    # Already decided -- can't approve/patch/reject again. Patch with a
    # validly-shaped payload so the assertion exercises the decided-state
    # guard, not schema validation (that's covered separately below).
    assert client.post(f"/correlations/{pending_id}/approve", json={"reviewed_by": "x"}).status_code == 404
    assert client.patch(f"/correlations/{pending_id}", json={"proposed_json": SAMPLE_PROPOSAL}).status_code == 404


def test_reject_correlation_leaves_active_correlation_unchanged(client, monkeypatch):
    fake_result = CorrelationResearchResult.model_validate(SAMPLE_RESULT_UPDATE)
    monkeypatch.setattr("api.main.research_correlation_update", lambda family_key, **kwargs: fake_result)
    submitted = client.post("/correlations/research", json={"family_key": "homopolymer"}).json()
    pending_id = submitted["pending_correlation_id"]

    r = client.post(
        f"/correlations/{pending_id}/reject",
        json={"reviewed_by": "test-reviewer", "reviewer_notes": "Citation doesn't hold up on review."},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "rejected"
    assert body["promoted_correlation_pk"] is None

    # A visbreaking request for this family should still cite the seeded v1 correlation.
    visbreaking_resp = client.post(
        "/visbreaking", json={"target_properties": {"mfr": 40.0}, "process": "reactive_extrusion"}
    )
    assert visbreaking_resp.status_code == 200
    if visbreaking_resp.json()["solution_found"]:
        assert "Tzoganakis" in (visbreaking_resp.json()["result"]["correlation_source_citation"] or "")
