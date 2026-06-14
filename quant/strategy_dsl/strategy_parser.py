"""YAML/JSON parser for strategy DSL files.

The YAML parser intentionally supports the small deterministic subset used by
strategy definitions: nested mappings, lists, booleans, nulls, numbers, and
quoted or plain strings. It avoids a required PyYAML dependency for CI hygiene.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class StrategyParser:
    """Parse strategy definitions from YAML or JSON."""

    def parse_file(self, path: str | Path) -> dict[str, Any]:
        source = Path(path)
        try:
            text = source.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise ValueError(f"strategy file not found: {source}") from exc
        suffix = source.suffix.lower()
        if suffix == ".json":
            return self._parse_json(text, source)
        if suffix in {".yaml", ".yml"}:
            return self.parse_yaml(text)
        raise ValueError("strategy file must be YAML or JSON")

    @staticmethod
    def _parse_json(text: str, source: Path) -> dict[str, Any]:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"strategy JSON is invalid: {source}") from exc
        if not isinstance(payload, dict):
            raise ValueError("strategy JSON must contain an object")
        return payload

    def parse_yaml(self, text: str) -> dict[str, Any]:
        lines = self._lines(text)
        if not lines:
            return {}
        value, index = self._parse_block(lines, 0, lines[0][0])
        if index != len(lines):
            raise ValueError("strategy YAML contains inconsistent indentation")
        if not isinstance(value, dict):
            raise ValueError("strategy YAML must contain a mapping")
        return value

    @staticmethod
    def _lines(text: str) -> list[tuple[int, str]]:
        output = []
        for line_number, raw in enumerate(text.splitlines(), start=1):
            stripped = StrategyParser._strip_comment(raw, line_number).rstrip()
            if not stripped.strip():
                continue
            indent = len(stripped) - len(stripped.lstrip(" "))
            output.append((indent, stripped.lstrip()))
        return output

    @staticmethod
    def _strip_comment(raw: str, line_number: int) -> str:
        quote: str | None = None
        escaped = False
        for index, char in enumerate(raw):
            if escaped:
                escaped = False
                continue
            if char == "\\" and quote == '"':
                escaped = True
                continue
            if char in {"'", '"'}:
                if quote is None:
                    quote = char
                elif quote == char:
                    quote = None
                continue
            if char == "#" and quote is None:
                return raw[:index]
        if quote is not None:
            raise ValueError(f"strategy YAML contains an unterminated quote on line {line_number}")
        return raw

    def _parse_block(self, lines: list[tuple[int, str]], index: int, indent: int):
        if index >= len(lines):
            return {}, index
        current_indent, content = lines[index]
        if current_indent != indent:
            raise ValueError("strategy YAML contains inconsistent indentation")
        if content.startswith("- "):
            return self._parse_list(lines, index, indent)
        return self._parse_mapping(lines, index, indent)

    def _parse_mapping(self, lines: list[tuple[int, str]], index: int, indent: int):
        output: dict[str, Any] = {}
        while index < len(lines):
            current_indent, content = lines[index]
            if current_indent < indent:
                break
            if current_indent > indent:
                raise ValueError("strategy YAML contains unexpected indentation")
            if content.startswith("- "):
                break
            key, value = self._split_key_value(content)
            index += 1
            if value == "":
                if index < len(lines) and lines[index][0] > current_indent:
                    nested, index = self._parse_block(lines, index, lines[index][0])
                    output[key] = nested
                else:
                    output[key] = {}
            else:
                output[key] = self._parse_scalar(value)
        return output, index

    def _parse_list(self, lines: list[tuple[int, str]], index: int, indent: int):
        output: list[Any] = []
        while index < len(lines):
            current_indent, content = lines[index]
            if current_indent < indent:
                break
            if current_indent != indent or not content.startswith("- "):
                break
            rest = content[2:].strip()
            index += 1
            if not rest:
                if index < len(lines) and lines[index][0] > current_indent:
                    item, index = self._parse_block(lines, index, lines[index][0])
                else:
                    item = None
            elif self._looks_like_inline_mapping_item(rest):
                key, value = self._split_key_value(rest)
                item = {key: self._parse_scalar(value)} if value else {key: {}}
                if index < len(lines) and lines[index][0] > current_indent:
                    nested, index = self._parse_block(lines, index, lines[index][0])
                    if isinstance(nested, dict):
                        item.update(nested)
                    else:
                        item[key] = nested
            elif ":" in rest and not rest.startswith(("'", '"')):
                raise ValueError(f"strategy YAML list item contains an unsupported ':' scalar: {rest}")
            else:
                item = self._parse_scalar(rest)
            output.append(item)
        return output, index

    @staticmethod
    def _looks_like_inline_mapping_item(rest: str) -> bool:
        if rest.startswith(("'", '"')) or ":" not in rest:
            return False
        key, _, value = rest.partition(":")
        return key.strip() == "name" and (value == "" or value.startswith(" "))

    @staticmethod
    def _split_key_value(content: str) -> tuple[str, str]:
        if ":" not in content:
            raise ValueError(f"strategy YAML line is missing ':': {content}")
        key, value = content.split(":", 1)
        key = key.strip()
        if not key:
            raise ValueError("strategy YAML contains an empty key")
        return key, value.strip()

    @staticmethod
    def _parse_scalar(value: str) -> Any:
        text = value.strip()
        if text == "":
            return ""
        if text.startswith(("[", "{")) or text.endswith(("]", "}")):
            raise ValueError(f"strategy YAML inline collections are not supported: {text}")
        if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
            return text[1:-1]
        lowered = text.lower()
        if lowered in {"true", "false"}:
            return lowered == "true"
        if lowered in {"null", "none"}:
            return None
        try:
            if any(char in text for char in (".", "e", "E")):
                return float(text)
            return int(text)
        except ValueError:
            return text
