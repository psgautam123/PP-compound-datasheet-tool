"""Structured-output schema for the correlation-research agent (architecture
plan §6). Mirrors the fields of db.models.CorrelationLibraryRow that a human
reviewer would need to approve a new version, plus `search_summary` so the
reviewer sees what was searched even when no update is proposed.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class CorrelationProposal(BaseModel):
    family_key: str = Field(description="'homopolymer' or 'impact_pp' -- must match the family this search was run for.")
    name: str = Field(description="Short human-readable name for this correlation, e.g. 'Homopolymer PP DCP visbreaking (2026 update)'.")
    ln_mfi_coefficient: float = Field(description="Coefficient k in ln(MFI) = ln(MFI0) + k * C_eff.")
    ea_kj_mol: float = Field(description="Arrhenius activation energy in kJ/mol for temperature-scaling the correlation.")
    reference_temp_C: float = Field(description="Processing temperature (deg C) the coefficient was measured/reported at.")
    reference_residence_time_min: float = Field(description="Residence time (min) the coefficient was measured/reported at.")
    source_citation: str = Field(
        description=(
            "Full citation(s) for this correlation, Tier 1-3 per the sourcing hierarchy: "
            "peer-reviewed journal article preferred (author, journal, volume, pages, year); "
            "reputed consulting/market-intelligence report next; patent number as a last resort. "
            "Must include enough detail for a human to independently verify the source."
        )
    )
    rationale: str = Field(
        description=(
            "Why this should replace the currently active correlation -- e.g. more recent "
            "peer-reviewed measurement, a wider validated composition/temperature range, or a "
            "correction of an error in the currently active value. Not a restatement of the citation."
        )
    )


class CorrelationResearchResult(BaseModel):
    family_key: str
    update_recommended: bool = Field(
        description=(
            "True only if the literature search found a genuine improvement over the currently "
            "active correlation. False if nothing found meaningfully improves on it -- do not "
            "propose a change just because a paper was found."
        )
    )
    proposal: CorrelationProposal | None = Field(
        default=None, description="Required when update_recommended is true; omit otherwise."
    )
    search_summary: str = Field(
        description="Brief summary (a few sentences) of what was searched and found, for the human reviewer, regardless of update_recommended."
    )
