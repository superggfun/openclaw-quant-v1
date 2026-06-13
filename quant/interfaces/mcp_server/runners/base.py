"""Shared MCP runner helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quant.config import DEFAULT_SYMBOLS


class BaseMCPRunner:
    def not_supported(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        return {"status": "NOT_SUPPORTED"}

    @staticmethod
    def _symbols(arguments: dict[str, Any]) -> list[str]:
        raw = arguments.get("symbols")
        if raw is None:
            return list(DEFAULT_SYMBOLS)
        if isinstance(raw, str):
            return [symbol.strip().upper() for symbol in raw.replace(",", " ").split() if symbol.strip()]
        return [str(symbol).strip().upper() for symbol in raw if str(symbol).strip()]

    @staticmethod
    def _ensure_regime_history(context, enabled: bool) -> None:
        if enabled and context.regime_history_store.latest() is None:
            context.regime_analytics.detect_and_save()

    @staticmethod
    def _latest_report(pattern: str) -> Path | None:
        reports = sorted(Path("reports").glob(pattern), key=lambda path: path.stat().st_mtime, reverse=True)
        return reports[0] if reports else None

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))
