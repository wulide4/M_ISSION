from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from isd.domain.models import ApiResponse, ErrorBody

Handler = Callable[[dict[str, Any]], ApiResponse[Any]]


@dataclass
class CommandBus:
    _handlers: dict[str, Handler] = field(default_factory=dict)

    def register(self, channel: str, handler: Handler) -> None:
        self._handlers[channel] = handler

    def dispatch(self, channel: str, payload: dict[str, Any] | None = None) -> ApiResponse[Any]:
        if channel not in self._handlers:
            return ApiResponse(
                success=False,
                error=ErrorBody(code="CHANNEL_NOT_FOUND", message=f"No handler for {channel}"),
            )
        try:
            return self._handlers[channel](payload or {})
        except Exception as exc:  # noqa: BLE001
            return ApiResponse(
                success=False,
                error=ErrorBody(code="UNHANDLED_EXCEPTION", message=str(exc)),
            )
