"""Visualization MCP runner methods."""

from __future__ import annotations

from pathlib import Path
from typing import Any


class VisualizationMCPRunner:
    def list_visualizations(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        root = Path(arguments.get("charts_dir", "reports/charts"))
        files = sorted(path for path in root.glob("*") if path.is_file()) if root.exists() else []
        return {"charts_dir": str(root), "visualizations": [str(path) for path in files], "count": len(files)}

    def visualization_summary(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        listing = self.list_visualizations(arguments, context)
        by_suffix: dict[str, int] = {}
        for path in listing["visualizations"]:
            suffix = Path(path).suffix.lower() or "<none>"
            by_suffix[suffix] = by_suffix.get(suffix, 0) + 1
        return listing | {"by_suffix": by_suffix}
