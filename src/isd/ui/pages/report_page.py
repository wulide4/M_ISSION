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
from isd.ui.i18n import LanguageManager, tr


class ReportCenterPage(QWidget):
    def __init__(self, bus: CommandBus) -> None:
        super().__init__()
        self.bus = bus
        self._lm = LanguageManager.instance()
        self._selected_result_ids: list[str] = []

        self.project_id_edit = QLineEdit()
        self.template_edit = QLineEdit("default_template")
        self.title_edit = QLineEdit(tr("rpt.default_title"))
        self.output_edit = QLineEdit("workspace/reports/report.html")

        self.include_stats = QCheckBox(tr("rpt.include_stats"))
        self.include_stats.setChecked(True)
        self.include_params = QCheckBox(tr("rpt.include_params"))
        self.include_params.setChecked(True)
        self.open_after_export = QCheckBox(tr("rpt.open_after"))
        self.open_after_export.setChecked(True)

        self.preview_box = QTextEdit()
        self.preview_box.setReadOnly(True)
        self._preview_html = ""
        self.result_picker = QListWidget()
        self.result_picker.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.result_picker.itemSelectionChanged.connect(self._sync_result_ids)

        self.state_hint = QLabel("Status: Ready")

        self._build_ui()
        self._lm.language_changed.connect(self._retranslate)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        self.title_label = QLabel(tr("rpt.title"))
        self.title_label.setStyleSheet("""
            font-size: 22px;
            font-weight: bold;
            color: #00e5ff;
            margin: 10px 0;
        """)
        layout.addWidget(self.title_label)

        self._settings_box = QGroupBox(tr("rpt.settings"))
        self._form_labels = []
        form = QFormLayout()
        form.setVerticalSpacing(10)
        for key, widget in [
            ("rpt.project_id", self.project_id_edit),
            ("rpt.template", self.template_edit),
            ("rpt.report_title", self.title_edit),
            ("rpt.output_path", self.output_edit),
        ]:
            lbl = QLabel(tr(key))
            self._form_labels.append((key, lbl))
            form.addRow(lbl, widget)
        form.addRow("", self.include_stats)
        form.addRow("", self.include_params)
        form.addRow("", self.open_after_export)
        self._settings_box.setLayout(form)
        layout.addWidget(self._settings_box)

        btn_row = QHBoxLayout()
        self.load_btn = QPushButton(tr("rpt.btn.load"))
        self.load_btn.clicked.connect(self.load_results)
        self.load_btn.setProperty("secondary", "true")

        self.browse_btn = QPushButton(tr("rpt.btn.browse"))
        self.browse_btn.clicked.connect(self.browse)
        self.browse_btn.setProperty("secondary", "true")

        self.preview_btn = QPushButton(tr("rpt.btn.preview"))
        self.preview_btn.clicked.connect(self.preview)

        self.export_btn = QPushButton(tr("rpt.btn.export"))
        self.export_btn.clicked.connect(self.export)

        btn_row.addWidget(self.load_btn)
        btn_row.addWidget(self.browse_btn)
        btn_row.addWidget(self.preview_btn)
        btn_row.addWidget(self.export_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._select_label = QLabel(tr("rpt.select_results"))
        layout.addWidget(self._select_label)
        layout.addWidget(self.result_picker)
        layout.addWidget(self.state_hint)
        layout.addWidget(self.preview_box)

    def _retranslate(self) -> None:
        self.title_label.setText(tr("rpt.title"))
        self._settings_box.setTitle(tr("rpt.settings"))
        for key, lbl in self._form_labels:
            lbl.setText(tr(key))
        self.load_btn.setText(tr("rpt.btn.load"))
        self.browse_btn.setText(tr("rpt.btn.browse"))
        self.preview_btn.setText(tr("rpt.btn.preview"))
        self.export_btn.setText(tr("rpt.btn.export"))
        self._select_label.setText(tr("rpt.select_results"))
        self.include_stats.setText(tr("rpt.include_stats"))
        self.include_params.setText(tr("rpt.include_params"))
        self.open_after_export.setText(tr("rpt.open_after"))

    def _sync_result_ids(self) -> None:
        self._selected_result_ids = [
            str(item.data(Qt.ItemDataRole.UserRole) or "")
            for item in self.result_picker.selectedItems()
            if item.data(Qt.ItemDataRole.UserRole)
        ]
        self.state_hint.setText(f"Status: {len(self._selected_result_ids)} results selected")

    def browse(self) -> None:
        p, _ = QFileDialog.getSaveFileName(
            self, tr("rpt.btn.browse"), self.output_edit.text(),
            "HTML (*.html);;PDF (*.pdf);;Text (*.txt)",
        )
        if p:
            self.output_edit.setText(p)

    def load_results(self) -> None:
        project_id = self.project_id_edit.text().strip()
        if not project_id:
            QMessageBox.warning(self, tr("dlg.warning"), "Please enter a project ID")
            return

        rsp = self.bus.dispatch(channels.RESULT_LIST, {"projectId": project_id})
        if not rsp.success:
            QMessageBox.warning(self, tr("dlg.warning"), rsp.error.message if rsp.error else "Load failed")
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

        self.state_hint.setText(f"Status: Loaded {self.result_picker.count()} results")

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
            QMessageBox.warning(self, tr("dlg.warning"), "Please enter a project ID")
            return

        if not self._selected_result_ids:
            QMessageBox.warning(self, tr("dlg.warning"), "Please select at least one result")
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
            QMessageBox.critical(self, tr("dlg.error"), rsp.error.message if rsp.error else "Preview failed")
            return

        preview_data = rsp.data or {}
        self._preview_html = self._render_preview_html(preview_data)
        self.preview_box.setHtml(self._preview_html)
        self.state_hint.setText("Status: Preview generated")

    def _render_preview_html(self, data: dict) -> str:
        summary = data.get("summary", {})
        cards = data.get("resultCards", [])
        options = data.get("options", {})
        title = options.get("title") or tr("rpt.default_title")

        rows_html = ""
        for card in cards[:50]:
            metric = card.get("metric", "-")
            metric_name = tr(f"metric.{metric}") if metric in ("ROTI", "AATR", "IAATR", "DIXSG", "SIGMA_PHI_F", "S4C") else metric
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
        risk_items = "".join(f"<li>{f}</li>" for f in risk_flags) if risk_flags else "<li>None</li>"

        return f"""
        <div style="font-family: 'Microsoft YaHei', sans-serif; color: #333;">
            <h2 style="color: #1a5276; border-bottom: 2px solid #2980b9; padding-bottom: 6px;">{title}</h2>
            <p>Results: <b>{summary.get('resultCount', 0)}</b> |
               Stations: <b>{', '.join(summary.get('stations', [])) or '-'}</b></p>
            <table border="1" cellpadding="4" cellspacing="0"
                   style="border-collapse:collapse; font-size:12px; width:100%;">
                <tr style="background:#2980b9; color:white;">
                    <th>Metric</th><th>Station</th><th>System</th>
                    <th>Min</th><th>Max</th><th>Mean</th><th>Events</th>
                </tr>
                {rows_html}
            </table>
            <h3 style="color:#2c3e50; margin-top:12px;">Quality Flags</h3>
            <ul style="font-size:12px;">{risk_items}</ul>
        </div>
        """

    def export(self) -> None:
        output = self.output_edit.text().strip()
        if not output:
            QMessageBox.warning(self, tr("dlg.warning"), "Please specify output path")
            return

        project_id = self.project_id_edit.text().strip()
        if not project_id:
            QMessageBox.warning(self, tr("dlg.warning"), "Please enter a project ID")
            return

        if not self._selected_result_ids:
            QMessageBox.warning(self, tr("dlg.warning"), "Please select at least one result")
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
            msg = f"Report exported: {exported}"
            if warning:
                msg += f"\n\nNote: {warning}"
            self.state_hint.setText("Status: Export complete")
            QMessageBox.information(self, tr("dlg.success"), msg)
            if self.open_after_export.isChecked():
                webbrowser.open(str(Path(exported).resolve()))
        else:
            QMessageBox.critical(self, tr("dlg.error"), rsp.error.message if rsp.error else "Export failed")
