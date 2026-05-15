from __future__ import annotations

from collections.abc import Iterable


def derive_risk_flags(
    *,
    chain_level: str | None,
    sampling_mode: str | None,
    metrics: Iterable[str] | None = None,
    systems: Iterable[str] | None = None,
    nav_fallback_enabled: bool = False,
) -> list[str]:
    metric_set = {str(x).upper() for x in (metrics or []) if str(x).strip()}
    system_set = {str(x).upper() for x in (systems or []) if str(x).strip()}
    flags: list[str] = []

    chain = (chain_level or "").upper()
    sampling = (sampling_mode or "").upper()

    if chain and chain != "FORMAL":
        flags.append("NON_FORMAL_CHAIN_LEVEL")
        if chain == "EXPERIMENTAL":
            flags.append("EXPERIMENTAL_CHAIN_LEVEL")
        elif chain == "DEGRADED":
            flags.append("DEGRADED_CHAIN_LEVEL")

    if sampling and sampling != "STANDARD_30S":
        flags.append("NON_STANDARD_SAMPLING_MODE")
        if sampling == "EXPERIMENTAL_1S_RESAMPLED":
            flags.append("EXPERIMENTAL_1S_RESAMPLED")

    if "SIGMA_PHI_F" in metric_set and any(sys != "GPS" for sys in system_set):
        flags.append("NON_GPS_SIGMAPHI_EXPERIMENT")

    if nav_fallback_enabled:
        flags.append("NAV_FALLBACK_ENABLED")

    if not flags:
        flags.append("FORMAL_PIPELINE")
    return list(dict.fromkeys(flags))


def derive_task_risk_flags(
    *,
    derived_chain_level: str | None,
    derived_sampling_mode: str | None,
    metrics: Iterable[str] | None,
    systems: Iterable[str] | None,
    nav_fallback_enabled: bool,
) -> list[str]:
    return derive_risk_flags(
        chain_level=derived_chain_level,
        sampling_mode=derived_sampling_mode,
        metrics=metrics,
        systems=systems,
        nav_fallback_enabled=nav_fallback_enabled,
    )


def derive_result_risk_flags(result_row: dict) -> list[str]:
    metric = result_row.get("metric")
    system = result_row.get("system")
    return derive_risk_flags(
        chain_level=result_row.get("chain_level"),
        sampling_mode=result_row.get("sampling_mode"),
        metrics=[metric] if metric else None,
        systems=[system] if system else None,
        nav_fallback_enabled=False,
    )


def risk_flags_to_text(flags: list[str]) -> str:
    if not flags:
        return "FORMAL_PIPELINE"
    return ", ".join(flags)

