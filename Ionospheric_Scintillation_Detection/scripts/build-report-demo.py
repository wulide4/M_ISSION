from __future__ import annotations

import argparse
import json
from pathlib import Path

from isd.application import channels
from isd.application.bootstrap import bootstrap


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a demo report from existing project results.")
    parser.add_argument("--project-id", required=True, help="Existing project id in workspace DB")
    parser.add_argument(
        "--output",
        default="workspace/reports/report_demo.pdf",
        help="Output report path relative to project root",
    )
    parser.add_argument("--title", default="MVP Demo Report")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    context = bootstrap(project_root / "src" / "isd")

    list_rsp = context.command_bus.dispatch(channels.RESULT_LIST, {"projectId": args.project_id})
    if not list_rsp.success:
        print(list_rsp.error.message if list_rsp.error else "result:list failed")
        return 1
    result_ids = [row["id"] for row in (list_rsp.data or [])][:8]
    if not result_ids:
        print("No results found for project:", args.project_id)
        return 1

    preview_rsp = context.command_bus.dispatch(
        channels.REPORT_PREVIEW,
        {
            "projectId": args.project_id,
            "templateId": "default_template",
            "resultIds": result_ids,
            "options": {"title": args.title, "includeParameterSnapshot": True, "includeLogSummary": True},
        },
    )
    if not preview_rsp.success:
        print(preview_rsp.error.message if preview_rsp.error else "report:preview failed")
        return 1

    output_path = (project_root / args.output).resolve()
    export_rsp = context.command_bus.dispatch(
        channels.REPORT_EXPORT,
        {
            "projectId": args.project_id,
            "templateId": "default_template",
            "resultIds": result_ids,
            "options": {
                "title": args.title,
                "includeParameterSnapshot": True,
                "includeLogSummary": True,
                "includeNonGpsSigmaPhiF": False,
            },
            "outputPath": str(output_path),
        },
    )
    if not export_rsp.success:
        print(export_rsp.error.message if export_rsp.error else "report:export failed")
        return 1

    info = {
        "projectId": args.project_id,
        "resultCountUsed": len(result_ids),
        "outputPath": export_rsp.data.get("outputPath"),
        "previewSummary": preview_rsp.data.get("summary"),
    }
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
