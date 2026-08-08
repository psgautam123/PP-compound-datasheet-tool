"""PDF -> structured-grade extraction agent (architecture plan §2).

One-shot, offline/async use of the Claude API -- not a persistent agent
loop. Called once per uploaded datasheet; the result lands in the
pending_extractions review queue (db/repository.py) for a human to confirm
or correct before it becomes a searchable grade. engine/* and the rest of
the app never depend on this module staying reachable -- if no Anthropic
credentials are configured, extraction submission fails cleanly and
search/blend/visbreaking keep working against whatever's already approved.

Uses claude-opus-5 with adaptive thinking and structured outputs
(client.messages.parse) so the response is guaranteed to validate against
ExtractedGrade -- see extraction/schema.py for why property keys stay a
free string rather than a fixed enum.
"""
from __future__ import annotations

import base64
from pathlib import Path

import anthropic

from .schema import ExtractedGrade

MODEL = "claude-opus-5"

SYSTEM_PROMPT = """\
You extract structured data from technical datasheets for compounded polypropylene (PP) products.

These are SABIC-style PP compound datasheets. They share a common table template (POLYMER \
PROPERTIES, MECHANICAL PROPERTIES, THERMAL PROPERTIES, FLAMMABILITY PROPERTIES) but the exact \
property set varies by grade -- some report Melt Flow Rate (MFR), some (long-glass-fiber grades) \
do not; some report Izod impact notched, others report Charpy impact notched and unnotched; some \
report tensile/flexural modulus at multiple temperatures, others at a single implied 23°C \
condition. Filler content may be labeled "Filler content" or "Glass fibre content".

Canonical property keys to prefer (snake_case): mfr, tensile_modulus, tensile_stress_yield, \
tensile_stress_break, tensile_strength, tensile_strain_break, flexural_modulus, izod_notched, \
charpy_notched, charpy_unnotched, hdt_a (1.8 MPa), hdt_b (0.45 MPa), clte. If a datasheet reports \
something that genuinely doesn't fit one of these (e.g. Vicat softening temperature, flexural \
strength, strain at yield), invent a clear new snake_case key rather than forcing it into the \
wrong one, and say so in extraction_notes.

For properties reported at multiple temperatures (e.g. tensile modulus at 23°C and 80°C), emit \
ONE entry per temperature with the same key -- do not average or drop either.

If a value is reported as "No Yield", "No Break", or otherwise non-numeric/absent, set value to \
null rather than inventing a number.

Ignore flammability/UL94/GWFI/GWIT detail beyond what fits the schema, and ignore storage/handling \
and disclaimer text entirely -- they're not needed for blend-prediction math.

Use extraction_notes for anything a human reviewer should double-check: uncertain family or \
filler_type classification not explicitly stated in the text, garbled or low-confidence OCR \
values, or property labels you weren't sure how to map.\
"""


def _pdf_to_base64(pdf_path: Path) -> str:
    return base64.standard_b64encode(pdf_path.read_bytes()).decode("utf-8")


def extract_grade_from_pdf(pdf_path: Path, source_pdf_filename: str | None = None) -> ExtractedGrade:
    """Run the extraction agent against a single PDF and return a validated
    ExtractedGrade. Raises whatever the Anthropic SDK raises on auth/network/
    API failure (see shared/error-codes.md) -- callers (the /extractions
    endpoint) are responsible for turning that into an HTTP error.
    """
    client = anthropic.Anthropic()
    filename = source_pdf_filename or pdf_path.name

    response = client.messages.parse(
        model=MODEL,
        max_tokens=8000,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": _pdf_to_base64(pdf_path),
                        },
                    },
                    {
                        "type": "text",
                        "text": f"Extract this datasheet ({filename}) into the schema.",
                    },
                ],
            }
        ],
        output_format=ExtractedGrade,
    )

    grade = response.parsed_output
    if grade.source_pdf != filename:
        grade = grade.model_copy(update={"source_pdf": filename})
    return grade
