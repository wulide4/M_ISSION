from __future__ import annotations

import json
import webbrowser
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from isd.application import channels
from isd.application.command_bus import CommandBus


class ReportCenterPage(QWidget):
    def __init__(self, bus: CommandBus) -> None:
        super().__init__()
        self.bus = bus
        self._selected_result_ids: list[str] = []

        self.project_id_edit = QLineEdit()
        self.template_edit = QLineEdit("default_template")
        self.title_edit = QLineEdit("闪烁指数监测报告")
        self.output_edit = QLineEdit("workspace/reports/report.html")

        self.include_stats = QCheckBox("包含统计摘要")
        self.include_stats.setChecked(True)
        self.include_params = QCheckBox("包含参数配置")
        self.include_params.setChecked(True)
        self.open_after_export = QCheckBox("导出后打开报告")
        self.open_after_export.setChecked(True)

        self.preview_box = QTextEdit()
        self.preview_box.setReadOnly(True)
        self._preview_html = ""
        self.result_picker = QListWidget()
        self.result_picker.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.result_picker.itemSelectionChanged.connect(self._sync_result_ids)

        self.state_hint = QLabel("状态: 就绪")

        layout = QVBoxLayout(self)
        title = QLabel("报告中心")
        title.setStyleSheet("""
            font-size: 22px;
            font-weight: bold;
            color: #00e5ff;
            margin: 10px 0;
        """)
        layout.addWidget(title)

        basic_box = QGroupBox("报告设置")
        form = QFormLayout()
        form.setVerticalSpacing(10)
        form.addRow("项目ID", self.project_id_edit)
        form.addRow("模板", self.template_edit)
        form.addRow("标题", self.title_edit)
        form.addRow("输出路径", self.output_edit)
        form.addRow("", self.include_stats)
        form.addRow("", self.include_params)
        form.addRow("", self.open_after_export)
        basic_box.setLayout(form)
        layout.addWidget(basic_box)

        btn_row = QHBoxLayout()
        load_btn = QPushButton("加载结果")
        load_btn.clicked.connect(self.load_results)
        load_btn.setProperty("secondary", "true")

        browse_btn = QPushButton("选择路径")
        browse_btn.clicked.connect(self.browse)
        browse_btn.setProperty("secondary", "true")

        preview_btn = QPushButton("预览报告")
        preview_btn.clicked.connect(self.preview)

        export_btn = QPushButton("导出报告")
        export_btn.clicked.connect(self.export)

        btn_row.addWidget(load_btn)
        btn_row.addWidget(browse_btn)
        btn_row.addWidget(preview_btn)
        btn_row.addWidget(export_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        layout.addWidget(QLabel("选择结果（可多选）"))
        layout.addWidget(self.result_picker)
        layout.addWidget(self.state_hint)
        layout.addWidget(self.preview_box)

    def _sync_result_ids(self) -> None:
        self._selected_result_ids = [
            str(item.data(Qt.ItemDataRole.UserRole) or "")
            for item in self.result_picker.selectedItems()
            if item.data(Qt.ItemDataRole.UserRole)
        ]
        self.state_hint.setText(f"状态: 已选择 {len(self._selected_result_ids)} 条结果")

    def browse(self) -> None:
        p, _ = QFileDialog.getSaveFileName(
            self,
            "导出报告",
            self.output_edit.text(),
            "HTML (*.html);;PDF (*.pdf);;Text (*.txt)",
        )
        if p:
            self.output_edit.setText(p)

    def load_results(self) -> None:
        project_id = self.project_id_edit.text().strip()
        if not project_id:
            QMessageBox.warning(self, "警告", "请先填写项目ID")
            return

        rsp = self.bus.dispatch(channels.RESULT_LIST, {"projectId": project_id})
        if not rsp.success:
            QMessageBox.warning(self, "警告", rsp.error.message if rsp.error else "加载失败")
            return

        self.result_picker.clear()
        self._selected_result_ids = []
        for row in rsp.data or []:
            rid = row.get("id", "")
            metric = row.get("metric", "-")
            station = row.get("station_id") or "-"
            label = f"{metric} | {station} | {rid[:12]}..."
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, rid)
            self.result_picker.addItem(item)

        self.state_hint.setText(f"状态: 已加载 {self.result_picker.count()} 条结果")

    def _build_options(self) -> dict:
        return {
            "title": self.title_edit.text().strip(),
            "includeStats": self.include_stats.isChecked(),
            "includeParameterSnapshot": self.include_params.isChecked(),
            "includeParams": self.include_params.isChecked(),
        }

    def preview(self) -> None:
        project_id = self.project_id_edit.text().strip()
        if not project_id:
            QMessageBox.warning(self, "警告", "请先填写项目ID")
            return

        if not self._selected_result_ids:
            QMessageBox.warning(self, "警告", "请至少选择一个结果")
            return

        rsp = self.bus.dispatch(
            channels.REPORT_PREVIEW,
            {
                "projectId": project_id,
                "templateId": self.template_edit.text().strip() or "default_template",
                "resultIds": self._selected_result_ids,
                "options": self._build_options(),
            },
        )
        if not rsp.success:
            QMessageBox.critical(self, "错误", rsp.error.message if rsp.error else "预览失败")
            return

        # Store preview data and render HTML
        preview_data = rsp.data or {}
        self._preview_html = self._render_preview_html(preview_data)
        self.preview_box.setHtml(self._preview_html)
        self.state_hint.setText("状态: 预览已生成")

    def _render_preview_html(self, data: dict) -> str:
        """Render a concise in-app HTML preview from the preview data."""
        summary = data.get("summary", {})
        cards = data.get("resultCards", [])
        options = data.get("options", {})
        title = options.get("title") or "电离层闪烁指数监测报告"

        METRIC_NAMES = {
            "ROTI": "ROTI (电离层变化率总电子含量)",
            "AATR": "AATR (绝对电离层变化率)",
            "IAATR": "IAATR (瞬时绝对电离层变化率)",
            "DIXSG": "DIXSG (空间梯度扰动指数)",
            "SIGMA_PHI_F": "σφf (振幅闪烁指数)",
        }

        rows_html = ""
        for card in cards[:50]:
            metric = card.get("metric", "-")
            metric_name = METRIC_NAMES.get(metric, metric)
            station = card.get("station") or "-"
            system = card.get("system") or "-"
            stats = card.get("stats", {})
            min_v = stats.get("min")
            max_v = stats.get("max")
            mean_v = stats.get("mean")
            ev = stats.get("eventCount")
            min_text = f"{min_v:.4f}" if min_v is not None else "-"
            max_text = f"{max_v:.4f}" if max_v is not None else "-"
            mean_text = f"{mean_v:.4f}" if mean_v is not None else "-"
            ev_text = str(ev) if ev is not None else "-"
            rows_html += (
                f"<tr><td>{metric_name}</td><td>{station}</td><td>{system}</td>"
                f"<td>{min_text}</td><td>{max_text}</td><td>{mean_text}</td>"
                f"<td>{ev_text}</td></tr>"
            )

        risk_flags = summary.get("riskFlags", [])
        risk_items = "".join(f"<li>{f}</li>" for f in risk_flags) if risk_flags else "<li>无</li>"

        return f"""
        <div style="font-family: 'Microsoft YaHei', sans-serif; color: #333;">
            <h2 style="color: #1a5276; border-bottom: 2px solid #2980b9; padding-bottom: 6px;">{title}</h2>
            <p>结果总数: <b>{summary.get('resultCount', 0)}</b> 条 |
               站点: <b>{', '.join(summary.get('stations', [])) or '-'}</b></p>
            <table border="1" cellpadding="4" cellspacing="0"
                   style="border-collapse:collapse; font-size:12px; width:100%;">
                <tr style="background:#2980b9; color:white;">
                    <th>指标</th><th>站点</th><th>系统</th>
                    <th>最小值</th><th>最大值</th><th>均值</th><th>事件数</th>
                </tr>
                {rows_html}
            </table>
            <h3 style="color:#2c3e50; margin-top:12px;">质量标志</h3>
            <ul style="font-size:12px;">{risk_items}</ul>
        </div>
        """

    def export(self) -> None:
        output = self.output_edit.text().strip()
        if not output:
            QMessageBox.warning(self, "警告", "请填写输出路径")
            return

        project_id = self.project_id_edit.text().strip()
        if not project_id:
            QMessageBox.warning(self, "警告", "请先填写项目ID")
            return

        if not self._selected_result_ids:
            QMessageBox.warning(self, "警告", "请至少选择一个结果")
            return

        payload = {
            "projectId": project_id,
            "templateId": self.template_edit.text().strip() or "default_template",
            "resultIds": self._selected_result_ids,
            "options": self._build_options(),
            "outputPath": output,
        }

        rsp = self.bus.dispatch(channels.REPORT_EXPORT, payload)
        if rsp.success:
            exported = (rsp.data or {}).get("outputPath", output)
            warning = (rsp.data or {}).get("warning")
            msg = f"报告已导出至: {exported}"
            if warning:
                msg += f"\n\n注意: {warning}"
            self.state_hint.setText("状态: 导出完成")
            QMessageBox.information(self, "成功", msg)
            if self.open_after_export.isChecked():
                webbrowser.open(str(Path(exported).resolve()))
        else:
            QMessageBox.critical(self, "错误", rsp.error.message if rsp.error else "导出失败")
