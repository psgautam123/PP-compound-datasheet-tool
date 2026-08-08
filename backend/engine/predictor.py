"""Step 2 orchestration: screen candidate grade pairs and predict a blend
composition that meets all user-specified properties within the acceptable
margin (Workflow2.txt §8-20).

Design notes:
- The *primary* screening property (mfr or tensile_modulus, whichever the
  user specified -- mfr preferred per §9) picks candidate grade pairs that
  bracket the target, and its blend ratio (phi_a) is solved in closed form.
- Every other user-specified property is then predicted at that same
  phi_a and checked against the target within ACCEPTABLE_MARGIN_FRACTION.
- Modulus defaults to simple linear rule-of-mixtures; Halpin-Tsai is only
  invoked as an escalation when the default misses tolerance and enough
  data is available to calibrate it (Workflow2.txt §13: "use sophisticated
  models ... only when necessary").
"""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations

from . import blend_rules as br
from .models import Grade
from .property_taxonomy import (
    ACCEPTABLE_MARGIN_FRACTION,
    ANCHORED_EXPONENTIAL_KEYS,
    PRIMARY_SCREENING_KEYS,
    BlendRule,
    blend_rule_for,
)

# Literature-default densities for volume-fraction conversion; not measured
# per-lot -- flagged per the truth/accuracy standard for any assumed constant.
GLASS_FIBER_DENSITY_KG_M3 = 2560.0
TALC_DENSITY_KG_M3 = 2750.0

_FILLER_DENSITY_BY_TYPE = {
    "glass_fiber_short": GLASS_FIBER_DENSITY_KG_M3,
    "glass_fiber_long": GLASS_FIBER_DENSITY_KG_M3,
    "talc": TALC_DENSITY_KG_M3,
}


@dataclass
class PropertyPrediction:
    key: str
    target: float
    predicted: float
    relative_error: float
    within_margin: bool
    method: str


@dataclass
class BlendResult:
    grade_a: Grade
    grade_b: Grade
    phi_a: float  # volume fraction of grade_a
    wt_pct_a: float
    predictions: list[PropertyPrediction]
    within_tolerance: bool
    max_relative_error: float = field(init=False)

    def __post_init__(self) -> None:
        self.max_relative_error = max((p.relative_error for p in self.predictions), default=0.0)


def _filler_density(grade: Grade) -> float | None:
    return _FILLER_DENSITY_BY_TYPE.get(grade.filler_type)


def find_unfilled_anchor(grades: list[Grade], family: str, target_mfr: float | None) -> Grade | None:
    """Find an unfilled PP grade (same family) with comparable melt flow,
    per Workflow2.txt §15 ("anchored by the unfilled PP value ... that has
    a comparable melt flow"). Falls back to any unfilled grade of the same
    family if MFR isn't available on either side.
    """
    candidates = [g for g in grades if g.filler_type == "none" and g.family == family]
    if not candidates:
        candidates = [g for g in grades if g.filler_type == "none"]
    if not candidates:
        return None
    if target_mfr is None:
        return candidates[0]

    def mfr_distance(g: Grade) -> float:
        mfr = g.get_one("mfr")
        return abs(mfr.value - target_mfr) if mfr else float("inf")

    return min(candidates, key=mfr_distance)


def screen_candidate_pairs(
    grades: list[Grade], primary_key: str, target_value: float
) -> list[tuple[Grade, Grade, float, float]]:
    """Return (grade_a, grade_b, value_a, value_b) tuples where the primary
    property brackets the target (value_a <= target <= value_b, grade_a the
    lower), sorted by bracket tightness (narrowest span first -- tends to
    minimize extrapolation error in the blend rule).
    """
    with_value = [(g, g.get_one(primary_key)) for g in grades]
    with_value = [(g, pv.value) for g, pv in with_value if pv is not None]

    pairs: list[tuple[Grade, Grade, float, float]] = []
    for (ga, va), (gb, vb) in combinations(with_value, 2):
        lo, hi = (ga, gb) if va <= vb else (gb, ga)
        vlo, vhi = (va, vb) if va <= vb else (vb, va)
        if vlo <= target_value <= vhi and vlo != vhi:
            pairs.append((lo, hi, vlo, vhi))

    pairs.sort(key=lambda t: t[3] - t[2])
    return pairs


def _predict_primary(key: str, value_a: float, value_b: float, phi_a: float) -> float:
    if key == "mfr":
        return br.log_additive_blend(value_a, value_b, phi_a)
    return br.linear_rule_of_mixtures(value_a, value_b, phi_a)


def _solve_phi_a_primary(key: str, target: float, value_a: float, value_b: float) -> float:
    if key == "mfr":
        return br.solve_phi_a_log_additive(target, value_a, value_b)
    return br.solve_phi_a_linear(target, value_a, value_b)


def _blend_filler_vf(grade_a: Grade, grade_b: Grade, phi_a: float) -> float | None:
    fda, fdb = _filler_density(grade_a), _filler_density(grade_b)
    if fda is None or fdb is None:
        return None
    vf_a = grade_a.volume_fraction_filler(fda) or 0.0
    vf_b = grade_b.volume_fraction_filler(fdb) or 0.0
    return phi_a * vf_a + (1.0 - phi_a) * vf_b


def _predict_modulus(
    key: str,
    grade_a: Grade,
    grade_b: Grade,
    phi_a: float,
    target: float,
    anchor: Grade | None,
) -> tuple[float, str]:
    val_a = grade_a.get_one(key, temp_C=23) or grade_a.get_one(key)
    val_b = grade_b.get_one(key, temp_C=23) or grade_b.get_one(key)
    if val_a is None or val_b is None:
        raise ValueError(f"{key} not reported for one of the candidate grades")

    predicted = br.linear_rule_of_mixtures(val_a.value, val_b.value, phi_a)
    rel_err = abs(predicted - target) / target if target else 0.0
    if rel_err <= ACCEPTABLE_MARGIN_FRACTION or anchor is None:
        return predicted, "linear_rom"

    # Escalate to Halpin-Tsai only if we have a matrix (unfilled) modulus
    # and a fiber volume fraction to calibrate against -- per §13, "only
    # when necessary".
    anchor_val = anchor.get_one(key, temp_C=23) or anchor.get_one(key)
    fd_a = _filler_density(grade_a)
    vf_a = grade_a.volume_fraction_filler(fd_a) if fd_a else None
    if anchor_val is None or vf_a is None or not vf_a:
        return predicted, "linear_rom"

    try:
        xi = br.calibrate_halpin_tsai_xi(anchor_val.value, br.E_GLASS_MODULUS_MPA, vf_a, val_a.value)
        blend_vf = _blend_filler_vf(grade_a, grade_b, phi_a)
        if blend_vf is None:
            return predicted, "linear_rom"
        ht_predicted = br.halpin_tsai_modulus(anchor_val.value, br.E_GLASS_MODULUS_MPA, blend_vf, xi)
        return ht_predicted, "halpin_tsai"
    except (ValueError, ZeroDivisionError):
        return predicted, "linear_rom"


def _predict_exponential(
    key: str, grade_a: Grade, grade_b: Grade, phi_a: float, family: str, target_mfr: float | None, grades: list[Grade]
) -> tuple[float, str]:
    anchor = find_unfilled_anchor(grades, family, target_mfr)
    if anchor is None:
        raise ValueError("no unfilled PP anchor grade available for exponential-decay properties")

    condition = {"temp_C": 23}
    anchor_val = anchor.get_one(key, **condition) or anchor.get_one(key)
    val_a = grade_a.get_one(key, **condition) or grade_a.get_one(key)
    val_b = grade_b.get_one(key, **condition) or grade_b.get_one(key)
    if anchor_val is None or (val_a is None and val_b is None):
        raise ValueError(f"insufficient data to anchor exponential decay for {key}")

    fd_a, fd_b = _filler_density(grade_a), _filler_density(grade_b)
    calib_grade, calib_val, calib_fd = (
        (grade_a, val_a, fd_a) if val_a is not None else (grade_b, val_b, fd_b)
    )
    vf_calib = calib_grade.volume_fraction_filler(calib_fd) if calib_fd else None
    if vf_calib is None or not vf_calib:
        raise ValueError(f"cannot compute filler volume fraction to fit decay constant for {key}")

    tail = 0.0
    k = br.fit_decay_constant(anchor_val.value, calib_val.value, vf_calib, tail)
    blend_vf = _blend_filler_vf(grade_a, grade_b, phi_a)
    if blend_vf is None:
        raise ValueError(f"cannot compute blend filler volume fraction for {key}")
    return br.exponential_decay(anchor_val.value, k, blend_vf, tail), "exponential_decay"


def _predict_hdt(
    key: str, grade_a: Grade, grade_b: Grade, phi_a: float, predicted_modulus: float | None
) -> tuple[float, str]:
    hdt_a = grade_a.get_one(key)
    hdt_b = grade_b.get_one(key)
    mod_a = grade_a.get_one("flexural_modulus") or grade_a.get_one("tensile_modulus")
    mod_b = grade_b.get_one("flexural_modulus") or grade_b.get_one("tensile_modulus")
    if hdt_a is None or hdt_b is None or mod_a is None or mod_b is None:
        raise ValueError(f"insufficient modulus/{key} data on candidate grades")

    n = br.calibrate_hdt_exponent(mod_a.value, hdt_a.value, mod_b.value, hdt_b.value)
    e_blend = predicted_modulus if predicted_modulus is not None else br.linear_rule_of_mixtures(
        mod_a.value, mod_b.value, phi_a
    )
    return br.hdt_power_law(hdt_a.value, mod_a.value, e_blend, n), "hdt_power_law_calibrated"


def predict_blend(
    target_properties: dict[str, float],
    grades: list[Grade],
    primary_key: str | None = None,
) -> BlendResult | None:
    """Try candidate grade pairs (tightest bracket first) and return the
    first one that meets every target property within
    ACCEPTABLE_MARGIN_FRACTION, or None if no pair works (Step 3 trigger).
    """
    if primary_key is None:
        primary_key = next((k for k in PRIMARY_SCREENING_KEYS if k in target_properties), None)
    if primary_key is None or primary_key not in target_properties:
        raise ValueError("target_properties must include mfr or tensile_modulus to screen candidate pairs")

    target_primary = target_properties[primary_key]
    candidates = screen_candidate_pairs(grades, primary_key, target_primary)

    results: list[BlendResult] = []
    for grade_a, grade_b, val_a, val_b in candidates:
        try:
            phi_a = _solve_phi_a_primary(primary_key, target_primary, val_a, val_b)
        except (ValueError, ZeroDivisionError):
            continue
        if not (0.0 <= phi_a <= 1.0):
            continue

        family = grade_a.family
        target_mfr = target_properties.get("mfr")
        predictions: list[PropertyPrediction] = []
        predicted_modulus: float | None = None
        failed = False

        for key, target in target_properties.items():
            rule = blend_rule_for(key)
            try:
                if key == primary_key:
                    predicted = _predict_primary(key, val_a, val_b, phi_a)
                    method = "log_additive" if key == "mfr" else "linear_rom"
                elif rule == BlendRule.HALPIN_TSAI_MODULUS:
                    anchor = find_unfilled_anchor(grades, family, target_mfr)
                    predicted, method = _predict_modulus(key, grade_a, grade_b, phi_a, target, anchor)
                    predicted_modulus = predicted
                elif rule == BlendRule.LINEAR_ROM_STRENGTH or rule == BlendRule.LINEAR_VF:
                    pv_a = grade_a.get_one(key)
                    pv_b = grade_b.get_one(key)
                    if pv_a is None or pv_b is None:
                        raise ValueError(f"{key} not reported for one of the candidate grades")
                    predicted = br.linear_rule_of_mixtures(pv_a.value, pv_b.value, phi_a)
                    method = "linear_rom"
                elif rule == BlendRule.EXPONENTIAL_DECAY or key in ANCHORED_EXPONENTIAL_KEYS:
                    predicted, method = _predict_exponential(
                        key, grade_a, grade_b, phi_a, family, target_mfr, grades
                    )
                elif rule == BlendRule.HDT_POWER_LAW:
                    predicted, method = _predict_hdt(key, grade_a, grade_b, phi_a, predicted_modulus)
                elif rule == BlendRule.ADDITIVE_DENSITY:
                    if grade_a.density_kg_m3 is None or grade_b.density_kg_m3 is None:
                        raise ValueError("density not reported for one of the candidate grades")
                    predicted = br.linear_rule_of_mixtures(grade_a.density_kg_m3, grade_b.density_kg_m3, phi_a)
                    method = "linear_rom"
                else:
                    raise ValueError(f"no blend rule registered for property '{key}'")
            except ValueError:
                failed = True
                break

            rel_err = abs(predicted - target) / target if target else 0.0
            predictions.append(
                PropertyPrediction(
                    key=key,
                    target=target,
                    predicted=predicted,
                    relative_error=rel_err,
                    within_margin=rel_err <= ACCEPTABLE_MARGIN_FRACTION,
                    method=method,
                )
            )

        if failed or not predictions:
            continue

        wt_pct_a = br.volume_fraction_to_wt_pct(phi_a, grade_a.density_kg_m3 or 900.0, grade_b.density_kg_m3 or 900.0)
        result = BlendResult(
            grade_a=grade_a,
            grade_b=grade_b,
            phi_a=phi_a,
            wt_pct_a=wt_pct_a,
            predictions=predictions,
            within_tolerance=all(p.within_margin for p in predictions),
        )
        results.append(result)
        if result.within_tolerance:
            return result

    # No pair satisfied every property within tolerance; surface the closest
    # attempt's diagnostics via caller inspection if needed, but per
    # Workflow2.txt this is a "no solution" -> Step 3 trigger.
    return None
