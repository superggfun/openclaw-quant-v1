"""Regime MCP runner methods."""

from __future__ import annotations

from typing import Any


class RegimeMCPRunner:
    def detect_regime(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        if arguments.get("benchmark"):
            context.regime_detector.benchmark = str(arguments["benchmark"]).upper()
        return context.regime_analytics.detect_and_save(start=arguments.get("start"), end=arguments.get("end"))

    def regime_history(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        return context.regime_analytics.history_report(limit=int(arguments.get("limit", 30)), regime=arguments.get("regime"))

    def regime_report(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        self._ensure_regime_history(context, bool(arguments.get("ensure_history", True)))
        return context.regime_analytics.regime_report()

    def regime_rank(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        self._ensure_regime_history(context, bool(arguments.get("ensure_history", True)))
        return context.regime_analytics.regime_rank(limit=int(arguments.get("limit", 10)))
