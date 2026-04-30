from __future__ import annotations

from dataclasses import dataclass

from isd.domain.enums import (
    BatchPageState,
    DataCalcPageState,
    GlobalAppState,
    ProjectPageState,
    ReportPageState,
    VisualizationPageState,
)


@dataclass
class UiStateMachines:
    global_state: GlobalAppState = GlobalAppState.BOOTING
    project_page_state: ProjectPageState = ProjectPageState.EMPTY
    data_calc_page_state: DataCalcPageState = DataCalcPageState.PRISTINE
    batch_page_state: BatchPageState = BatchPageState.EMPTY_QUEUE
    visualization_page_state: VisualizationPageState = VisualizationPageState.NO_RESULT
    report_page_state: ReportPageState = ReportPageState.NO_SELECTION

    def set_global_ready(self) -> None:
        self.global_state = GlobalAppState.READY

    def on_project_opened(self) -> None:
        self.global_state = GlobalAppState.PROJECT_OPENED

    def on_task_running(self) -> None:
        self.global_state = GlobalAppState.TASK_RUNNING

    def on_task_idle(self) -> None:
        self.global_state = GlobalAppState.READY
