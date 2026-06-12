"""JSON-safe MCP model objects."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class MCPToolMetadata:
    name: str
    category: str
    capability_level: str
    description: str
    arguments: dict[str, Any]
    return_schema: dict[str, Any]
    version: str = "v0.37.0"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MCPRequest:
    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    request_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MCPResponse:
    tool_name: str
    status: str
    result: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    request_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "status": self.status,
            "result": json_safe(self.result),
            "warnings": list(self.warnings),
            "error": self.error,
            "metadata": json_safe(self.metadata),
            "request_id": self.request_id,
        }


@dataclass(frozen=True)
class MCPTool:
    metadata: MCPToolMetadata
    handler: Callable[[dict[str, Any], Any], dict[str, Any]]
    required_arguments: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return self.metadata.to_dict()


def json_safe(value: Any) -> Any:
    """Return a JSON-serializable value without binary payloads."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, bytes):
        return f"<bytes:{len(value)}>"
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return json_safe(value.to_dict())
    if hasattr(value, "to_report") and callable(value.to_report):
        return json_safe(value.to_report())
    return str(value)
