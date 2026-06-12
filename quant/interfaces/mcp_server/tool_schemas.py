"""Stable MCP argument and return schemas."""

from __future__ import annotations


def object_schema(properties: dict | None = None, required: list[str] | None = None) -> dict:
    return {
        "type": "object",
        "properties": properties or {},
        "required": required or [],
    }


def response_schema(description: str) -> dict:
    return {
        "type": "object",
        "description": description,
        "json_safe": True,
        "binary_payloads": False,
    }

