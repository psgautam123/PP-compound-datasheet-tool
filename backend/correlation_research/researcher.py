"""Correlation-research agent (architecture plan §6): the second bounded
LLM touchpoint. Periodic/on-demand, one-shot use of the Claude API -- not a
persistent agent loop, and never in the request path of /visbreaking.
Checks whether newer or better-validated peer-reviewed peroxide-visbreaking
correlations exist for a PP family than the one currently active in
correlation_library. Proposed updates land in the pending_correlations
review queue (db/repository.py); a human approves before engine.visbreaking
can use them -- this module has no DB access itself.

Two separate Claude calls rather than one:
  1. `_research()` -- Claude + the web_search server tool, plain text
     output. Free to cite sources inline as it searches.
  2. `_structure()` -- a second, tool-free call that converts step 1's
     research text into CorrelationResearchResult via client.messages.parse.
Structured outputs are documented as incompatible with citations (400
error), and Claude's web-search responses carry citations by default, so
combining web_search and output_config/parse in a single call is a live
400 risk -- splitting into a research pass and a structuring pass avoids it
entirely and also gives the human reviewer the raw research trace, not just
the final JSON, if they want to check search_summary against it.
"""
from __future__ import annotations

import anthropic

from .schema import CorrelationResearchResult

MODEL = "claude-opus-5"

RESEARCH_SYSTEM_PROMPT = """\
You are a polymer engineering research assistant checking whether the peroxide-visbreaking \
(reactive extrusion) correlation currently used for a polypropylene (PP) family is still the \
best available, or whether more recent or better-validated peer-reviewed literature exists.

The correlation has the form: ln(MFI) = ln(MFI0) + k * C_eff, where k is a family-specific \
coefficient, C_eff is effective peroxide concentration, and the correlation also carries an \
Arrhenius activation energy (Ea, kJ/mol) for temperature scaling and a reference \
temperature/residence-time the coefficient was measured at.

Search the web for peer-reviewed sources on DCP (dicumyl peroxide) or comparable peroxide \
visbreaking kinetics for the specified PP family. Apply this sourcing hierarchy strictly, in \
order of preference:
  1. Peer-reviewed journals (Polymer Engineering & Science, Polymer Degradation and Stability, \
     Chemical Engineering Science, Polymers, etc.)
  2. Reputed consulting / market-intelligence reports (McKinsey, Wood Mackenzie, ICIS, S&P \
     Global, BloombergNEF)
  3. Patent databases (USPTO, EPO Espacenet, Google Patents) with an explicit patent number
Do not rely on a source below Tier 3, and do not rely on a vendor technical bulletin as your \
primary basis -- it may corroborate but not replace a Tier 1-3 source.

Report what you found in plain text, citing sources inline (author, journal/publisher, year). \
Explicitly state whether what you found is genuinely better than the currently active \
correlation (more recent, wider validated range, or a correction) or not -- do not manufacture \
an improvement just because you found *a* paper. If you find nothing, say so plainly.\
"""

STRUCTURE_SYSTEM_PROMPT = """\
Convert the polymer-correlation research findings below into the required structured format. \
Set update_recommended to true only if the research text itself concludes an update is \
warranted; otherwise false. Only populate `proposal` when update_recommended is true. Keep \
search_summary factual and grounded in the research text -- do not add information that isn't \
there.\
"""


def _current_correlation_description(
    version: int | None,
    ln_mfi_coefficient: float | None,
    ea_kj_mol: float | None,
    reference_temp_C: float | None,
    reference_residence_time_min: float | None,
    source_citation: str | None,
) -> str:
    if version is None:
        return "No active correlation currently on file for this family."
    return (
        f"Currently active (v{version}): ln(MFI) = ln(MFI0) + {ln_mfi_coefficient} * C_eff, "
        f"Ea = {ea_kj_mol} kJ/mol, reference {reference_temp_C} C / "
        f"{reference_residence_time_min} min residence time. Citation: {source_citation}"
    )


def _research(family_key: str, current_description: str) -> str:
    client = anthropic.Anthropic(timeout=180.0)
    response = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        thinking={"type": "adaptive"},
        system=RESEARCH_SYSTEM_PROMPT,
        tools=[{"type": "web_search_20260209", "name": "web_search"}],
        messages=[
            {
                "role": "user",
                "content": (
                    f"PP family: {family_key} (peroxide-visbreaking / reactive extrusion).\n\n"
                    f"{current_description}\n\n"
                    "Search for and report on the current state of the literature for this family."
                ),
            }
        ],
    )
    text = "\n".join(b.text for b in response.content if b.type == "text")
    if not text.strip():
        raise RuntimeError("correlation research agent produced no text output during the web-search pass")
    return text


def _structure(family_key: str, research_text: str) -> CorrelationResearchResult:
    client = anthropic.Anthropic()
    response = client.messages.parse(
        model=MODEL,
        max_tokens=4000,
        thinking={"type": "adaptive"},
        system=STRUCTURE_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Family: {family_key}\n\nResearch findings:\n\n{research_text}",
            }
        ],
        output_format=CorrelationResearchResult,
    )
    result = response.parsed_output
    if result.family_key != family_key:
        result = result.model_copy(update={"family_key": family_key})
    return result


def research_correlation_update(
    family_key: str,
    *,
    current_version: int | None = None,
    current_ln_mfi_coefficient: float | None = None,
    current_ea_kj_mol: float | None = None,
    current_reference_temp_C: float | None = None,
    current_reference_residence_time_min: float | None = None,
    current_source_citation: str | None = None,
) -> CorrelationResearchResult:
    """Run the two-step research -> structure pipeline for one PP family.
    Pass the currently active correlation's parameters (from
    db.repository.get_active_correlation) so the agent can judge whether
    anything it finds is actually an improvement, not just "a paper".
    """
    current_description = _current_correlation_description(
        current_version,
        current_ln_mfi_coefficient,
        current_ea_kj_mol,
        current_reference_temp_C,
        current_reference_residence_time_min,
        current_source_citation,
    )
    research_text = _research(family_key, current_description)
    return _structure(family_key, research_text)
