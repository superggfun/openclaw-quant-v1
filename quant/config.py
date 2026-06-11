"""Project configuration defaults."""

from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv("OPENCLAW_QUANT_DATA_DIR", PROJECT_ROOT / "data"))
DB_PATH = Path(os.getenv("OPENCLAW_QUANT_DB_PATH", DATA_DIR / "quant.db"))

DEFAULT_SYMBOLS = (
    "SPY",
    "QQQ",
    "NVDA",
    "AAPL",
    "MSFT",
    "TSLA",
    "AMD",
    "META",
    "GOOGL",
    "TLT",
    "GLD",
)

DEFAULT_START_DATE = os.getenv("OPENCLAW_QUANT_START_DATE", "1990-01-01")

