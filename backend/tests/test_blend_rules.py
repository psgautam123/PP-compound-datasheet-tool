"""Unit tests for the pure blend-formula functions in engine.blend_rules.

These are hand-computed/round-trip checks, independent of any datasheet
data, isolating correctness of the formulas themselves (Workflow2.txt
§8-19) from the grade-screening/optimizer orchestration in predictor.py.
"""
from __future__ import annotations

import math

import pytest

from engine import blend_rules as br


# ---------------------------------------------------------------------------
# Composition conversion
# ---------------------------------------------------------------------------


def test_wt_pct_to_volume_fraction_equal_densities():
    # equal densities => volume fraction equals weight fraction
    assert br.wt_pct_to_volume_fraction(30, 1000, 1000) == pytest.approx(0.30)


def test_wt_pct_volume_fraction_round_trip():
    vf = br.wt_pct_to_volume_fraction(40, 1100, 905)
    wt = br.volume_fraction_to_wt_pct(vf, 1100, 905)
    assert wt == pytest.approx(40, abs=1e-9)


# ---------------------------------------------------------------------------
# Log-additive MFR
# ---------------------------------------------------------------------------


def test_log_additive_blend_endpoints():
    assert br.log_additive_blend(15, 5, phi_a=1.0) == pytest.approx(15)
    assert br.log_additive_blend(15, 5, phi_a=0.0) == pytest.approx(5)


def test_log_additive_blend_matches_hand_computation():
    # ln(8.660...) = 0.5*ln(15) + 0.5*ln(5)
    expected = math.exp(0.5 * math.log(15) + 0.5 * math.log(5))
    assert br.log_additive_blend(15, 5, phi_a=0.5) == pytest.approx(expected)


def test_solve_phi_a_log_additive_round_trip():
    blended = br.log_additive_blend(20, 4, phi_a=0.35)
    phi_recovered = br.solve_phi_a_log_additive(blended, 20, 4)
    assert phi_recovered == pytest.approx(0.35)


def test_krieger_dougherty_relative_viscosity_increases_with_loading():
    low = br.krieger_dougherty_relative_viscosity(0.10)
    high = br.krieger_dougherty_relative_viscosity(0.30)
    assert high > low > 1.0


def test_krieger_dougherty_relative_viscosity_rejects_at_or_above_phi_max():
    with pytest.raises(ValueError):
        br.krieger_dougherty_relative_viscosity(0.62, phi_max=0.62)


def test_krieger_dougherty_mfr_adjustment_lower_at_higher_filler():
    # more filler -> higher viscosity -> lower MFR, at fixed test conditions
    adjusted = br.krieger_dougherty_mfr_adjustment(
        mfr_baseline=15, phi_filler_baseline=0.05, phi_filler_target=0.15
    )
    assert adjusted < 15


# ---------------------------------------------------------------------------
# Modulus: linear ROM + Halpin-Tsai
# ---------------------------------------------------------------------------


def test_linear_rule_of_mixtures_endpoints():
    assert br.linear_rule_of_mixtures(4700, 980, phi_a=1.0) == pytest.approx(4700)
    assert br.linear_rule_of_mixtures(4700, 980, phi_a=0.0) == pytest.approx(980)


def test_solve_phi_a_linear_round_trip():
    blended = br.linear_rule_of_mixtures(4700, 980, phi_a=0.62)
    assert br.solve_phi_a_linear(blended, 4700, 980) == pytest.approx(0.62)


def test_halpin_tsai_modulus_reduces_to_matrix_at_zero_vf():
    e = br.halpin_tsai_modulus(e_matrix=1300, e_filler=br.E_GLASS_MODULUS_MPA, vf_filler=0.0, xi=2.0)
    assert e == pytest.approx(1300)


def test_halpin_tsai_modulus_increases_with_vf():
    e_low = br.halpin_tsai_modulus(1300, br.E_GLASS_MODULUS_MPA, 0.05, xi=2.0)
    e_high = br.halpin_tsai_modulus(1300, br.E_GLASS_MODULUS_MPA, 0.15, xi=2.0)
    assert e_high > e_low > 1300


def test_calibrate_halpin_tsai_xi_reproduces_known_point():
    e_matrix, e_filler, vf_known = 1300.0, br.E_GLASS_MODULUS_MPA, 0.08
    true_xi = 3.2
    e_known = br.halpin_tsai_modulus(e_matrix, e_filler, vf_known, true_xi)
    fitted_xi = br.calibrate_halpin_tsai_xi(e_matrix, e_filler, vf_known, e_known)
    assert fitted_xi == pytest.approx(true_xi, rel=1e-6)


# ---------------------------------------------------------------------------
# Exponential decay (impact / strain at break)
# ---------------------------------------------------------------------------


def test_exponential_decay_at_zero_vf_returns_unfilled_value():
    assert br.exponential_decay(value_unfilled=13, k=5.0, vf_filler=0.0) == pytest.approx(13)


def test_exponential_decay_with_tail_approaches_tail():
    v = br.exponential_decay(value_unfilled=13, k=5.0, vf_filler=10.0, tail=2.0)
    assert v == pytest.approx(2.0, abs=1e-3)


def test_fit_decay_constant_round_trip():
    k_true = 4.2
    known = br.exponential_decay(13.0, k_true, vf_filler=0.12)
    k_fitted = br.fit_decay_constant(value_unfilled=13.0, value_known=known, vf_known=0.12)
    assert k_fitted == pytest.approx(k_true, rel=1e-6)


def test_fit_decay_constant_rejects_value_outside_range():
    with pytest.raises(ValueError):
        # value_known above value_unfilled is non-physical for a decay curve
        br.fit_decay_constant(value_unfilled=6.0, value_known=13.0, vf_known=0.1)


# ---------------------------------------------------------------------------
# HDT power law
# ---------------------------------------------------------------------------


def test_hdt_power_law_identity_at_reference_modulus():
    assert br.hdt_power_law(hdt_ref=140, e_ref=4700, e_target=4700, n=0.4) == pytest.approx(140)


def test_calibrate_hdt_exponent_round_trip():
    n_true = 0.37
    hdt2 = br.hdt_power_law(hdt_ref=140, e_ref=4700, e_target=7600, n=n_true)
    n_fitted = br.calibrate_hdt_exponent(4700, 140, 7600, hdt2)
    assert n_fitted == pytest.approx(n_true, rel=1e-6)
