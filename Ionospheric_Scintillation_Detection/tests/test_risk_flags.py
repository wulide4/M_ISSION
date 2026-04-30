from isd.application.risk_flags import derive_result_risk_flags, derive_task_risk_flags


def test_derive_task_risk_flags_formal():
    flags = derive_task_risk_flags(
        derived_chain_level="FORMAL",
        derived_sampling_mode="STANDARD_30S",
        metrics=["ROTI"],
        systems=["GPS"],
        nav_fallback_enabled=False,
    )
    assert flags == ["FORMAL_PIPELINE"]


def test_derive_task_risk_flags_experimental_non_gps_sigma():
    flags = derive_task_risk_flags(
        derived_chain_level="EXPERIMENTAL",
        derived_sampling_mode="EXPERIMENTAL_1S_RESAMPLED",
        metrics=["SIGMA_PHI_F"],
        systems=["GPS", "BDS"],
        nav_fallback_enabled=False,
    )
    assert "NON_FORMAL_CHAIN_LEVEL" in flags
    assert "EXPERIMENTAL_CHAIN_LEVEL" in flags
    assert "NON_STANDARD_SAMPLING_MODE" in flags
    assert "EXPERIMENTAL_1S_RESAMPLED" in flags
    assert "NON_GPS_SIGMAPHI_EXPERIMENT" in flags


def test_derive_result_risk_flags_degraded():
    flags = derive_result_risk_flags(
        {
            "metric": "SIGMA_PHI_F",
            "system": "GPS",
            "chain_level": "DEGRADED",
            "sampling_mode": "STANDARD_30S",
        }
    )
    assert "NON_FORMAL_CHAIN_LEVEL" in flags
    assert "DEGRADED_CHAIN_LEVEL" in flags

