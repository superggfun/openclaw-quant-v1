"""CLI command for report visualization."""

from __future__ import annotations

import argparse
from pathlib import Path


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("visualize-report", help="Generate charts and a dashboard from a JSON report.")
    parser.add_argument("--report", required=True, help="Path to an existing JSON report.")
    parser.add_argument("--output-dir", default="reports/charts", help="Directory for generated chart files.")


def handle(args: argparse.Namespace, context) -> int:
    result = context.report_visualizer.visualize_file(Path(args.report), output_dir=Path(args.output_dir))
    print("Visualization Summary")
    print(f"report_type: {result.report_type}")
    print(f"source_report: {result.source_report}")
    print(f"output_dir: {result.output_dir}")
    print(f"dashboard: {result.dashboard_path}")
    print("charts:")
    for chart in result.charts:
        print(f"- {chart['chart_id']}: {chart['png_path']} | {chart['svg_path']}")
    for warning in result.warnings:
        print(f"warning: {warning}")
    return 0
