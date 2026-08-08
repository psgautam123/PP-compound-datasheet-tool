"""Step 3: reactive-extrusion (peroxide visbreaking) fallback, triggered when
Step 2 (predictor.predict_blend) finds no blend solution (Workflow2.txt
§21-57).

Correlations are the curated defaults seeded from Workflow2.txt's cited
references (Tzoganakis 1988; Rocha 1995; Azizi 2004; Iedema 2001; Berzin
2022; Stanic 2022; ExxonMobil/LyondellBasell CR-PP technical bulletins) --
see the architecture plan's `correlation_library` concept. These are
DCP/DHBP heuristics for standard reactive-extrusion conditions (200-230 C,
1-3 min residence); treat all outputs as a starting point for the
factorial-DOE validation this module also generates, not a guaranteed
result -- flagged per the workflow's own framing ("heuristics drawn from
peer-reviewed studies", not exact first-principles kinetics).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

from .models import Grade

NO_SOLUTION_PROMPT = (
    "No solution was found. Would you like me to look at what options are "
    "available if we use peroxides to control melt flow via visbreaking in "
    "a reactive extrusion operation?"
)

# ln(MFI) = ln(MFI0) + coefficient * C_DCP(wt%), empirical fit at 220 C
# (Workflow2.txt §38, §46).
PEROXIDE_LN_MFI_COEFFICIENT = {
    "homopolymer": 9.5,
    "impact_pp": 7.0,
}

# The source correlations only distinguish homopolymer vs. impact
# (heterophasic/rubber-modified) PP. Plain random copolymers (SABIC
# `family == "copolymer"`, e.g. H1200) aren't covered separately -- they
# lack the rubber phase that moderates scission in impact PP, so they're
# approximated with the homopolymer coefficient here. This is an
# assumption, not a literature-backed value for that specific case --
# recommend a confirmatory DOE run before committing to it in production.
FAMILY_TO_PEROXIDE_KEY: dict[str, Literal["homopolymer", "impact_pp"]] = {
    "homopolymer": "homopolymer",
    "copolymer": "homopolymer",
    "impact_copolymer": "impact_pp",
}

REFERENCE_TEMP_C = 220.0  # "empirical fit at 220 C", Workflow2.txt §37, §45
# Not explicitly pinned in the workflow beyond "processed ... for ~1-3 min
# residence time" -- midpoint of that stated range, used as the reference
# residence time the base ln(MFI) correlation is assumed calibrated at.
REFERENCE_RESIDENCE_TIME_MIN = 2.0
DEFAULT_EA_KJ_MOL = 117.5  # midpoint of the stated 110-125 kJ/mol range (Workflow2.txt §51)
GAS_CONSTANT_J_MOL_K = 8.314

PROCESS_PRESETS: dict[str, dict[str, float]] = {
    # Reactive extrusion: matches the correlations' reference conditions.
    "reactive_extrusion": {"temp_C": REFERENCE_TEMP_C, "residence_time_min": REFERENCE_RESIDENCE_TIME_MIN},
    # Injection molding: short residence time -> needs a much higher dose
    # for the same MFI shift (Workflow2.txt §54-56); 0.75 min is the
    # midpoint of the stated 0.5-1 min range.
    "injection_molding": {"temp_C": REFERENCE_TEMP_C, "residence_time_min": 0.75},
}

DEFAULT_OVERSHOOT_FRACTION = 0.05  # midpoint of the workflow's stated 0-10% overshoot band (§25)
DOE_FACTOR_LEVELS = (-0.20, 0.0, 0.20)  # "conditions that are within 20% of the predicted value" (§57)


def _dose_scale_factor(
    temp_C: float,
    residence_time_min: float,
    ea_kj_mol: float = DEFAULT_EA_KJ_MOL,
    temp_ref_C: float = REFERENCE_TEMP_C,
    t_ref_min: float = REFERENCE_RESIDENCE_TIME_MIN,
) -> float:
    """Effective-dose multiplier relative to reference conditions:
    dose ~ C * t * exp(-Ea/RT) (Workflow2.txt §55), normalized so the
    multiplier is 1.0 at (temp_ref_C, t_ref_min).
    """
    ea_j_mol = ea_kj_mol * 1000.0
    t_k = temp_C + 273.15
    t_ref_k = temp_ref_C + 273.15
    temp_scale = math.exp(-ea_j_mol / GAS_CONSTANT_J_MOL_K * (1.0 / t_k - 1.0 / t_ref_k))
    time_scale = residence_time_min / t_ref_min
    return temp_scale * time_scale


def peroxide_coefficient_for_family(family: str) -> float:
    key = FAMILY_TO_PEROXIDE_KEY.get(family)
    if key is None:
        raise ValueError(f"no peroxide visbreaking correlation registered for family '{family}'")
    return PEROXIDE_LN_MFI_COEFFICIENT[key]


def predict_mfi_after_visbreaking(
    mfi0: float,
    c_dcp_wt_pct: float,
    family: str,
    temp_C: float = REFERENCE_TEMP_C,
    residence_time_min: float = REFERENCE_RESIDENCE_TIME_MIN,
    ea_kj_mol: float = DEFAULT_EA_KJ_MOL,
    coefficient: float | None = None,
) -> float:
    """`coefficient` overrides the built-in family lookup -- used by the API
    layer to pass whatever correlation_library row is currently active in
    the DB (see db/repository.get_active_correlation) instead of the
    hardcoded default, without engine/* needing any DB awareness itself.
    """
    coeff = coefficient if coefficient is not None else peroxide_coefficient_for_family(family)
    scale = _dose_scale_factor(temp_C, residence_time_min, ea_kj_mol)
    c_eff = c_dcp_wt_pct * scale
    return math.exp(math.log(mfi0) + coeff * c_eff)


def solve_peroxide_dose(
    mfi0: float,
    target_mfi: float,
    family: str,
    temp_C: float = REFERENCE_TEMP_C,
    residence_time_min: float = REFERENCE_RESIDENCE_TIME_MIN,
    ea_kj_mol: float = DEFAULT_EA_KJ_MOL,
    coefficient: float | None = None,
) -> float:
    """Closed-form inversion of predict_mfi_after_visbreaking for C_DCP wt%.
    See predict_mfi_after_visbreaking for the `coefficient` override."""
    if target_mfi <= mfi0:
        raise ValueError("target_mfi must exceed the base grade's mfi0 -- visbreaking only increases melt flow")
    coeff = coefficient if coefficient is not None else peroxide_coefficient_for_family(family)
    scale = _dose_scale_factor(temp_C, residence_time_min, ea_kj_mol)
    if scale <= 0:
        raise ValueError("dose scale factor must be positive")
    c_eff_needed = (math.log(target_mfi) - math.log(mfi0)) / coeff
    return c_eff_needed / scale


def screen_visbreaking_base_grades(
    target_properties: dict[str, float], grades: list[Grade]
) -> list[Grade]:
    """Find grades with lower melt flow than the target but higher tensile
    modulus (Workflow2.txt §24), sorted so the grade requiring the least
    peroxide (smallest MFR gap to close) comes first. If a tensile_modulus
    target is given, a grade missing that property is excluded rather than
    assumed to pass.
    """
    if "mfr" not in target_properties:
        raise ValueError("target_properties must include 'mfr' to screen visbreaking base grades")
    target_mfr = target_properties["mfr"]
    target_modulus = target_properties.get("tensile_modulus")

    candidates: list[tuple[float, Grade]] = []
    for grade in grades:
        mfr = grade.get_one("mfr")
        if mfr is None or mfr.value >= target_mfr:
            continue
        if target_modulus is not None:
            modulus = grade.get_one("tensile_modulus")
            if modulus is None or modulus.value < target_modulus:
                continue
        candidates.append((target_mfr - mfr.value, grade))

    candidates.sort(key=lambda t: t[0])
    return [g for _, g in candidates]


@dataclass
class DoeRun:
    dose_wt_pct: float
    temp_C: float
    residence_time_min: float
    predicted_mfi: float


@dataclass
class VisbreakingProposal:
    base_grade: Grade
    target_mfr: float
    final_mfi_design_point: float
    peroxide_dose_wt_pct: float
    process: str
    temp_C: float
    residence_time_min: float
    peroxide_family_key: str
    doe: list[DoeRun] = field(default_factory=list)


def generate_doe(
    base_grade: Grade,
    dose_wt_pct: float,
    temp_C: float,
    residence_time_min: float,
    family: str,
    levels: tuple[float, ...] = DOE_FACTOR_LEVELS,
    ea_kj_mol: float = DEFAULT_EA_KJ_MOL,
    coefficient: float | None = None,
) -> list[DoeRun]:
    """Small full-factorial DOE crossing peroxide dose and residence time at
    +/-20% around the predicted values (temperature held at nominal).

    Dose and residence time are both ratio-scale quantities (a meaningful
    zero), so a +/-20% *percentage* perturbation is physically sound for
    them. Temperature in Celsius is not a ratio scale -- a naive +/-20% on
    e.g. 220 C would swing to 264 C, which can exceed a grade's stated
    processing ceiling (one datasheet in this dataset caps at 240 C) and
    risk thermal degradation rather than a controlled visbreaking trial.
    Temperature is therefore fixed at the nominal process condition here;
    vary it manually with a small, plant-appropriate absolute delta (e.g.
    +/-10 C) if a temperature factor is wanted.

    Each run's predicted MFI is included as a starting expectation; actual
    validation requires physical trials per Workflow2.txt §57.
    """
    mfi0 = base_grade.get_one("mfr").value
    runs: list[DoeRun] = []
    for dose_delta in levels:
        for time_delta in levels:
            run_dose = dose_wt_pct * (1.0 + dose_delta)
            run_time = residence_time_min * (1.0 + time_delta)
            predicted = predict_mfi_after_visbreaking(
                mfi0, run_dose, family, temp_C, run_time, ea_kj_mol, coefficient
            )
            runs.append(
                DoeRun(dose_wt_pct=run_dose, temp_C=temp_C, residence_time_min=run_time, predicted_mfi=predicted)
            )
    return runs


def propose_visbreaking(
    target_properties: dict[str, float],
    grades: list[Grade],
    process: str = "reactive_extrusion",
    temp_C: float | None = None,
    residence_time_min: float | None = None,
    overshoot_fraction: float = DEFAULT_OVERSHOOT_FRACTION,
    ea_kj_mol: float = DEFAULT_EA_KJ_MOL,
    coefficient: float | None = None,
) -> VisbreakingProposal | None:
    """End-to-end Step 3: screen for a base grade, solve the peroxide dose
    to land 0-10% above the user's target MFR (design point defaults to the
    midpoint, 5%), and attach a validation DOE. Returns None if no base
    grade satisfies the screening criteria (§24).
    """
    if not (0.0 <= overshoot_fraction <= 0.10):
        raise ValueError("overshoot_fraction must be within the workflow's specified 0-10% band")
    if process not in PROCESS_PRESETS:
        raise ValueError(f"unknown process preset '{process}'; expected one of {list(PROCESS_PRESETS)}")

    preset = PROCESS_PRESETS[process]
    resolved_temp_C = temp_C if temp_C is not None else preset["temp_C"]
    resolved_residence_time_min = residence_time_min if residence_time_min is not None else preset["residence_time_min"]

    candidates = screen_visbreaking_base_grades(target_properties, grades)
    if not candidates:
        return None
    base_grade = candidates[0]

    target_mfr = target_properties["mfr"]
    final_mfi_design_point = target_mfr * (1.0 + overshoot_fraction)
    peroxide_key = FAMILY_TO_PEROXIDE_KEY.get(base_grade.family)
    if peroxide_key is None:
        return None

    mfi0 = base_grade.get_one("mfr").value
    dose = solve_peroxide_dose(
        mfi0,
        final_mfi_design_point,
        base_grade.family,
        resolved_temp_C,
        resolved_residence_time_min,
        ea_kj_mol,
        coefficient,
    )
    doe = generate_doe(
        base_grade,
        dose,
        resolved_temp_C,
        resolved_residence_time_min,
        base_grade.family,
        ea_kj_mol=ea_kj_mol,
        coefficient=coefficient,
    )

    return VisbreakingProposal(
        base_grade=base_grade,
        target_mfr=target_mfr,
        final_mfi_design_point=final_mfi_design_point,
        peroxide_dose_wt_pct=dose,
        process=process,
        temp_C=resolved_temp_C,
        residence_time_min=resolved_residence_time_min,
        peroxide_family_key=peroxide_key,
        doe=doe,
    )
