from isd.domain.enums import GlobalAppState
from isd.domain.state_machine import UiStateMachines


def test_state_machine_basic_flow():
    sm = UiStateMachines()
    assert sm.global_state == GlobalAppState.BOOTING

    sm.set_global_ready()
    assert sm.global_state == GlobalAppState.READY

    sm.on_project_opened()
    assert sm.global_state == GlobalAppState.PROJECT_OPENED

    sm.on_task_running()
    assert sm.global_state == GlobalAppState.TASK_RUNNING

    sm.on_task_idle()
    assert sm.global_state == GlobalAppState.READY
