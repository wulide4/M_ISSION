"""Apply PPP model correction to carrier phase per model_cor.m.

corrected_phase_m = phase_cycles * wavelength - correction_m
"""
from __future__ import annotations

import numpy as np


def apply_model_correction(
    phase_cycles: np.ndarray,
    correction_m: np.ndarray,
    wavelength: float,
) -> np.ndarray:
    """Apply PPP model correction to carrier phase.

    Args:
        phase_cycles: (T, n_sat) carrier phase in cycles from RINEX
        correction_m: (T, n_sat) total model correction in metres from nmodel
        wavelength: carrier wavelength in metres

    Returns:
        (T, n_sat) corrected phase in metres.
    """
    phase_m = phase_cycles * wavelength
    # Subtract model correction
    corrected = phase_m - correction_m
    # Where correction is NaN (no satellite state available), output NaN
    corrected[np.isnan(correction_m)] = np.nan
    return corrected
