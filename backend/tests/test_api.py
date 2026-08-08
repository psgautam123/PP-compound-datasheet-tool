"""End-to-end tests for the FastAPI layer (api/main.py), against an
isolated in-memory SQLite database seeded from the real datasheet JSON --
not the dev-file DB (backend/data/app.db), so tests never depend on or
mutate it. Schema-equivalent to the Postgres DDL in migrations/versions/
(same db/models.py); no local Postgres/Docker is available in this
environment to run the real thing end-to-end, so this is the closest
practical substitute -- see db/session.py's module docstring.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.main import app
from db.models import Base
from db.repository import seed_correlation_library, seed_grades_from_json
from db.session import get_session


@pytest.fixture(scope="module")
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
def client(test_session_factory):
    def override_get_session():
        session = test_session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_list_grades_returns_all_18(client):
    r = client.get("/grades")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 18
    assert {"grade_id", "family", "filler_type", "mfr", "tensile_modulus"} <= body[0].keys()


def test_get_grade_detail(client):
    r = client.get("/grades/H1015")
    assert r.status_code == 200
    body = r.json()
    assert body["grade_id"] == "H1015"
    assert body["source_pdf"] == "SABIC-EE-MF15-SGF15-H1015.pdf"
    assert any(p["key"] == "mfr" and p["value"] == 15 for p in body["properties"])


def test_get_grade_detail_404_for_unknown(client):
    r = client.get("/grades/NOT_A_GRADE")
    assert r.status_code == 404


def test_get_datasheet_serves_pdf(client):
    r = client.get("/grades/H1015/datasheet")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"


def test_get_datasheet_404_for_unknown_grade(client):
    r = client.get("/grades/NOT_A_GRADE/datasheet")
    assert r.status_code == 404


def test_search_exact_match(client):
    r = client.post("/search", json={"target_properties": {"mfr": 15, "tensile_modulus": 4700}})
    assert r.status_code == 200
    matches = r.json()["matches"]
    assert matches[0]["grade"]["grade_id"] == "H1015"
    assert matches[0]["source_pdf"] == "SABIC-EE-MF15-SGF15-H1015.pdf"


def test_search_no_match_returns_empty_list(client):
    r = client.post("/search", json={"target_properties": {"mfr": 15, "hdt_a": 999}})
    assert r.status_code == 200
    assert r.json()["matches"] == []


def test_blend_solution_found(client):
    r = client.post("/blend", json={"target_properties": {"mfr": 12, "flexural_modulus": 5500}})
    assert r.status_code == 200
    body = r.json()
    assert body["solution_found"] is True
    assert body["result"]["within_tolerance"] is True
    assert body["visbreaking_prompt"] is None


def test_blend_no_solution_returns_visbreaking_prompt(client):
    # tensile_modulus target unreachable by any bracketing pair in the dataset
    r = client.post("/blend", json={"target_properties": {"mfr": 12, "tensile_modulus": 50000}})
    assert r.status_code == 200
    body = r.json()
    assert body["solution_found"] is False
    assert body["result"] is None
    assert body["visbreaking_prompt"].startswith("No solution was found.")


def test_blend_requires_primary_property(client):
    r = client.post("/blend", json={"target_properties": {"hdt_a": 140}})
    assert r.status_code == 400


def test_visbreaking_solution_found_with_citation(client):
    r = client.post("/visbreaking", json={"target_properties": {"mfr": 20, "tensile_modulus": 4000}})
    assert r.status_code == 200
    body = r.json()
    assert body["solution_found"] is True
    assert body["result"]["base_grade"]["grade_id"] == "H1015"
    assert body["result"]["peroxide_dose_wt_pct"] > 0
    assert body["result"]["correlation_source_citation"] is not None
    assert len(body["result"]["doe"]) == 9


def test_visbreaking_no_candidate_returns_false(client):
    r = client.post("/visbreaking", json={"target_properties": {"mfr": 1}})
    assert r.status_code == 200
    body = r.json()
    assert body["solution_found"] is False
    assert body["result"] is None


def test_visbreaking_requires_mfr(client):
    r = client.post("/visbreaking", json={"target_properties": {"tensile_modulus": 4000}})
    assert r.status_code == 400
