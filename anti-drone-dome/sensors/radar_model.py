"""Physics-based radar detection: range equation plus Shnidman's P_d.

Replaces a hand-drawn piecewise detection curve that had no radar equation
behind it - no transmit power, no antenna gain, no wavelength, no noise figure,
no integration gain - and in which ``false_alarm_probability`` was a free
scenario parameter rather than a consequence of the detection threshold. P_d and
P_fa were therefore **decoupled, which is physically impossible**: you cannot
lower your false-alarm rate without also lowering your detection probability,
because both follow from where the threshold sits relative to the noise floor.

Here they are coupled properly. Given a link budget, a target RCS, a range, and
a false-alarm probability, single-pulse SNR follows from the range equation and
P_d follows from Shnidman's approximation to the Swerling detection integrals.

    SNR = (Pt * G^2 * lambda^2 * sigma) / ((4*pi)^3 * R^4 * k * Ts * B * L)

Everything is closed-form and licence-free, so it runs in CI and every
contributor can reproduce it. See ``docs-internal/PROGRAM_PLAN.md`` section 4.2
for why this is done in Python rather than with a MATLAB toolbox, and for the
trigger that would revisit that.

**Accuracy bounds.** Shnidman's approximation is quoted as within ~0.5 dB of the
exact Swerling integrals for 0.1 <= P_d <= 0.99, 1 <= N <= 100, and
1e-9 <= P_fa <= 1e-3. ``required_snr_db`` clamps its inputs to that envelope and
``SHNIDMAN_VALID`` documents it. Outside those bounds the result is an
extrapolation and should not be quoted.

Evidence status: ``design-placeholder`` for the budget values in
``DEFAULT_BUDGET``; the *model* is standard textbook radar, but the specific
transmit power, gain, and losses are representative until a real front end is
selected. See section 6.3.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

BOLTZMANN = 1.380649e-23
SPEED_OF_LIGHT = 299_792_458.0

# Envelope over which Shnidman's approximation is quoted as ~0.5 dB accurate.
SHNIDMAN_VALID = {
    "pd": (0.1, 0.99),
    "pfa": (1e-9, 1e-3),
    "n_pulses": (1, 100),
}

# Swerling target fluctuation models. The K parameter is the number of
# independent fluctuations integrated over the dwell.
#   0 - non-fluctuating (steady point target)
#   1 - slow fluctuation, many similar scatterers (scan-to-scan)
#   2 - fast fluctuation, many similar scatterers (pulse-to-pulse)
#   3 - slow fluctuation, one dominant scatterer
#   4 - fast fluctuation, one dominant scatterer
_SWERLING_K = {0: None, 1: 1, 2: None, 3: 2, 4: None}


def _swerling_k(case: int, n_pulses: int) -> float:
    """K parameter for Shnidman's C-factor."""
    if case == 0:
        return math.inf          # non-fluctuating: C -> 1
    if case == 1:
        return 1.0
    if case == 2:
        return float(n_pulses)
    if case == 3:
        return 2.0
    if case == 4:
        return 2.0 * n_pulses
    raise ValueError(f"unsupported Swerling case: {case!r}")


def required_snr_db(
    pd: float,
    pfa: float,
    n_pulses: int = 1,
    swerling: int = 1,
) -> float:
    """Single-pulse SNR (dB) needed for ``pd`` at ``pfa`` over ``n_pulses``.

    Shnidman's approximation. Inputs are clamped to ``SHNIDMAN_VALID``.
    """
    pd = float(np.clip(pd, *SHNIDMAN_VALID["pd"]))
    pfa = float(np.clip(pfa, *SHNIDMAN_VALID["pfa"]))
    n = int(np.clip(n_pulses, *SHNIDMAN_VALID["n_pulses"]))

    alpha = 0.0 if n < 40 else 0.25 / n
    eta = (
        math.sqrt(-0.8 * math.log(4.0 * pfa * (1.0 - pfa)))
        + math.copysign(1.0, pd - 0.5)
        * math.sqrt(-0.8 * math.log(4.0 * pd * (1.0 - pd)))
    )
    x_inf = eta * (eta + 2.0 * math.sqrt(n / 2.0 + (alpha - 0.25)))

    k = _swerling_k(swerling, n)
    if math.isinf(k):
        c_db = 0.0                                   # non-fluctuating
    else:
        c1 = (
            ((17.7006 * pd - 18.4496) * pd + 14.5339) * pd - 3.525
        ) / k
        c2 = (
            math.exp(27.31 * pd - 25.14)
            + (pd - 0.8) * (
                0.7 * math.log(1e-5 / pfa) + (2.0 * n - 20.0) / 80.0
            )
        ) / k
        c_db = c1 + c2

    c_linear = 10.0 ** (c_db / 10.0)
    return 10.0 * math.log10(c_linear * x_inf / n)


def probability_of_detection(
    snr_db,
    pfa: float = 1e-6,
    n_pulses: int = 1,
    swerling: int = 1,
) -> float | np.ndarray:
    """Invert ``required_snr_db`` for P_d at the given single-pulse SNR.

    Shnidman gives SNR as a function of P_d; it has no closed-form inverse, so
    this bisects on P_d. The mapping is monotonic in SNR, which makes bisection
    both safe and exact to tolerance.
    """
    scalar = np.isscalar(snr_db) or np.ndim(snr_db) == 0
    values = np.atleast_1d(np.asarray(snr_db, dtype=float))

    lo_pd, hi_pd = SHNIDMAN_VALID["pd"]
    snr_at_lo = required_snr_db(lo_pd, pfa, n_pulses, swerling)
    snr_at_hi = required_snr_db(hi_pd, pfa, n_pulses, swerling)

    out = np.empty_like(values)
    for index, snr in enumerate(values):
        if snr <= snr_at_lo:
            out[index] = lo_pd
            continue
        if snr >= snr_at_hi:
            out[index] = hi_pd
            continue
        low, high = lo_pd, hi_pd
        for _ in range(60):
            mid = 0.5 * (low + high)
            if required_snr_db(mid, pfa, n_pulses, swerling) < snr:
                low = mid
            else:
                high = mid
        out[index] = 0.5 * (low + high)

    return float(out[0]) if scalar else out


@dataclass(frozen=True)
class RadarBudget:
    """Link budget for a monostatic pulse-Doppler radar.

    Defaults describe a representative small X-band surveillance set. They are
    ``design-placeholder`` values, not a selected front end.
    """

    peak_power_w: float = 100.0
    antenna_gain_dbi: float = 30.0
    frequency_hz: float = 9.4e9          # X-band
    noise_figure_db: float = 4.0
    bandwidth_hz: float = 5.0e6
    system_loss_db: float = 6.0
    pulses_integrated: int = 20
    system_temperature_k: float = 290.0
    swerling: int = 1
    false_alarm_probability: float = 1e-6

    @property
    def wavelength_m(self) -> float:
        return SPEED_OF_LIGHT / self.frequency_hz

    def snr_db(self, range_m, rcs_m2):
        """Single-pulse SNR (dB) from the monostatic radar range equation.

        Accepts scalars or arrays; broadcasts over both arguments.
        """
        rng = np.asarray(range_m, dtype=float)
        rcs = np.asarray(rcs_m2, dtype=float)
        rng = np.maximum(rng, 1e-3)
        rcs = np.maximum(rcs, 1e-9)

        gain = 10.0 ** (self.antenna_gain_dbi / 10.0)
        losses = 10.0 ** (self.system_loss_db / 10.0)
        noise_figure = 10.0 ** (self.noise_figure_db / 10.0)

        numerator = (
            self.peak_power_w
            * gain * gain
            * self.wavelength_m ** 2
            * rcs
        )
        denominator = (
            (4.0 * math.pi) ** 3
            * rng ** 4
            * BOLTZMANN
            * self.system_temperature_k
            * noise_figure
            * self.bandwidth_hz
            * losses
        )
        return 10.0 * np.log10(numerator / denominator)

    def probability_of_detection(self, range_m, rcs_m2):
        """P_d at a given range and RCS, with P_fa coupled to the threshold."""
        return probability_of_detection(
            self.snr_db(range_m, rcs_m2),
            pfa=self.false_alarm_probability,
            n_pulses=self.pulses_integrated,
            swerling=self.swerling,
        )

    def detection_range_m(self, rcs_m2: float, pd: float = 0.5) -> float:
        """Range at which P_d falls to ``pd`` for a target of ``rcs_m2``.

        Closed form: SNR scales as R^-4, so the range at which SNR equals the
        Shnidman requirement follows directly from the reference SNR.
        """
        needed = required_snr_db(
            pd,
            self.false_alarm_probability,
            self.pulses_integrated,
            self.swerling,
        )
        reference_range = 1000.0
        snr_at_reference = float(self.snr_db(reference_range, rcs_m2))
        # SNR(R) = SNR(R0) - 40*log10(R/R0)  ->  solve SNR(R) = needed
        return reference_range * 10.0 ** ((snr_at_reference - needed) / 40.0)


DEFAULT_BUDGET = RadarBudget()


class RadarDetectionModel:
    """Detection model with a hard range cutoff, for use inside ``RadarNode``.

    ``max_range_m`` is the declared instrumented range of the set. Beyond it the
    model returns zero regardless of what the range equation says, because the
    radar is not looking there.
    """

    def __init__(self, budget: RadarBudget | None = None, max_range_m: float = 25.0):
        self.budget = budget or DEFAULT_BUDGET
        self.max_range_m = float(max_range_m)

    def p_detect(self, range_m: float, rcs_m2: float) -> float:
        if range_m > self.max_range_m:
            return 0.0
        return float(self.budget.probability_of_detection(range_m, rcs_m2))

    def describe(self) -> dict:
        """Provenance block for mission records and reports."""
        return {
            "schema": "aegis.radar-detection-model.v1",
            "model": "radar-range-equation + shnidman",
            "evidence_status": "design-placeholder",
            "peak_power_w": self.budget.peak_power_w,
            "antenna_gain_dbi": self.budget.antenna_gain_dbi,
            "frequency_hz": self.budget.frequency_hz,
            "wavelength_m": self.budget.wavelength_m,
            "noise_figure_db": self.budget.noise_figure_db,
            "bandwidth_hz": self.budget.bandwidth_hz,
            "system_loss_db": self.budget.system_loss_db,
            "pulses_integrated": self.budget.pulses_integrated,
            "swerling": self.budget.swerling,
            "false_alarm_probability": self.budget.false_alarm_probability,
            "max_range_m": self.max_range_m,
        }
