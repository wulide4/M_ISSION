from __future__ import annotations

from pathlib import Path

from isd.application.report_service import ReportService
from isd.domain.enums import ChainLevel, GnssSystem, MetricKey, SamplingMode, ThresholdSource
from isd.domain.models import ResultSet, ResultStats
from isd.infrastructure.db.sqlite import Database
from isd.infrastructure.repositories.result_repository import ResultRepository
from isd.infrastructure.repositories.template_repository import TemplateRepository


def _service(tmp_path: Path) -> ReportService:
    db = Database(tmp_path / "workspace" / "isd.sqlite3")
    migrations = Path(__file__).resolve().parents[1] / "src" / "isd" / "infrastructure" / "db" / "migrations"
    db.init(migrations)
    conn = db.connect()
    return ReportService(ResultRepository(conn), TemplateRepository(conn))


def _seed_results(service: ReportService, project_id: str) -> list[str]:
    rows = [
        ResultSet(
            id="res_1",
            task_id="task_1",
            sub_task_id="sub_1",
            project_id=project_id,
            metric=MetricKey.ROTI,
            station_id="ALBH",
            system=GnssSystem.GPS,
            chain_level=ChainLevel.FORMAL,
            sampling_mode=SamplingMode.STANDARD_30S,
            threshold_source=ThresholdSource.LITERATURE_REFERENCE,
            parameter_source_summary="test",
            data_path="workspace/a.npz",
            stats=ResultStats(min=1.0, max=3.0, mean=2.0),
            created_at="2026-04-21T10:00:00Z",
        ),
        ResultSet(
            id="res_2",
            task_id="task_1",
            sub_task_id="sub_2",
            project_id=project_id,
            metric=MetricKey.AATR,
            station_id="BAMF",
            system=GnssSystem.GPS,
            chain_level=ChainLevel.EXPERIMENTAL,
            sampling_mode=SamplingMode.STANDARD_30S,
            threshold_source=ThresholdSource.LITERATURE_REFERENCE,
            parameter_source_summary="test",
            data_path="workspace/b.npz",
            stats=ResultStats(min=0.1, max=0.9, mean=0.3),
            created_at="2026-04-21T10:01:00Z",
        ),
        ResultSet(
            id="res_3",
            task_id="task_2",
            sub_task_id="sub_3",
            project_id=project_id,
            metric=MetricKey.DIXSG,
            station_id="YEL2",
            system=GnssSystem.GPS,
            chain_level=ChainLevel.FORMAL,
            sampling_mode=SamplingMode.EXPERIMENTAL_1S_RESAMPLED,
            threshold_source=ThresholdSource.LITERATURE_REFERENCE,
            parameter_source_summary="test",
            data_path="workspace/c.npz",
            stats=ResultStats(min=0.0, max=10.0, mean=3.0),
            created_at="2026-04-21T10:02:00Z",
        ),
    ]
    service.result_repo.insert_many(rows)
    return [row.id for row in rows]


def test_report_preview_builds_summary_and_risk_flags(tmp_path: Path):
    service = _service(tmp_path)
    _seed_results(service, "proj_1")

    preview = service.preview_report(
        template_id="default_template",
        result_ids=[],
        options={"title": "demo"},
        project_id="proj_1",
    )

    assert preview["summary"]["resultCount"] == 3
    assert preview["summary"]["metricsBreakdown"]["ROTI"] == 1
    assert preview["summary"]["metricsBreakdown"]["AATR"] == 1
    assert "providerSources" in preview["summary"]
    assert "NON_FORMAL_CHAIN_LEVEL" in preview["summary"]["riskFlags"]
    assert "NON_STANDARD_SAMPLING_MODE" in preview["summary"]["riskFlags"]


def test_report_preview_filters_by_result_ids(tmp_path: Path):
    service = _service(tmp_path)
    ids = _seed_results(service, "proj_2")

    preview = service.preview_report(
        template_id="default_template",
        result_ids=[ids[1]],
        options={},
        project_id="proj_2",
    )

    assert preview["resultIds"] == [ids[1]]
    assert preview["summary"]["resultCount"] == 1
    assert preview["summary"]["metricsBreakdown"] == {"AATR": 1}


def test_report_export_writes_file(tmp_path: Path):
    service = _service(tmp_path)
    ids = _seed_results(service, "proj_3")
    out = tmp_path / "report" / "demo.txt"

    rsp = service.export_report(
        template_id="default_template",
        result_ids=[ids[0], ids[2]],
        options={"title": "regression report", "includeParameterSnapshot": True},
        output_path=str(out),
        project_id="proj_3",
    )

    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "resultCount=2" in content
    assert "template=default_template" in content
    assert "resultIds=" in content
    assert rsp["status"] == "SUCCESS"


def test_report_export_pdf_writes_file(tmp_path: Path):
    service = _service(tmp_path)
    ids = _seed_results(service, "proj_pdf")
    out = tmp_path / "report" / "demo.pdf"

    rsp = service.export_report(
        template_id="default_template",
        result_ids=[ids[0], ids[1]],
        options={"title": "pdf report", "includeParameterSnapshot": True},
        output_path=str(out),
        project_id="proj_pdf",
    )

    assert out.exists()
    assert out.suffix.lower() == ".pdf"
    assert rsp["status"] == "SUCCESS"
    assert rsp["format"] in {"PDF", "TEXT"}
    if rsp["format"] == "PDF":
        assert rsp["outputPath"].endswith(".pdf")
    else:
        assert rsp["fallbackUsed"] is True


def test_report_preview_excludes_non_gps_sigma_by_default(tmp_path: Path):
    service = _service(tmp_path)
    _seed_results(service, "proj_sigma")
    service.result_repo.insert_many(
        [
            ResultSet(
                id="res_sigma_glo",
                task_id="task_sigma",
                sub_task_id="sub_sigma",
                project_id="proj_sigma",
                metric=MetricKey.SIGMA_PHI_F,
                station_id="GLO1",
                system=GnssSystem.GLO,
                chain_level=ChainLevel.EXPERIMENTAL,
                sampling_mode=SamplingMode.STANDARD_30S,
                threshold_source=ThresholdSource.LITERATURE_REFERENCE,
                parameter_source_summary="test",
                data_path="workspace/sigma_glo.npz",
                stats=ResultStats(min=0.01, max=0.3, mean=0.1),
                created_at="2026-04-21T10:03:00Z",
            )
        ]
    )

    preview_default = service.preview_report(
        template_id="default_template",
        result_ids=[],
        options={},
        project_id="proj_sigma",
    )
    metrics_default = preview_default["summary"]["metricsBreakdown"]
    assert "SIGMA_PHI_F" not in metrics_default

    preview_opt_in = service.preview_report(
        template_id="default_template",
        result_ids=[],
        options={"includeNonGpsSigmaPhiF": True},
        project_id="proj_sigma",
    )
    metrics_opt_in = preview_opt_in["summary"]["metricsBreakdown"]
    assert metrics_opt_in["SIGMA_PHI_F"] == 1
