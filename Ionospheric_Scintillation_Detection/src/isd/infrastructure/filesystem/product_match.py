from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable

from isd.domain.enums import ChainLevel, FileKind, MetricKey
from isd.domain.models import ProjectFile


@dataclass(frozen=True)
class _DailyKinds:
    obs: bool
    kinds: set[FileKind]


class ProductMatcher:
    def resolve(self, files: list[ProjectFile], metrics: Iterable[MetricKey | str]) -> dict[str, dict[str, Any]]:
        metric_set = self._normalize_metrics(metrics)
        by_date = self._build_daily_kinds(files)
        out: dict[str, dict[str, Any]] = {}

        for date in sorted(by_date.keys()):
            daily = by_date[date]
            missing: list[str] = []
            for required in (FileKind.SP3, FileKind.CLK, FileKind.ATX):
                if required not in daily.kinds:
                    missing.append(required.value)

            sigmaphi_required = MetricKey.SIGMA_PHI_F in metric_set
            # Per M_ISSION paper: sigma_phi_f can work in simplified mode (OBS only)
            # without SP3/CLK/ATX. Full mode requires all precise products.
            has_all_precise = not missing
            if sigmaphi_required and not has_all_precise:
                chain_level = ChainLevel.DEGRADED.value
            else:
                chain_level = ChainLevel.FORMAL.value
            out[date] = {
                'SP3': 'matched' if FileKind.SP3 in daily.kinds else 'missing',
                'CLK': 'matched' if FileKind.CLK in daily.kinds else 'missing',
                'ATX': 'matched' if FileKind.ATX in daily.kinds else 'missing',
                'NAV': 'available_degraded_only' if FileKind.NAV in daily.kinds else 'missing',
                'obsPresent': daily.obs,
                'missingRequired': missing,
                'chainLevel': chain_level,
                'sigmaPhiFullMode': has_all_precise,
                'status': 'ready' if daily.obs else 'partial',
            }
        return out

    def assign_match_flags(self, files: list[ProjectFile]) -> None:
        by_date = self._build_daily_kinds(files)
        any_obs = any(day.obs for day in by_date.values())

        for file in files:
            if file.kind == FileKind.SPACE_WEATHER:
                file.matched = True
                continue

            if file.kind == FileKind.ATX and not file.file_date:
                file.matched = any_obs
                continue

            if not file.file_date:
                file.matched = False
                continue

            daily = by_date.get(file.file_date)
            if not daily:
                file.matched = False
                continue

            if file.kind == FileKind.OBS:
                file.matched = all(k in daily.kinds for k in (FileKind.SP3, FileKind.CLK, FileKind.ATX))
            else:
                file.matched = daily.obs

    def _normalize_metrics(self, metrics: Iterable[MetricKey | str]) -> set[MetricKey]:
        out: set[MetricKey] = set()
        for metric in metrics:
            try:
                out.add(metric if isinstance(metric, MetricKey) else MetricKey(str(metric)))
            except ValueError:
                continue
        return out

    def _build_daily_kinds(self, files: list[ProjectFile]) -> dict[str, _DailyKinds]:
        rows_by_date: dict[str, list[ProjectFile]] = defaultdict(list)
        global_kinds: set[FileKind] = set()
        for file in files:
            if file.file_date:
                rows_by_date[file.file_date].append(file)
            elif file.kind in {FileKind.ATX}:
                global_kinds.add(file.kind)

        out: dict[str, _DailyKinds] = {}
        for date, rows in rows_by_date.items():
            kinds = {row.kind for row in rows} | global_kinds
            obs_present = any(row.kind == FileKind.OBS for row in rows)
            out[date] = _DailyKinds(obs=obs_present, kinds=kinds)
        return out