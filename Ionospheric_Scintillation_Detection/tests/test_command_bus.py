from isd.application.command_bus import CommandBus
from isd.domain.models import ApiResponse


def test_command_bus_dispatch():
    bus = CommandBus()
    bus.register("demo:ok", lambda payload: ApiResponse(success=True, data={"x": payload.get("x", 0)}))

    rsp = bus.dispatch("demo:ok", {"x": 7})
    assert rsp.success is True
    assert rsp.data["x"] == 7


def test_command_bus_missing_channel():
    bus = CommandBus()
    rsp = bus.dispatch("missing", {})
    assert rsp.success is False
    assert rsp.error is not None
