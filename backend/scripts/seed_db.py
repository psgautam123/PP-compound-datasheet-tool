"""Seed the database with the extracted datasheet grades and the default
peroxide-visbreaking correlation library. Run after `alembic upgrade head`:

    .venv/Scripts/python scripts/seed_db.py

Idempotent -- safe to run multiple times; only missing rows are inserted.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.repository import seed_correlation_library, seed_grades_from_json
from db.session import SessionLocal


def main() -> None:
    session = SessionLocal()
    try:
        n_grades = seed_grades_from_json(session)
        n_correlations = seed_correlation_library(session)
    finally:
        session.close()
    print(f"Inserted {n_grades} new grade(s), {n_correlations} new correlation(s).")


if __name__ == "__main__":
    main()
