"""Validation for the physics-based radar detection model.

The textbook-reference tests are the point of this file: they are what let us
claim the detection model is real physics rather than a fitted curve, without
buying a MATLAB toolbox to say the same thing. See
``docs-internal/PROGRAM_PLAN.md`` section 4.2.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sensors.radar_model import (  # noqa: E402
    BOLTZMANN,
    SPEED_OF_LIGHT,
    RadarBudget,
    RadarDetectionModel,
    probability_of_detection,
    required_snr_db,
)


# --------------------------------------------------------------------------
# Shnidman against published reference values
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "pd, pfa, n, swerling, expected_db, tol_db",
    [
        # Non-fluctuating single pulse: the canonical worked examples.
        (0.90, 1e-6, 1, 0, 13.2, 0.5),
        (0.50, 1e-6, 1, 0, 11.2, 0.5),
        # Swerling 1 carries a large fluctuation loss at high Pd.
        (0.90, 1e-6, 1, 1, 21.1, 0.6),
    ],
)
def test_required_snr_matches_published_values(pd, pfa, n, swerling, expected_db, tol_db):
    assert required_snr_db(pd, pfa, n, swerling) == pytest.approx(
        expected_db, abs=tol_db
    )


def test_required_snr_is_monotonic_in_pd():
    values = [required_snr_db(pd, 1e-6, 20, 1) for pd in np.linspace(0.15, 0.95, 12)]
    assert all(b > a for a, b in zip(values, values[1:]))


def test_stricter_false_alarm_rate_costs_snr():
    """P_d and P_fa are coupled through the threshold - the whole point.

    The curve this replaced let false_alarm_probability be set independently of
    the detection curve, which is physically impossible.
    """
    assert required_snr_db(0.9, 1e-9, 20, 1) > required_snr_db(0.9, 1e-3, 20, 1)


def test_integration_gain_reduces_per_pulse_snr():
    assert required_snr_db(0.9, 1e-6, 50, 1) < required_snr_db(0.9, 1e-6, 1, 1)


def test_swerling1_costs_more_than_nonfluctuating():
    """A fluctuating target is harder to detect at high Pd."""
    assert required_snr_db(0.9, 1e-6, 10, 1) > required_snr_db(0.9, 1e-6, 10, 0)


def test_unsupported_swerling_case_rejected():
    with pytest.raises(ValueError):
        required_snr_db(0.9, 1e-6, 10, 7)


# --------------------------------------------------------------------------
# Inversion
# --------------------------------------------------------------------------

def test_probability_of_detection_inverts_required_snr():
    for pd in (0.2, 0.5, 0.75, 0.9, 0.95):
        snr = required_snr_db(pd, 1e-6, 20, 1)
        assert probability_of_detection(snr, 1e-6, 20, 1) == pytest.approx(pd, abs=1e-3)


def test_probability_of_detection_is_monotonic_and_bounded():
    snrs = np.linspace(-20.0, 40.0, 60)
    pds = probability_of_detection(snrs, 1e-6, 20, 1)
    assert np.all(np.diff(pds) >= -1e-9)
    assert np.all(pds >= 0.1) and np.all(pds <= 0.99)


def test_probability_of_detection_accepts_arrays_and_scalars():
    scalar = probability_of_detection(10.0, 1e-6, 20, 1)
    assert isinstance(scalar, float)
    array = probability_of_detection(np.array([0.0, 10.0, 20.0]), 1e-6, 20, 1)
    assert array.shape == (3,)


# --------------------------------------------------------------------------
# Range equation
# --------------------------------------------------------------------------

def test_snr_follows_inverse_fourth_power_law():
    """Doubling range must cost exactly 12 dB - the R^-4 signature."""
    budget = RadarBudget()
    near = float(budget.snr_db(500.0, 0.05))
    far = float(budget.snr_db(1000.0, 0.05))
    assert near - far == pytest.approx(12.0411, abs=1e-3)


def test_snr_is_linear_in_rcs():
    """Ten times the RCS is exactly 10 dB more signal."""
    budget = RadarBudget()
    assert (
        float(budget.snr_db(1000.0, 0.5)) - float(budget.snr_db(1000.0, 0.05))
    ) == pytest.approx(10.0, abs=1e-6)


def test_snr_matches_hand_calculation():
    """Independent evaluation of the range equation, term by term."""
    budget = RadarBudget()
    rng, rcs = 1200.0, 0.05

    wavelength = SPEED_OF_LIGHT / budget.frequency_hz
    gain = 10.0 ** (budget.antenna_gain_dbi / 10.0)
    numerator = budget.peak_power_w * gain**2 * wavelength**2 * rcs
    denominator = (
        (4.0 * np.pi) ** 3
        * rng**4
        * BOLTZMANN
        * budget.system_temperature_k
        * 10.0 ** (budget.noise_figure_db / 10.0)
        * budget.bandwidth_hz
        * 10.0 ** (budget.system_loss_db / 10.0)
    )
    expected = 10.0 * np.log10(numerator / denominator)
    assert float(budget.snr_db(rng, rcs)) == pytest.approx(expected, abs=1e-9)


def test_wavelength_matches_frequency():
    budget = RadarBudget(frequency_hz=9.4e9)
    assert budget.wavelength_m == pytest.approx(0.0319, abs=1e-4)


def test_detection_range_is_consistent_with_pd_curve():
    """R50 must be the range at which P_d actually equals 0.5."""
    budget = RadarBudget()
    r50 = budget.detection_range_m(0.05, pd=0.5)
    assert float(budget.probability_of_detection(r50, 0.05)) == pytest.approx(
        0.5, abs=0.01
    )


def test_larger_rcs_detected_further():
    budget = RadarBudget()
    assert budget.detection_range_m(0.5, 0.5) > budget.detection_range_m(0.05, 0.5)
    # R ~ sigma^(1/4): a 10x RCS buys a 10^0.25 = 1.78x range increase.
    ratio = budget.detection_range_m(0.5, 0.5) / budget.detection_range_m(0.05, 0.5)
    assert ratio == pytest.approx(10.0 ** 0.25, rel=1e-3)


def test_detection_degrades_across_the_instrumented_range():
    """A useful model must actually fall off inside the radar's own range.

    A detection curve that is ~1.0 everywhere is not modelling anything.
    """
    budget = RadarBudget()
    near = float(budget.probability_of_detection(200.0, 0.05))
    mid = float(budget.probability_of_detection(1000.0, 0.05))
    far = float(budget.probability_of_detection(1500.0, 0.05))
    assert near > 0.95
    assert 0.7 < mid < near
    assert far < mid


# --------------------------------------------------------------------------
# RadarDetectionModel
# --------------------------------------------------------------------------

def test_hard_cutoff_beyond_instrumented_range():
    model = RadarDetectionModel(max_range_m=1500.0)
    assert model.p_detect(1499.0, 0.05) > 0.0
    assert model.p_detect(1501.0, 0.05) == 0.0


def test_describe_reports_provenance():
    model = RadarDetectionModel(max_range_m=1500.0)
    described = model.describe()
    assert described["schema"] == "aegis.radar-detection-model.v1"
    assert described["evidence_status"] == "design-placeholder"
    # Every term of the range equation must be recoverable from the record.
    assert {
        "peak_power_w", "antenna_gain_dbi", "frequency_hz", "noise_figure_db",
        "bandwidth_hz", "system_loss_db", "pulses_integrated", "swerling",
        "false_alarm_probability",
    } <= set(described)


def test_radar_node_uses_the_physics_model_by_default():
    from sensors.radar import RadarNode

    node = RadarNode(max_range=1500.0)
    assert isinstance(node._detection_model, RadarDetectionModel)
    assert node._detection_model.max_range_m == 1500.0


def test_radar_node_accepts_an_injected_model():
    from sensors.radar import RadarNode

    class AlwaysDetects:
        max_range_m = 1e9

        def p_detect(self, range_m, rcs_m2):
            return 1.0

    node = RadarNode(max_range=1500.0, detection_model=AlwaysDetects())
    assert node._detection_model.p_detect(999.0, 0.01) == 1.0
