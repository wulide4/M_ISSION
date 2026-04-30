from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import textwrap

from isd.application.risk_flags import derive_result_risk_flags
from isd.domain.enums import MetricKey
from isd.infrastructure.repositories.result_repository import ResultRepository
from isd.infrastructure.repositories.template_repository import TemplateRepository


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
                self._export_pdf(preview, out)
                return {"outputPath": str(out), "status": "SUCCESS", "format": "PDF", "fallbackUsed": False}
            except Exception as exc:  # noqa: BLE001
                fallback = out.with_suffix(".txt")
                self._export_text(preview, fallback)
                return {
                    "outputPath": str(fallback),
                    "status": "SUCCESS",
                    "format": "TEXT",
                    "fallbackUsed": True,
                    "warning": f"PDF export failed, fallback to text: {exc}",
                }

        self._export_text(preview, out)
        return {"outputPath": str(out), "status": "SUCCESS", "format": "TEXT", "fallbackUsed": False}

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
            "payload": {
                "sections": ["overview", "metrics", "risk_flags", "result_cards"],
            },
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
                row
                for row in rows
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
        return {
            "projectIds": project_ids,
            "taskIds": task_ids,
            "taskCount": len(task_ids),
        }

    def _build_parameter_snapshot(self, rows: list[dict]) -> dict:
        chain_levels = sorted({row.get("chain_level") for row in rows if row.get("chain_level")})
        sampling_modes = sorted({row.get("sampling_mode") for row in rows if row.get("sampling_mode")})
        threshold_sources = sorted({row.get("threshold_source") for row in rows if row.get("threshold_source")})
        parameter_sources = sorted(
            {row.get("parameter_source_summary") for row in rows if row.get("parameter_source_summary")}
        )
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
            cards.append(
                {
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
                        "eventCount": stats.get("event_count"),
                    },
                }
            )
        return cards

    def _build_report_lines(self, preview: dict) -> list[str]:
        summary = preview["summary"]
        lines = [
            "Ionospheric Scintillation Detection Report",
            f"template={preview['templateId']} ({preview['templateName']})",
            f"title={preview.get('options', {}).get('title', '')}",
            f"projectId={preview.get('projectId') or '-'}",
            f"resultCount={summary['resultCount']}",
            f"metrics={summary['metricsBreakdown']}",
            f"stations={summary['stations']}",
            f"chainLevels={summary['chainLevels']}",
            f"samplingModes={summary['samplingModes']}",
            f"providerSources={summary.get('providerSources', [])}",
            f"riskFlags={summary['riskFlags']}",
            f"taskInfo={preview.get('taskInfo', {})}",
        ]
        if preview.get("parameterSnapshot"):
            lines.append(f"parameterSnapshot={preview['parameterSnapshot']}")
        if preview.get("options", {}).get("includeLogSummary", True):
            lines.append("includeLogSummary=true")
        lines.append(f"resultIds={','.join(preview['resultIds'])}")

        cards = preview.get("resultCards", [])
        lines.append("")
        lines.append("resultCards:")
        for card in cards[:20]:
            lines.append(
                f"- {card.get('id')} | {card.get('metric')} | {card.get('station')} | "
                f"{card.get('system')} | coord={card.get('coordinateSource')} | "
                f"providers={card.get('providerSummary')} | risk={card.get('riskFlags')} | stats={card.get('stats')}"
            )
        return lines

    def _extract_provider_summary(self, parameter_source_summary: str | None) -> str:
        text = str(parameter_source_summary or "").strip()
        if not text:
            return "-"
        marker = "providers="
        idx = text.find(marker)
        if idx < 0:
            return "-"
        return text[idx + len(marker) :].strip()

    def _export_text(self, preview: dict, out: Path) -> None:
        lines = self._build_report_lines(preview)
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _export_pdf(self, preview: dict, out: Path) -> None:
        lines = self._build_report_lines(preview)
        wrapped: list[str] = []
        for line in lines:
            chunks = textwrap.wrap(line, width=100, replace_whitespace=False) or [line]
            wrapped.extend(chunks)

        lines_per_page = 46
        pages: list[list[str]] = []
        for idx in range(0, len(wrapped), lines_per_page):
            pages.append(wrapped[idx : idx + lines_per_page])
        if not pages:
            pages = [["Ionospheric Scintillation Detection Report", "No result selected"]]

        self._write_simple_pdf(out, pages)

    def _write_simple_pdf(self, out: Path, pages: list[list[str]]) -> None:
        objects: list[bytes] = []

        # obj 1: catalog
        objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")

        page_count = len(pages)
        font_obj_id = 3 + page_count * 2
        kids = []
        for idx in range(page_count):
            page_obj_id = 3 + idx * 2
            kids.append(f"{page_obj_id} 0 R")
        objects.append(f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {page_count} >>".encode("ascii"))

        # page/content object pairs
        for idx, page_lines in enumerate(pages):
            page_obj_id = 3 + idx * 2
            content_obj_id = page_obj_id + 1
            page_obj = (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                f"/Resources << /Font << /F1 {font_obj_id} 0 R >> >> "
                f"/Contents {content_obj_id} 0 R >>"
            ).encode("ascii")
            objects.append(page_obj)

            lines = [b"BT", b"/F1 11 Tf", b"50 795 Td", b"15 TL"]
            for raw in page_lines:
                safe = self._pdf_escape(raw)
                lines.append(f"({safe}) Tj".encode("latin-1", errors="replace"))
                lines.append(b"T*")
            lines.append(b"ET")
            stream = b"\n".join(lines) + b"\n"
            content_obj = f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"endstream"
            objects.append(content_obj)

        # font object
        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("wb") as handle:
            handle.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
            offsets = [0]
            for idx, body in enumerate(objects, start=1):
                offsets.append(handle.tell())
                handle.write(f"{idx} 0 obj\n".encode("ascii"))
                handle.write(body)
                handle.write(b"\nendobj\n")

            xref_start = handle.tell()
            handle.write(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
            handle.write(b"0000000000 65535 f \n")
            for off in offsets[1:]:
                handle.write(f"{off:010d} 00000 n \n".encode("ascii"))

            handle.write(
                (
                    "trailer\n"
                    f"<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
                    "startxref\n"
                    f"{xref_start}\n"
                    "%%EOF\n"
                ).encode("ascii")
            )

    def _pdf_escape(self, text: str) -> str:
        return str(text).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
