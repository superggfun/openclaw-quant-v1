"""Load strategy DSL definitions from files or registry names."""

from __future__ import annotations

from pathlib import Path

from quant.strategy_dsl.strategy_definition import StrategyDefinition
from quant.strategy_dsl.strategy_parser import StrategyParser


class StrategyLoader:
    """Resolve strategy names and files from a strategy directory."""

    def __init__(self, strategy_dir: str | Path = "strategies") -> None:
        self.strategy_dir = Path(strategy_dir)
        self.parser = StrategyParser()

    def list_files(self) -> list[Path]:
        if not self.strategy_dir.exists():
            return []
        files = []
        for suffix in ("*.yaml", "*.yml", "*.json"):
            files.extend(self.strategy_dir.glob(suffix))
        return sorted(files, key=lambda path: path.name)

    def load_file(self, path: str | Path) -> StrategyDefinition:
        payload = self.parser.parse_file(path)
        return StrategyDefinition.from_mapping(payload)

    def load_name(self, name: str) -> tuple[StrategyDefinition, Path]:
        normalized = self.normalize_name(name)
        for path in self.list_files():
            if path.stem == normalized:
                return self.load_file(path), path
            try:
                definition = self.load_file(path)
            except ValueError:
                continue
            if self.normalize_name(definition.name) == normalized:
                return definition, path
        raise ValueError(f"strategy not found: {name}")

    @staticmethod
    def normalize_name(name: str) -> str:
        return str(name).strip().lower().replace(" ", "_")
