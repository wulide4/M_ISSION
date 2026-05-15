from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from isd.application.risk_flags import derive_result_risk_flags
from isd.domain.enums import MetricKey
from isd.infrastructure.repositories.result_repository import ResultRepository
from isd.infrastructure.repositories.template_repository import TemplateRepository

# ---------- Chinese labels for enums ----------

METRIC_NAMES = {
    "ROTI": "ROTI (电离层变化率总电子含量)",
    "AATR": "AATR (绝对电离层变化率)",
    "IAATR": "IAATR (瞬时绝对电离层变化率)",
    "DIXSG": "DIXSG (空间梯度扰动指数)",
    "SIGMA_PHI_F": "σφf (振幅闪烁指数)",
}

METRIC_UNITS = {
    "ROTI": "TECU/min",
    "AATR": "TECU/min",
    "IAATR": "TECU/min",
    "DIXSG": "无量纲",
    "SIGMA_PHI_F": "rad",
}

METRIC_THRESHOLDS = {
    "ROTI": (0.5, "Pi et al. (1997)"),
    "AATR": (0.2, "Sanz et al. (2014)"),
    "IAATR": (0.2, "Sanz et al. (2014)"),
    "DIXSG": (0.5, "Jakowski et al. (2012)"),
    "SIGMA_PHI_F": (0.3, "Ahmed et al. (2015)"),
}

CHAIN_NAMES = {
    "FORMAL": "正式链",
    "DEGRADED": "降级链",
    "EXPERIMENTAL": "实验链",
    "SYNTHETIC": "合成数据",
}

SAMPLING_NAMES = {
    "STANDARD_30S": "30秒标准采样",
    "HIGH_RATE_1S": "1秒高采样",
    "EXPERIMENTAL_1S_RESAMPLED": "1秒重采样(实验)",
}

RISK_NAMES = {
    "FORMAL_PIPELINE": "正式处理流程",
    "NON_FORMAL_CHAIN_LEVEL": "非正式处理链",
    "EXPERIMENTAL_CHAIN_LEVEL": "实验处理链",
    "DEGRADED_CHAIN_LEVEL": "降级处理链",
    "NON_STANDARD_SAMPLING_MODE": "非标准采样",
    "EXPERIMENTAL_1S_RESAMPLED": "实验性1秒重采样",
    "NON_GPS_SIGMAPHI_EXPERIMENT": "非GPS σφf (实验)",
    "NAV_FALLBACK_ENABLED": "导航星历回退已启用",
    "NO_RESULT_SELECTED": "未选择结果",
}

SYSTEM_NAMES = {
    "GPS": "GPS",
    "GLO": "GLONASS",
    "GAL": "Galileo",
    "BDS": "BeiDou",
}


@dataclass
class ReportService:
    result_repo: ResultRepository
    template_repo: TemplateRepository

    def list_templates(self) -> list[dict]:
        rows = self.template_repo.list_all()
        if not rows:
            return [self._default_template()]
        return [row.model_dump(mode="json") for row in rows]

    def preview_report(
        self,
        template_id: str,
        result_ids: list[str],
        options: dict,
        project_id: str | None = None,
    ) -> dict:
        template = self._resolve_template(template_id)
        results = self._resolve_results(project_id, result_ids, options)
        summary = self._build_summary(results)

        preview = {
            "templateId": template["id"],
            "templateName": template["name"],
            "resultIds": [row["id"] for row in results],
            "projectId": project_id,
            "options": options,
            "summary": summary,
            "taskInfo": self._build_task_info(results),
            "resultCards": self._build_result_cards(results),
            "note": "Preview based on repository results.",
        }
        if options.get("includeParameterSnapshot", True):
            preview["parameterSnapshot"] = self._build_parameter_snapshot(results)
        return preview

    def export_report(
        self,
        template_id: str,
        result_ids: list[str],
        options: dict,
        output_path: str,
        project_id: str | None = None,
    ) -> dict:
        preview = self.preview_report(template_id, result_ids, options, project_id=project_id)
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        ext = out.suffix.lower()
        if ext == ".pdf":
            try:
                self._export_html(preview, out)
                return {"outputPath": str(out), "status": "SUCCESS", "format": "HTML(saved as .pdf)", "fallbackUsed": False}
            except Exception as exc:
                fallback = out.with_suffix(".html")
                self._export_html(preview, fallback)
                return {
                    "outputPath": str(fallback),
                    "status": "SUCCESS",
                    "format": "HTML",
                    "fallbackUsed": True,
                    "warning": f"PDF export failed, fallback to HTML: {exc}",
                }

        self._export_html(preview, out)
        return {"outputPath": str(out), "status": "SUCCESS", "format": "HTML", "fallbackUsed": False}

    def _resolve_template(self, template_id: str) -> dict:
        row = self.template_repo.get(template_id)
        if row:
            return row.model_dump(mode="json")
        return self._default_template()

    def _default_template(self) -> dict:
        return {
            "id": "default_template",
            "name": "Default Report Template",
            "description": "Built-in fallback template",
            "scope": "REPORT",
            "is_default": True,
            "payload": {"sections": ["overview", "metrics", "risk_flags", "result_cards"]},
            "created_at": "",
            "updated_at": "",
        }

    def _resolve_results(self, project_id: str | None, result_ids: list[str], options: dict) -> list[dict]:
        rows: list[dict] = []
        if project_id:
            rows = [row.model_dump(mode="json") for row in self.result_repo.list_results(project_id)]

        if result_ids:
            wanted = set(result_ids)
            rows = [row for row in rows if row["id"] in wanted]

        include_non_gps_sigma = bool(options.get("includeNonGpsSigmaPhiF", False))
        if not include_non_gps_sigma:
            rows = [
                row for row in rows
                if not (
                    row.get("metric") == MetricKey.SIGMA_PHI_F.value
                    and row.get("system")
                    and row.get("system") != "GPS"
                )
            ]

        return rows[:100]

    def _build_summary(self, rows: list[dict]) -> dict:
        if not rows:
            return {
                "resultCount": 0,
                "metricsBreakdown": {},
                "stations": [],
                "chainLevels": [],
                "samplingModes": [],
                "providerSources": [],
                "riskFlags": ["NO_RESULT_SELECTED"],
            }

        metrics = Counter(row.get("metric", "UNKNOWN") for row in rows)
        stations = sorted({row.get("station_id") for row in rows if row.get("station_id")})
        chain_levels = sorted({row.get("chain_level") for row in rows if row.get("chain_level")})
        sampling_modes = sorted({row.get("sampling_mode") for row in rows if row.get("sampling_mode")})
        provider_sources = sorted(
            {self._extract_provider_summary(row.get("parameter_source_summary")) for row in rows if row.get("parameter_source_summary")}
        )

        risk_flags: list[str] = []
        for row in rows:
            for flag in derive_result_risk_flags(row):
                if flag not in risk_flags:
                    risk_flags.append(flag)
        if len(risk_flags) > 1 and "FORMAL_PIPELINE" in risk_flags:
            risk_flags.remove("FORMAL_PIPELINE")

        return {
            "resultCount": len(rows),
            "metricsBreakdown": dict(metrics),
            "stations": stations,
            "chainLevels": chain_levels,
            "samplingModes": sampling_modes,
            "providerSources": provider_sources,
            "riskFlags": risk_flags,
        }

    def _build_task_info(self, rows: list[dict]) -> dict:
        task_ids = sorted({row.get("task_id") for row in rows if row.get("task_id")})
        project_ids = sorted({row.get("project_id") for row in rows if row.get("project_id")})
        return {"projectIds": project_ids, "taskIds": task_ids, "taskCount": len(task_ids)}

    def _build_parameter_snapshot(self, rows: list[dict]) -> dict:
        chain_levels = sorted({row.get("chain_level") for row in rows if row.get("chain_level")})
        sampling_modes = sorted({row.get("sampling_mode") for row in rows if row.get("sampling_mode")})
        threshold_sources = sorted({row.get("threshold_source") for row in rows if row.get("threshold_source")})
        parameter_sources = sorted({row.get("parameter_source_summary") for row in rows if row.get("parameter_source_summary")})
        coordinate_sources = sorted({row.get("coordinate_source") for row in rows if row.get("coordinate_source")})
        provider_sources = sorted(
            {self._extract_provider_summary(row.get("parameter_source_summary")) for row in rows if row.get("parameter_source_summary")}
        )
        return {
            "chainLevels": chain_levels,
            "samplingModes": sampling_modes,
            "thresholdSources": threshold_sources,
            "parameterSources": parameter_sources,
            "coordinateSources": coordinate_sources,
            "providerSources": provider_sources,
        }

    def _build_result_cards(self, rows: list[dict]) -> list[dict]:
        cards: list[dict] = []
        for row in rows:
            stats = row.get("stats") or {}
            cards.append({
                "id": row.get("id"),
                "metric": row.get("metric"),
                "station": row.get("station_id"),
                "system": row.get("system"),
                "chainLevel": row.get("chain_level"),
                "samplingMode": row.get("sampling_mode"),
                "coordinateSource": row.get("coordinate_source"),
                "providerSummary": self._extract_provider_summary(row.get("parameter_source_summary")),
                "riskFlags": derive_result_risk_flags(row),
                "stats": {
                    "min": stats.get("min"),
                    "max": stats.get("max"),
                    "mean": stats.get("mean"),
                    "p95": stats.get("p95"),
                    "eventCount": stats.get("event_count"),
                },
            })
        return cards

    def _extract_provider_summary(self, parameter_source_summary: str | None) -> str:
        text = str(parameter_source_summary or "").strip()
        if not text:
            return "-"
        marker = "providers="
        idx = text.find(marker)
        if idx < 0:
            return "-"
        return text[idx + len(marker):].strip()

    # ------------------------------------------------------------------
    # HTML report generation
    # ------------------------------------------------------------------

    def _export_html(self, preview: dict, out: Path) -> None:
        html = self._build_html(preview)
        out.write_text(html, encoding="utf-8")

    def _build_html(self, preview: dict) -> str:
        summary = preview["summary"]
        options = preview.get("options", {})
        cards = preview.get("resultCards", [])
        title = options.get("title") or "电离层闪烁指数监测报告"
        now_str = datetime.now().strftime("%Y年%m月%d日 %H:%M")

        # --- Overview section ---
        overview_rows = []
        overview_rows.append(("结果总数", f"{summary['resultCount']} 条"))
        overview_rows.append(("涉及站点", "、".join(summary["stations"]) if summary["stations"] else "无"))
        overview_rows.append(("处理链级别", "、".join(CHAIN_NAMES.get(c, c) for c in summary["chainLevels"]) if summary["chainLevels"] else "-"))
        overview_rows.append(("采样模式", "、".join(SAMPLING_NAMES.get(s, s) for s in summary["samplingModes"]) if summary["samplingModes"] else "-"))

        overview_html = ""
        for label, value in overview_rows:
            overview_html += f'<tr><td class="label">{label}</td><td>{value}</td></tr>\n'

        # --- Metrics breakdown section ---
        metrics_html = ""
        for metric_key, count in sorted(summary["metricsBreakdown"].items()):
            name = METRIC_NAMES.get(metric_key, metric_key)
            unit = METRIC_UNITS.get(metric_key, "-")
            threshold_info = METRIC_THRESHOLDS.get(metric_key)
            threshold_text = f'{threshold_info[0]} {unit} ({threshold_info[1]})' if threshold_info else "-"
            metrics_html += f'<tr><td>{name}</td><td>{count}</td><td>{unit}</td><td>{threshold_text}</td></tr>\n'

        # --- Per-station detailed cards ---
        stations_map: dict[str, list[dict]] = {}
        for card in cards:
            sid = card.get("station") or "未知"
            stations_map.setdefault(sid, []).append(card)

        detail_html = ""
        for sid in sorted(stations_map.keys()):
            station_cards = stations_map[sid]
            detail_html += f'<h3>测站: {sid}</h3>\n<table>\n'
            detail_html += '<tr><th>指标</th><th>卫星系统</th><th>最小值</th><th>最大值</th><th>均值</th><th>P95</th><th>阈值</th><th>事件数</th><th>评估</th></tr>\n'
            for card in station_cards:
                metric = card.get("metric", "-")
                metric_name = METRIC_NAMES.get(metric, metric)
                unit = METRIC_UNITS.get(metric, "")
                sys_name = SYSTEM_NAMES.get(card.get("system"), card.get("system") or "-")
                stats = card.get("stats", {})

                min_v = stats.get("min")
                max_v = stats.get("max")
                mean_v = stats.get("mean")
                p95_v = stats.get("p95")
                ev = stats.get("eventCount")
                min_text = f"{min_v:.4f}" if min_v is not None else "-"
                max_text = f"{max_v:.4f}" if max_v is not None else "-"
                mean_text = f"{mean_v:.4f}" if mean_v is not None else "-"
                p95_text = f"{p95_v:.4f}" if p95_v is not None else "-"
                ev_text = str(ev) if ev is not None else "-"

                threshold_info = METRIC_THRESHOLDS.get(metric)
                threshold_text = f'{threshold_info[0]} {unit}' if threshold_info else "-"
                threshold_val = threshold_info[0] if threshold_info else None

                # Determine assessment — use mean as primary criterion
                assessment = "-"
                assessment_class = ""
                if mean_v is not None and threshold_val is not None:
                    if mean_v > threshold_val:
                        assessment = "超出阈值"
                        assessment_class = ' class="warn"'
                    elif max_v is not None and max_v > threshold_val:
                        assessment = "部分超出"
                        assessment_class = ' class="warn"'
                    else:
                        assessment = "正常"
                        assessment_class = ' class="ok"'

                detail_html += (
                    f'<tr><td>{metric_name}</td><td>{sys_name}</td>'
                    f'<td>{min_text}</td><td>{max_text}</td><td>{mean_text}</td>'
                    f'<td>{p95_text}</td><td>{threshold_text}</td><td>{ev_text}</td>'
                    f'<td{assessment_class}>{assessment}</td></tr>\n'
                )
            detail_html += '</table>\n'

        # --- Risk flags section ---
        risk_flags = summary.get("riskFlags", [])
        risk_html = ""
        for flag in risk_flags:
            name = RISK_NAMES.get(flag, flag)
            is_formal = flag == "FORMAL_PIPELINE"
            cls = ' class="ok"' if is_formal else ' class="warn"'
            risk_html += f'<li{cls}>{name}</li>\n'

        # --- Parameter snapshot section ---
        param_html = ""
        params = preview.get("parameterSnapshot")
        if params and options.get("includeParameterSnapshot"):
            param_rows = []
            for key, label in [
                ("chainLevels", "处理链级别"),
                ("samplingModes", "采样模式"),
                ("thresholdSources", "阈值来源"),
                ("coordinateSources", "坐标来源"),
            ]:
                vals = params.get(key, [])
                param_rows.append((label, "、".join(vals) if vals else "-"))
            for label, value in param_rows:
                param_html += f'<tr><td class="label">{label}</td><td>{value}</td></tr>\n'

        # --- Compose full HTML ---
        param_section = ""
        if param_html:
            param_section = f'''
            <h2>5. 参数配置</h2>
            <table>{param_html}</table>
            '''

        html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
  body {{
    font-family: "Microsoft YaHei", "SimHei", "Helvetica Neue", Arial, sans-serif;
    max-width: 900px;
    margin: 40px auto;
    padding: 0 20px;
    color: #333;
    line-height: 1.6;
  }}
  h1 {{
    text-align: center;
    color: #1a5276;
    border-bottom: 3px solid #2980b9;
    padding-bottom: 12px;
    margin-bottom: 8px;
  }}
  .subtitle {{
    text-align: center;
    color: #666;
    font-size: 14px;
    margin-bottom: 30px;
  }}
  h2 {{
    color: #2c3e50;
    border-left: 4px solid #2980b9;
    padding-left: 10px;
    margin-top: 30px;
  }}
  h3 {{
    color: #34495e;
    margin-top: 20px;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    margin: 10px 0 20px 0;
    font-size: 14px;
  }}
  th, td {{
    border: 1px solid #bdc3c7;
    padding: 8px 12px;
    text-align: left;
  }}
  th {{
    background-color: #2980b9;
    color: white;
    font-weight: bold;
  }}
  tr:nth-child(even) {{ background-color: #f2f8fc; }}
  td.label {{
    font-weight: bold;
    width: 160px;
    background-color: #ecf0f1;
  }}
  .ok {{ color: #27ae60; font-weight: bold; }}
  .warn {{ color: #e74c3c; font-weight: bold; }}
  .footer {{
    margin-top: 40px;
    padding-top: 12px;
    border-top: 1px solid #bdc3c7;
    font-size: 12px;
    color: #999;
    text-align: center;
  }}
  ul {{ padding-left: 20px; }}
  li {{ margin: 4px 0; }}
  @media print {{
    body {{ margin: 0; padding: 20px; }}
    h2 {{ page-break-before: auto; }}
  }}
</style>
</head>
<body>

<h1>{title}</h1>
<div class="subtitle">报告生成时间: {now_str}</div>

<h2>1. 概述</h2>
<table>
{overview_html}
</table>

<h2>2. 指标统计</h2>
<table>
<tr><th>指标名称</th><th>结果数量</th><th>单位</th><th>告警阈值</th></tr>
{metrics_html}
</table>

<h2>3. 各站详细数据</h2>
{detail_html}

<h2>4. 质量评估</h2>
<ul>
{risk_html}
</ul>
{param_section}

<div class="footer">
  本报告由电离层闪烁指数监测系统(ISD)自动生成<br>
  数据仅供参考，最终解释权归用户所有
</div>

</body>
</html>'''
        return html
