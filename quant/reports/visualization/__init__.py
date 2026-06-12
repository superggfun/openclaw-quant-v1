"""Visualization layered namespace."""

from quant.visualization import *  # noqa: F401,F403
from quant.utils.module_alias import alias_modules

alias_modules(
    __name__,
    {
        "chart_builder": "quant.visualization.chart_builder",
        "report_visualizer": "quant.visualization.report_visualizer",
    },
)

