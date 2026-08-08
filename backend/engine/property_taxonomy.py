"""Maps canonical property keys to the blend-prediction rule that applies to
them (Workflow2.txt Step 2). This is the dispatch table the blend engine
uses to pick a formula per property; keep it in sync with the keys the
extraction pipeline emits (see backend/data/datasheets.json).
"""
from __future__ import annotations

from enum import Enum


class BlendRule(str, Enum):
    LOG_ADDITIVE_MFR = "log_additive_mfr"
    HALPIN_TSAI_MODULUS = "halpin_tsai_modulus"
    LINEAR_ROM_STRENGTH = "linear_rom_strength"
    EXPONENTIAL_DECAY = "exponential_decay"
    HDT_POWER_LAW = "hdt_power_law"
    LINEAR_VF = "linear_vf"
    ADDITIVE_DENSITY = "additive_density"


# canonical property key -> BlendRule
PROPERTY_BLEND_RULE: dict[str, BlendRule] = {
    "mfr": BlendRule.LOG_ADDITIVE_MFR,
    "tensile_modulus": BlendRule.HALPIN_TSAI_MODULUS,
    "flexural_modulus": BlendRule.HALPIN_TSAI_MODULUS,
    "tensile_stress_yield": BlendRule.LINEAR_ROM_STRENGTH,
    "tensile_stress_break": BlendRule.LINEAR_ROM_STRENGTH,
    "tensile_strength": BlendRule.LINEAR_ROM_STRENGTH,
    "tensile_strain_break": BlendRule.EXPONENTIAL_DECAY,
    "izod_notched": BlendRule.EXPONENTIAL_DECAY,
    "charpy_notched": BlendRule.EXPONENTIAL_DECAY,
    "charpy_unnotched": BlendRule.EXPONENTIAL_DECAY,
    "hdt_a": BlendRule.HDT_POWER_LAW,
    "hdt_b": BlendRule.HDT_POWER_LAW,
    "clte": BlendRule.LINEAR_VF,
}

# Properties usable as the "primary" screening property for candidate grade
# pairs, per Workflow2.txt §9 ("Typically, Melt flow or Tensile modulus is
# used to select the grades").
PRIMARY_SCREENING_KEYS: tuple[str, ...] = ("mfr", "tensile_modulus")

# Impact-type properties that require an unfilled-PP anchor value (same
# family, comparable MFR) per Workflow2.txt §15.
ANCHORED_EXPONENTIAL_KEYS: tuple[str, ...] = (
    "tensile_strain_break",
    "izod_notched",
    "charpy_notched",
    "charpy_unnotched",
)

ACCEPTABLE_MARGIN_FRACTION = 0.05


def blend_rule_for(key: str) -> BlendRule | None:
    return PROPERTY_BLEND_RULE.get(key)
