"""Agent export CLI command."""

from __future__ import annotations

from pathlib import Path

from quant.agent_export.agent_exporter import SUPPORTED_FORMATS


def register_parser(subparsers) -> None:
    parser = subparsers.add_parser("export-for-agent", help="Export a compact LLM/agent summary from a report.")
    parser.add_argument("--report", required=True, help="Path to an existing JSON report.")
    parser.add_argument("--format", choices=sorted(SUPPORTED_FORMATS), default="text")
    parser.add_argument("--max-tokens", type=int, default=800)
    parser.add_argument("--output", default=None, help="Optional output path.")


def handle(args, context) -> int:
    rendered = context.agent_exporter.export_file(
        report_path=Path(args.report),
        output_format=args.format,
        max_tokens=args.max_tokens,
        output_path=Path(args.output) if args.output else None,
    )
    print(rendered, end="" if rendered.endswith("\n") else "\n")
    if args.output:
        print(f"export_path: {args.output}")
    return 0
