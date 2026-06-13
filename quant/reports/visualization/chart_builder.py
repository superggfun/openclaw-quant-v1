"""Small dependency-free SVG, PNG, and HTML chart builder."""

from __future__ import annotations

import html
import math
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


WIDTH = 900
HEIGHT = 420
MARGIN = 54
COLORS = ["#2563eb", "#16a34a", "#dc2626", "#9333ea", "#ea580c", "#0891b2", "#4f46e5", "#65a30d"]


@dataclass(frozen=True)
class ChartArtifact:
    chart_id: str
    title: str
    png_path: str
    svg_path: str

    def to_dict(self) -> dict[str, str]:
        return {
            "chart_id": self.chart_id,
            "title": self.title,
            "png_path": self.png_path,
            "svg_path": self.svg_path,
        }


class ChartBuilder:
    """Create simple deterministic charts without optional plotting dependencies."""

    def __init__(self, output_dir: str | Path = "reports/charts") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def line_chart(self, prefix: str, chart_id: str, title: str, points: list[tuple[str, float]]) -> ChartArtifact | None:
        clean = self._clean_points(points)
        if not clean:
            return None
        coords, y_min, y_max = self._line_coords(clean)
        polyline = " ".join(f"{x:.2f},{y:.2f}" for x, y in coords)
        svg = self._svg_header(title)
        svg += self._axes(y_min, y_max)
        svg += f'<polyline fill="none" stroke="{COLORS[0]}" stroke-width="3" points="{polyline}" />\n'
        svg += self._label(clean[0][0], MARGIN, HEIGHT - 16, "start")
        svg += self._label(clean[-1][0], WIDTH - MARGIN, HEIGHT - 16, "end")
        svg += "</svg>\n"
        return self._write_artifact(prefix, chart_id, title, svg, self._png_line(clean, title))

    def bar_chart(self, prefix: str, chart_id: str, title: str, values: dict[str, float]) -> ChartArtifact | None:
        clean = [(str(key), float(value)) for key, value in values.items() if self._finite(value)]
        if not clean:
            return None
        y_min = min(0.0, min(value for _, value in clean))
        y_max = max(0.0, max(value for _, value in clean))
        if y_min == y_max:
            y_max = y_min + 1.0
        plot_w = WIDTH - 2 * MARGIN
        plot_h = HEIGHT - 2 * MARGIN
        bar_w = max(6, plot_w / max(len(clean), 1) * 0.72)
        zero_y = HEIGHT - MARGIN - ((0 - y_min) / (y_max - y_min)) * plot_h
        svg = self._svg_header(title)
        svg += self._axes(y_min, y_max)
        for index, (label, value) in enumerate(clean):
            x = MARGIN + index * plot_w / len(clean) + (plot_w / len(clean) - bar_w) / 2
            y = HEIGHT - MARGIN - ((value - y_min) / (y_max - y_min)) * plot_h
            height = abs(zero_y - y)
            top = min(y, zero_y)
            color = COLORS[index % len(COLORS)] if value >= 0 else "#dc2626"
            svg += f'<rect x="{x:.2f}" y="{top:.2f}" width="{bar_w:.2f}" height="{height:.2f}" fill="{color}" />\n'
            svg += self._label(label[:12], x + bar_w / 2, HEIGHT - 16, "middle")
        svg += "</svg>\n"
        return self._write_artifact(prefix, chart_id, title, svg, self._png_bar(clean, title))

    def pie_chart(self, prefix: str, chart_id: str, title: str, values: dict[str, float]) -> ChartArtifact | None:
        clean = [(str(key), max(float(value), 0.0)) for key, value in values.items() if self._finite(value) and float(value) > 0]
        if not clean:
            return None
        total = sum(value for _, value in clean)
        cx, cy, radius = WIDTH / 2, HEIGHT / 2 + 8, 130
        angle = -math.pi / 2
        svg = self._svg_header(title)
        for index, (label, value) in enumerate(clean):
            sweep = (value / total) * math.tau
            x1, y1 = cx + radius * math.cos(angle), cy + radius * math.sin(angle)
            x2, y2 = cx + radius * math.cos(angle + sweep), cy + radius * math.sin(angle + sweep)
            large = 1 if sweep > math.pi else 0
            color = COLORS[index % len(COLORS)]
            svg += f'<path d="M {cx:.2f},{cy:.2f} L {x1:.2f},{y1:.2f} A {radius},{radius} 0 {large},1 {x2:.2f},{y2:.2f} Z" fill="{color}" />\n'
            svg += self._label(f"{label} {value / total:.1%}", 60, 70 + index * 22, "start", color)
            angle += sweep
        svg += "</svg>\n"
        return self._write_artifact(prefix, chart_id, title, svg, self._png_bar(dict(clean), title))

    def heatmap(self, prefix: str, chart_id: str, title: str, matrix: dict[str, dict[str, float]]) -> ChartArtifact | None:
        labels = sorted(matrix)
        if not labels:
            return None
        values = [float(matrix[row].get(col, 0.0)) for row in labels for col in labels if self._finite(matrix[row].get(col, 0.0))]
        if not values:
            return None
        v_min, v_max = min(values), max(values)
        cell = min(44, (WIDTH - 2 * MARGIN) / max(len(labels), 1), (HEIGHT - 2 * MARGIN) / max(len(labels), 1))
        svg = self._svg_header(title)
        for r, row in enumerate(labels):
            for c, col in enumerate(labels):
                value = float(matrix[row].get(col, 0.0))
                color = self._heat_color(value, v_min, v_max)
                x = MARGIN + c * cell
                y = MARGIN + r * cell
                svg += f'<rect x="{x:.2f}" y="{y:.2f}" width="{cell:.2f}" height="{cell:.2f}" fill="{color}" />\n'
            svg += self._label(row[:8], 8, MARGIN + r * cell + cell / 2, "start")
        for c, col in enumerate(labels):
            svg += self._label(col[:8], MARGIN + c * cell + cell / 2, HEIGHT - 16, "middle")
        svg += "</svg>\n"
        png_values = {f"{row}/{col}": float(matrix[row].get(col, 0.0)) for row in labels for col in labels}
        return self._write_artifact(prefix, chart_id, title, svg, self._png_bar(png_values, title))

    def dashboard(
        self,
        prefix: str,
        title: str,
        report_type: str,
        metrics: dict[str, Any],
        charts: list[ChartArtifact],
        warnings: list[str],
        notes: list[str],
    ) -> Path:
        path = self.output_dir / f"{prefix}_summary.html"
        metric_rows = "\n".join(
            f"<tr><th>{html.escape(str(key))}</th><td>{html.escape(self._format_value(value))}</td></tr>"
            for key, value in metrics.items()
        )
        chart_blocks = "\n".join(
            f"<section><h2>{html.escape(chart.title)}</h2><img src=\"{html.escape(Path(chart.svg_path).name)}\" alt=\"{html.escape(chart.title)}\"></section>"
            for chart in charts
        )
        warning_items = "".join(f"<li>{html.escape(str(warning))}</li>" for warning in warnings) or "<li>None</li>"
        note_items = "".join(f"<li>{html.escape(str(note))}</li>" for note in notes) or "<li>None</li>"
        path.write_text(
            f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 32px; color: #111827; }}
table {{ border-collapse: collapse; margin-bottom: 24px; }}
th, td {{ border: 1px solid #d1d5db; padding: 8px 12px; text-align: left; }}
section {{ margin: 28px 0; }}
img {{ max-width: 100%; border: 1px solid #e5e7eb; }}
</style>
</head>
<body>
<h1>{html.escape(title)}</h1>
<p>Report type: <strong>{html.escape(report_type)}</strong></p>
<h2>Metrics</h2>
<table>{metric_rows}</table>
<h2>Warnings</h2><ul>{warning_items}</ul>
<h2>Interpretation Notes</h2><ul>{note_items}</ul>
{chart_blocks}
</body>
</html>
""",
            encoding="utf-8",
        )
        return path

    def _write_artifact(self, prefix: str, chart_id: str, title: str, svg: str, png_bytes: bytes) -> ChartArtifact:
        svg_path = self.output_dir / f"{prefix}_{chart_id}.svg"
        png_path = self.output_dir / f"{prefix}_{chart_id}.png"
        svg_path.write_text(svg, encoding="utf-8")
        png_path.write_bytes(png_bytes)
        return ChartArtifact(chart_id=chart_id, title=title, png_path=str(png_path), svg_path=str(svg_path))

    def _svg_header(self, title: str) -> str:
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">\n'
            '<rect width="100%" height="100%" fill="#ffffff"/>\n'
            f'<text x="{WIDTH / 2}" y="28" text-anchor="middle" font-family="Arial" font-size="20" font-weight="700">{html.escape(title)}</text>\n'
        )

    def _axes(self, y_min: float, y_max: float) -> str:
        return (
            f'<line x1="{MARGIN}" y1="{HEIGHT - MARGIN}" x2="{WIDTH - MARGIN}" y2="{HEIGHT - MARGIN}" stroke="#111827"/>\n'
            f'<line x1="{MARGIN}" y1="{MARGIN}" x2="{MARGIN}" y2="{HEIGHT - MARGIN}" stroke="#111827"/>\n'
            f'{self._label(f"{y_max:.4g}", 8, MARGIN + 4, "start")}'
            f'{self._label(f"{y_min:.4g}", 8, HEIGHT - MARGIN, "start")}'
        )

    @staticmethod
    def _label(text: str, x: float, y: float, anchor: str, color: str = "#374151") -> str:
        return f'<text x="{x:.2f}" y="{y:.2f}" text-anchor="{anchor}" font-family="Arial" font-size="12" fill="{color}">{html.escape(text)}</text>\n'

    def _line_coords(self, points: list[tuple[str, float]]) -> tuple[list[tuple[float, float]], float, float]:
        values = [value for _, value in points]
        y_min, y_max = min(values), max(values)
        if y_min == y_max:
            y_min -= 1
            y_max += 1
        plot_w = WIDTH - 2 * MARGIN
        plot_h = HEIGHT - 2 * MARGIN
        coords = []
        for index, (_, value) in enumerate(points):
            x = MARGIN + (index / max(len(points) - 1, 1)) * plot_w
            y = HEIGHT - MARGIN - ((value - y_min) / (y_max - y_min)) * plot_h
            coords.append((x, y))
        return coords, y_min, y_max

    def _png_line(self, points: list[tuple[str, float]], title: str) -> bytes:
        pixels = self._blank_pixels()
        coords, _, _ = self._line_coords(points)
        self._draw_axes(pixels)
        for start, end in zip(coords, coords[1:], strict=False):
            self._draw_line(pixels, int(start[0]), int(start[1]), int(end[0]), int(end[1]), (37, 99, 235))
        return self._encode_png(pixels)

    def _png_bar(self, values: dict[str, float] | list[tuple[str, float]], title: str) -> bytes:
        clean = list(values.items()) if isinstance(values, dict) else list(values)
        clean = [(label, value) for label, value in clean if self._finite(value)]
        pixels = self._blank_pixels()
        self._draw_axes(pixels)
        if not clean:
            return self._encode_png(pixels)
        y_min = min(0.0, min(value for _, value in clean))
        y_max = max(0.0, max(value for _, value in clean))
        if y_min == y_max:
            y_max = y_min + 1.0
        plot_w = WIDTH - 2 * MARGIN
        plot_h = HEIGHT - 2 * MARGIN
        zero_y = int(HEIGHT - MARGIN - ((0 - y_min) / (y_max - y_min)) * plot_h)
        bar_w = max(2, int(plot_w / max(len(clean), 1) * 0.72))
        for index, (_, value) in enumerate(clean):
            x = int(MARGIN + index * plot_w / len(clean) + (plot_w / len(clean) - bar_w) / 2)
            y = int(HEIGHT - MARGIN - ((value - y_min) / (y_max - y_min)) * plot_h)
            color = (37, 99, 235) if value >= 0 else (220, 38, 38)
            self._fill_rect(pixels, x, min(y, zero_y), bar_w, abs(zero_y - y), color)
        return self._encode_png(pixels)

    @staticmethod
    def _clean_points(points: list[tuple[str, float]]) -> list[tuple[str, float]]:
        return [(str(label), float(value)) for label, value in points if ChartBuilder._finite(value)]

    @staticmethod
    def _finite(value: Any) -> bool:
        try:
            number = float(value)
            return math.isfinite(number)
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _heat_color(value: float, v_min: float, v_max: float) -> str:
        if v_max == v_min:
            ratio = 0.5
        else:
            ratio = (value - v_min) / (v_max - v_min)
        red = int(220 * ratio + 37 * (1 - ratio))
        blue = int(235 * (1 - ratio) + 38 * ratio)
        return f"#{red:02x}63{blue:02x}"

    @staticmethod
    def _format_value(value: Any) -> str:
        if isinstance(value, float):
            return f"{value:.6g}"
        if isinstance(value, (list, dict)):
            return html.escape(str(value))
        return str(value)

    @staticmethod
    def _blank_pixels() -> list[list[tuple[int, int, int]]]:
        return [[(255, 255, 255) for _ in range(WIDTH)] for _ in range(HEIGHT)]

    @staticmethod
    def _draw_axes(pixels: list[list[tuple[int, int, int]]]) -> None:
        ChartBuilder._draw_line(pixels, MARGIN, HEIGHT - MARGIN, WIDTH - MARGIN, HEIGHT - MARGIN, (17, 24, 39))
        ChartBuilder._draw_line(pixels, MARGIN, MARGIN, MARGIN, HEIGHT - MARGIN, (17, 24, 39))

    @staticmethod
    def _draw_line(pixels: list[list[tuple[int, int, int]]], x1: int, y1: int, x2: int, y2: int, color: tuple[int, int, int]) -> None:
        dx = abs(x2 - x1)
        dy = -abs(y2 - y1)
        sx = 1 if x1 < x2 else -1
        sy = 1 if y1 < y2 else -1
        err = dx + dy
        x, y = x1, y1
        while True:
            if 0 <= x < WIDTH and 0 <= y < HEIGHT:
                pixels[y][x] = color
            if x == x2 and y == y2:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x += sx
            if e2 <= dx:
                err += dx
                y += sy

    @staticmethod
    def _fill_rect(pixels: list[list[tuple[int, int, int]]], x: int, y: int, width: int, height: int, color: tuple[int, int, int]) -> None:
        for yy in range(max(0, y), min(HEIGHT, y + max(height, 1))):
            for xx in range(max(0, x), min(WIDTH, x + max(width, 1))):
                pixels[yy][xx] = color

    @staticmethod
    def _encode_png(pixels: list[list[tuple[int, int, int]]]) -> bytes:
        raw = bytearray()
        for row in pixels:
            raw.append(0)
            for red, green, blue in row:
                raw.extend((red, green, blue))
        def chunk(kind: bytes, data: bytes) -> bytes:
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b"")
