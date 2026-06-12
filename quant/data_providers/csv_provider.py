"""Local CSV data provider for offline imports and tests."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from quant.data_providers.base import DataProvider, ProviderHealth, empty_price_frame, normalize_price_frame


class CSVProvider(DataProvider):
    name = "csv"
    description = "Local CSV OHLCV provider"
    status = "available"

    def __init__(self, csv_path: str | Path | None = None, csv_dir: str | Path | None = None) -> None:
        self.csv_path = Path(csv_path) if csv_path else None
        self.csv_dir = Path(csv_dir) if csv_dir else Path("data/csv")

    def get_price_history(
        self,
        symbol: str,
        start: str | date | None = None,
        end: str | date | None = None,
    ) -> pd.DataFrame:
        ticker = symbol.upper().strip()
        frame = self._load_frame(ticker)
        if frame.empty:
            return frame
        if start:
            frame = frame[frame["date"] >= str(start)]
        if end:
            frame = frame[frame["date"] <= str(end)]
        return frame.sort_values("date").reset_index(drop=True)

    def health_check(self) -> ProviderHealth:
        if self.csv_path and self.csv_path.exists():
            return ProviderHealth(self.name, True, "PASS", messages=(f"csv_path={self.csv_path}",))
        if self.csv_dir.exists():
            return ProviderHealth(self.name, True, "PASS", messages=(f"csv_dir={self.csv_dir}",))
        return ProviderHealth(
            self.name,
            False,
            "WARNING",
            warning="no CSV path found",
            messages=(f"expected csv_dir={self.csv_dir}",),
        )

    def _load_frame(self, symbol: str) -> pd.DataFrame:
        paths = []
        if self.csv_path:
            paths.append(self.csv_path)
        paths.append(self.csv_dir / f"{symbol}.csv")
        paths.append(self.csv_dir / "prices.csv")
        for path in paths:
            if not path.exists():
                continue
            raw = pd.read_csv(path)
            frame = normalize_price_frame(raw, symbol=symbol)
            if "symbol" in frame.columns:
                frame = frame[frame["symbol"].str.upper() == symbol]
            return frame
        return empty_price_frame()
