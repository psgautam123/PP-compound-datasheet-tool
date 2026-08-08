"""Load the extracted datasheet JSON (backend/data/datasheets.json) into
Grade/PropertyValue objects. This stands in for the eventual DB-backed
extraction pipeline (see architecture plan §1-2) -- same target schema,
file-based for now so the engine can be developed/tested without a running
Postgres instance.
"""
from __future__ import annotations

import json
from pathlib import Path

from .models import Grade, PropertyValue

DEFAULT_DATASHEETS_PATH = Path(__file__).resolve().parent.parent / "data" / "datasheets.json"


def load_grades(path: Path | str = DEFAULT_DATASHEETS_PATH) -> list[Grade]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    grades: list[Grade] = []
    for entry in raw:
        properties = tuple(
            PropertyValue(
                key=p["key"],
                cls=p["class"],
                value=p["value"],
                unit=p["unit"],
                condition=p.get("condition") or {},
                test_method=p.get("test_method"),
            )
            for p in entry["properties"]
            if p["value"] is not None  # drop "No Yield"/"No Break"/unreported rows
        )
        grades.append(
            Grade(
                grade_id=entry["grade_id"],
                product_name=entry["product_name"],
                source_pdf=entry["source_pdf"],
                family=entry["family"],
                filler_type=entry["filler_type"],
                filler_content_pct=entry.get("filler_content_pct"),
                density_kg_m3=entry.get("density_kg_m3"),
                mould_shrinkage_pct=entry.get("mould_shrinkage_pct"),
                properties=properties,
            )
        )
    return grades
