from __future__ import annotations

import inspect
import time
from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from pe.axiz.payments_evals_lab.domain.models import ToolCallTrace

T = TypeVar("T", bound=BaseModel)


class ToolDefinition:
    def __init__(
        self,
        name: str,
        description: str,
        args_model: type[BaseModel],
        handler: Callable[..., Any],
    ) -> None:
        self.name = name
        self.description = description
        self.args_model = args_model
        self.handler = handler


class ToolRegistry:
    """Registro de herramientas con validación Pydantic y telemetría uniforme."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        if definition.name in self._tools:
            raise ValueError(f"Herramienta duplicada: {definition.name}")
        self._tools[definition.name] = definition

    def names(self) -> list[str]:
        return sorted(self._tools)

    def schema(self, name: str) -> dict[str, Any]:
        tool = self._tools[name]
        return tool.args_model.model_json_schema()

    async def invoke(self, name: str, arguments: dict[str, Any], turn_id: str | None = None) -> ToolCallTrace:
        started = time.perf_counter()
        definition = self._tools.get(name)
        if definition is None:
            return ToolCallTrace(
                tool=name,
                arguments=arguments,
                schema_valid=False,
                error="Herramienta no registrada",
                latency_ms=(time.perf_counter() - started) * 1000,
                turn_id=turn_id,
            )
        try:
            parsed = definition.args_model.model_validate(arguments)
        except ValidationError as exc:
            return ToolCallTrace(
                tool=name,
                arguments=arguments,
                schema_valid=False,
                error=str(exc),
                latency_ms=(time.perf_counter() - started) * 1000,
                turn_id=turn_id,
            )

        try:
            result = definition.handler(**parsed.model_dump())
            if inspect.isawaitable(result):
                result = await result
            if isinstance(result, BaseModel):
                result = result.model_dump(mode="json")
            return ToolCallTrace(
                tool=name,
                arguments=parsed.model_dump(mode="json"),
                schema_valid=True,
                result=result,
                latency_ms=(time.perf_counter() - started) * 1000,
                turn_id=turn_id,
            )
        except Exception as exc:  # noqa: BLE001
            return ToolCallTrace(
                tool=name,
                arguments=parsed.model_dump(mode="json"),
                schema_valid=True,
                error=f"{type(exc).__name__}: {exc}",
                latency_ms=(time.perf_counter() - started) * 1000,
                turn_id=turn_id,
            )
