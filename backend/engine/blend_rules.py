"""Property-blending formulas for Workflow2.txt Step 2.

Every function is pure and takes plain floats (no I/O, no DB access) so it
can be unit-tested against hand-computed or literature values in isolation
from the grade-search / pair-screening layer. Volume fraction `phi_a` is
always "fraction of grade A in the blend" unless noted otherwise.

Sources for the formulas: Workflow2.txt §8-19 (client-provided workflow).
Standard forms (Halpin-Tsai, Krieger-Dougherty) are widely published
composite-mechanics results; see e.g. Halpin & Kardos (1976) and Krieger &
Dougherty (1959) for the canonical derivations. Numeric constants used as
defaults (E-glass modulus, packing fraction) are typical textbook values,
not measured for these specific SABIC grades -- flagged inline.
"""
from __future__ import annotations

import math

from scipy.optimize import brentq

# ---------------------------------------------------------------------------
# Composition conversion
# ---------------------------------------------------------------------------


def wt_pct_to_volume_fraction(wt_pct_a: float, density_a: float, density_b: float) -> float:
    """Convert grade-A weight fraction (0-100) in an A/B blend to A's volume
    fraction, given each grade's bulk density (kg/m3)."""
    wa = wt_pct_a / 100.0
    wb = 1.0 - wa
    va = wa / density_a
    vb = wb / density_b
    return va / (va + vb)


def volume_fraction_to_wt_pct(vol_frac_a: float, density_a: float, density_b: float) -> float:
    """Inverse of wt_pct_to_volume_fraction."""
    mass_a = vol_frac_a * density_a
    mass_b = (1.0 - vol_frac_a) * density_b
    return 100.0 * mass_a / (mass_a + mass_b)


# ---------------------------------------------------------------------------
# Melt flow: log-additivity (Workflow2.txt §12)
# ---------------------------------------------------------------------------


def log_additive_blend(value_a: float, value_b: float, phi_a: float) -> float:
    """ln(MFI_blend) = phi_a*ln(MFI_a) + (1-phi_a)*ln(MFI_b).

    Applied on volume fraction per the workflow's explicit "convert wt% to
    vol%" step preceding all rule-of-mixtures calculations, so this uses
    phi_a consistently rather than weight fraction (a common alternative
    convention in the melt-viscosity-blending literature -- flagged here
    since the two conventions diverge when the two grades' densities
    differ materially, e.g. differing glass-fiber loadings).
    """
    ln_blend = phi_a * math.log(value_a) + (1.0 - phi_a) * math.log(value_b)
    return math.exp(ln_blend)


def solve_phi_a_log_additive(target: float, value_a: float, value_b: float) -> float:
    """Closed-form inversion of log_additive_blend for phi_a."""
    return (math.log(target) - math.log(value_b)) / (math.log(value_a) - math.log(value_b))


def krieger_dougherty_relative_viscosity(
    phi_filler: float, phi_max: float = 0.62, intrinsic_viscosity: float = 2.5
) -> float:
    """eta_r = (1 - phi/phi_max) ** (-[eta] * phi_max).

    Standard Krieger-Dougherty form (Krieger & Dougherty, 1959). Defaults
    (phi_max=0.62 random close packing, intrinsic viscosity 2.5) are the
    classic values for rigid spheres -- reasonable order-of-magnitude
    defaults for glass fiber per Workflow2.txt §12, but should be replaced
    with fiber-specific calibrated values when available; treat results as
    approximate.
    """
    if phi_filler >= phi_max:
        raise ValueError("phi_filler must be below phi_max (rheological percolation limit)")
    return (1.0 - phi_filler / phi_max) ** (-intrinsic_viscosity * phi_max)


def krieger_dougherty_mfr_adjustment(
    mfr_baseline: float,
    phi_filler_baseline: float,
    phi_filler_target: float,
    phi_max: float = 0.62,
    intrinsic_viscosity: float = 2.5,
) -> float:
    """Rescale an MFR predicted by simple log-additivity to account for a
    difference in total glass-fiber volume fraction, using the assumption
    MFR ~ 1/relative_viscosity at fixed test conditions (ISO 1133 fixed
    shear stress). This is an approximation -- MFR-viscosity conversion
    ignores shear-thinning non-Newtonian effects -- appropriate only as a
    secondary correction on top of log-additivity, per Workflow2.txt §12's
    guidance to use "good quality correlations" for filled PP.
    """
    eta_r_base = krieger_dougherty_relative_viscosity(phi_filler_baseline, phi_max, intrinsic_viscosity)
    eta_r_target = krieger_dougherty_relative_viscosity(phi_filler_target, phi_max, intrinsic_viscosity)
    return mfr_baseline * (eta_r_base / eta_r_target)


# ---------------------------------------------------------------------------
# Elastic modulus: linear rule-of-mixtures (default) / Halpin-Tsai (Workflow2.txt §13)
# ---------------------------------------------------------------------------


def linear_rule_of_mixtures(value_a: float, value_b: float, phi_a: float) -> float:
    """Simple Voigt (parallel) rule of mixtures: value = phi_a*A + (1-phi_a)*B.

    Default for blending two already-compounded grades' bulk properties
    (modulus, strength, density, CLTE, shrinkage) directly -- i.e. treating
    each commercial grade as one "phase" of the blend. Workflow2.txt §13
    reserves Halpin-Tsai/Tandon-Weng/Mori-Tanaka for when this is
    insufficient (e.g. when the two grades differ enough in fiber loading
    that treating them as two phases at the pellet level misses the
    change in the underlying fiber network).
    """
    return phi_a * value_a + (1.0 - phi_a) * value_b


def solve_phi_a_linear(target: float, value_a: float, value_b: float) -> float:
    """Closed-form inversion of linear_rule_of_mixtures for phi_a."""
    return (target - value_b) / (value_a - value_b)


def halpin_tsai_modulus(e_matrix: float, e_filler: float, vf_filler: float, xi: float = 2.0) -> float:
    """Halpin-Tsai composite modulus (Halpin & Kardos, 1976):

        eta = (Ef/Em - 1) / (Ef/Em + xi)
        E   = Em * (1 + xi*eta*Vf) / (1 - eta*Vf)

    `xi` is the shape/reinforcement-efficiency parameter (commonly ~2 for
    short-fiber composites, higher for long/aligned fiber, ~0.5-1 for
    randomly-oriented). Use `calibrate_halpin_tsai_xi` to fit xi against a
    known compounded grade of the same fiber type rather than assuming the
    textbook default, since chopped short-glass and long-glass (STAMAX)
    systems have materially different effective xi.
    """
    ratio = e_filler / e_matrix
    eta = (ratio - 1.0) / (ratio + xi)
    return e_matrix * (1.0 + xi * eta * vf_filler) / (1.0 - eta * vf_filler)


def calibrate_halpin_tsai_xi(
    e_matrix: float, e_filler: float, vf_known: float, e_known: float
) -> float:
    """Solve for the xi that reproduces a known (Vf, E) data point from an
    existing datasheet, so halpin_tsai_modulus can be extrapolated to a new
    target Vf for the *same* fiber/matrix system with a calibrated,
    literature-appropriate shape factor instead of an assumed one.
    """

    def residual(xi: float) -> float:
        return halpin_tsai_modulus(e_matrix, e_filler, vf_known, xi) - e_known

    return brentq(residual, 1e-3, 50.0)


E_GLASS_MODULUS_MPA = 72_400.0  # typical E-glass fiber tensile modulus; literature default, not measured per-lot


# ---------------------------------------------------------------------------
# Strength (Workflow2.txt §14) -- no sophisticated model specified; linear ROM
# ---------------------------------------------------------------------------

# tensile_stress_yield / tensile_stress_break / tensile_strength all use
# linear_rule_of_mixtures directly (re-exported via property_taxonomy).


# ---------------------------------------------------------------------------
# Strain-at-break / impact: anchored exponential decay (Workflow2.txt §15)
# ---------------------------------------------------------------------------


def exponential_decay(value_unfilled: float, k: float, vf_filler: float, tail: float = 0.0) -> float:
    """value(Vf) = tail + (value_unfilled - tail) * exp(-k * Vf).

    tail=0 reduces to the plain strain-at-break form given in the workflow
    (e_b(Vf) = e_b0 * exp(-k*Vf)); tail>0 matches the Izod form with an
    asymptote (I(Vf) = I0*exp(-k*Vf) + I_inf).
    """
    return tail + (value_unfilled - tail) * math.exp(-k * vf_filler)


def fit_decay_constant(
    value_unfilled: float, value_known: float, vf_known: float, tail: float = 0.0
) -> float:
    """Calibrate k from one known (Vf, value) point (e.g. one of the two
    bracketing grades) anchored at the unfilled-PP value, per Workflow2.txt
    §15 ("anchored by the unfilled PP value ... located in another
    datasheet that has a comparable melt flow").
    """
    if vf_known <= 0:
        raise ValueError("vf_known must be > 0 to fit a decay constant")
    ratio = (value_known - tail) / (value_unfilled - tail)
    if not (0.0 < ratio <= 1.0):
        raise ValueError(
            "value_known must lie between tail and value_unfilled (decay curves "
            "cannot increase filled-property values above the unfilled anchor)"
        )
    return -math.log(ratio) / vf_known


# ---------------------------------------------------------------------------
# HDT: correlated with modulus (Workflow2.txt §17)
# ---------------------------------------------------------------------------


def hdt_power_law(hdt_ref: float, e_ref: float, e_target: float, n: float = 0.4) -> float:
    """HDT scales with E^n, n typically 0.3-0.5 per the workflow. Default
    n=0.4 (mid-range); prefer `calibrate_hdt_exponent` when two known
    (E, HDT) data points are available (e.g. the two bracketing grades),
    since n varies by resin family.
    """
    return hdt_ref * (e_target / e_ref) ** n


def calibrate_hdt_exponent(e1: float, hdt1: float, e2: float, hdt2: float) -> float:
    """n = ln(HDT2/HDT1) / ln(E2/E1), fit from two known grades."""
    return math.log(hdt2 / hdt1) / math.log(e2 / e1)


# ---------------------------------------------------------------------------
# CLTE / mould shrinkage / density: linear with volume fraction (Workflow2.txt §16, 18)
# ---------------------------------------------------------------------------

# All use linear_rule_of_mixtures directly: blending two grades linearly in
# volume fraction is mathematically equivalent to a property that varies
# linearly with total filler Vf, so no separate function is needed -- see
# property_taxonomy.BlendRule.LINEAR_VF / ADDITIVE_DENSITY.
