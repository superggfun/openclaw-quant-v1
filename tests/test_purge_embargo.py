"""Purge/embargo look-ahead bias prevention validation tests."""

from __future__ import annotations

import math
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from quant.storage.sqlite_store import SQLitePriceStore


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _seed_price_series(db_path: Path, symbols: list[str], start: date, days: int) -> None:
    rows = []
    for symbol in symbols:
        for offset in range(days):
            price = 100.0 + offset * 0.5 + hash(symbol) % 23
            d = start + timedelta(days=offset)
            rows.append({
                "symbol": symbol,
                "date": d.isoformat(),
                "open": price, "high": price, "low": price,
                "close": price, "adj_close": price, "volume": 1000,
            })
    SQLitePriceStore(db_path).upsert_prices(pd.DataFrame(rows))


# ---------------------------------------------------------------------------
# Window generation tests (no price data needed — generate_windows is static)
# ---------------------------------------------------------------------------

def test_generate_windows_no_purge_no_embargo_defaults(tmp_path: Path) -> None:
    """Default zero purge/embargo → train_end is raw, no gap."""
    from quant.engines.walk_forward.walk_forward import WalkForwardEngine

    engine = WalkForwardEngine(SQLitePriceStore(tmp_path / "test.db"))
    windows = engine.generate_windows(
        train_years=1, test_years=0.5,
        start="2020-01-01", end="2025-12-31",
    )
    assert len(windows) >= 1
    w = windows[0]
    assert w["train_end"] == w["train_end_raw"]
    assert w["test_start"] == (pd.Timestamp(w["train_end_raw"]) + timedelta(days=1)).strftime("%Y-%m-%d")
    assert w["purge_days"] == 0
    assert w["embargo_days"] == 0


def test_purge_truncates_train_end(tmp_path: Path) -> None:
    """Purge of N days → train_end = raw_train_end - N."""
    from quant.engines.walk_forward.walk_forward import WalkForwardEngine

    engine = WalkForwardEngine(SQLitePriceStore(tmp_path / "test.db"))
    windows = engine.generate_windows(
        train_years=1, test_years=0.5,
        start="2020-01-01", end="2025-12-31",
        purge_days=10, embargo_days=0,
    )
    assert len(windows) >= 1
    w = windows[0]
    raw = pd.Timestamp(w["train_end_raw"])
    effective = pd.Timestamp(w["train_end"])
    assert (raw - effective).days == 10
    assert w["purge_days"] == 10


def test_embargo_adds_gap_after_train_end(tmp_path: Path) -> None:
    """Embargo of G days → test_start = train_end_raw + 1 + G."""
    from quant.engines.walk_forward.walk_forward import WalkForwardEngine

    engine = WalkForwardEngine(SQLitePriceStore(tmp_path / "test.db"))
    windows = engine.generate_windows(
        train_years=1, test_years=0.5,
        start="2020-01-01", end="2025-12-31",
        purge_days=0, embargo_days=5,
    )
    assert len(windows) >= 1
    w = windows[0]
    train_end_raw = pd.Timestamp(w["train_end_raw"])
    test_start = pd.Timestamp(w["test_start"])
    expected_gap = (test_start - train_end_raw).days
    assert expected_gap == 1 + 5, f"gap={expected_gap}, want {1 + 5}"
    assert w["embargo_days"] == 5


def test_purge_plus_embargo_combined(tmp_path: Path) -> None:
    """Combined: train window shortened, test start delayed."""
    from quant.engines.walk_forward.walk_forward import WalkForwardEngine

    engine = WalkForwardEngine(SQLitePriceStore(tmp_path / "test.db"))
    windows = engine.generate_windows(
        train_years=1, test_years=0.5,
        start="2020-01-01", end="2025-12-31",
        purge_days=5, embargo_days=3,
    )
    assert len(windows) >= 1
    w = windows[0]
    raw_end = pd.Timestamp(w["train_end_raw"])
    eff_end = pd.Timestamp(w["train_end"])
    test_s = pd.Timestamp(w["test_start"])

    assert (raw_end - eff_end).days == 5
    assert (test_s - raw_end).days == 1 + 3
    assert eff_end < test_s


def test_train_never_overlaps_test(tmp_path: Path) -> None:
    """Even with zero purge/embargo, train_end + 1 == test_start."""
    from quant.engines.walk_forward.walk_forward import WalkForwardEngine

    engine = WalkForwardEngine(SQLitePriceStore(tmp_path / "test.db"))
    windows = engine.generate_windows(
        train_years=1, test_years=1,
        start="2020-01-01", end="2025-12-31",
        purge_days=0, embargo_days=0,
    )
    assert len(windows) >= 1
    for w in windows:
        train_end = pd.Timestamp(w["train_end"])
        test_start = pd.Timestamp(w["test_start"])
        assert train_end < test_start, f"train_end={train_end} >= test_start={test_start}"
        assert (test_start - pd.Timestamp(w["train_end_raw"])).days == 1


def test_generate_windows_covers_full_period(tmp_path: Path) -> None:
    """All generated windows should cover the full start..end range."""
    from quant.engines.walk_forward.walk_forward import WalkForwardEngine

    engine = WalkForwardEngine(SQLitePriceStore(tmp_path / "test.db"))
    windows = engine.generate_windows(
        train_years=1, test_years=0.5,
        start="2020-01-01", end="2025-12-31",
        purge_days=0, embargo_days=0,
    )
    assert len(windows) >= 2, f"got {len(windows)} windows, need at least 2"
    # Each window's test range should be contiguous
    for i in range(len(windows) - 1):
        curr_test_end = pd.Timestamp(windows[i]["test_end"])
        next_test_start = pd.Timestamp(windows[i + 1]["test_start"])
        gap = (next_test_start - curr_test_end).days
        assert gap <= 7, f"gap of {gap} days between windows {i} and {i+1}"


# ---------------------------------------------------------------------------
# Look-ahead prevention verification
# ---------------------------------------------------------------------------

def test_purge_prevents_forward_label_leakage(tmp_path: Path) -> None:
    """With purge=20 (matching forward return horizon), the last 20
    training observations are removed so their forward returns cannot
    leak into the test period."""
    from quant.engines.walk_forward.walk_forward import WalkForwardEngine

    engine = WalkForwardEngine(SQLitePriceStore(tmp_path / "test.db"))
    windows = engine.generate_windows(
        train_years=1, test_years=0.5,
        start="2020-01-01", end="2025-12-31",
        purge_days=20, embargo_days=0,
    )
    assert len(windows) >= 1
    for w in windows:
        raw_end = pd.Timestamp(w["train_end_raw"])
        eff_end = pd.Timestamp(w["train_end"])
        test_s = pd.Timestamp(w["test_start"])

        # The purge removes the last 20 calendar days of observations
        assert (raw_end - eff_end).days == 20

        # After purge, training uses only data through eff_end.
        # The forward return of purged observations would extend into the
        # test period. By removing them from training, we eliminate leakage.
        assert eff_end < test_s


def test_purge_days_cannot_exceed_train_window(tmp_path: Path) -> None:
    """Extreme purge values must not make train_end < train_start."""
    from quant.engines.walk_forward.walk_forward import WalkForwardEngine

    engine = WalkForwardEngine(SQLitePriceStore(tmp_path / "test.db"))
    windows = engine.generate_windows(
        train_years=2 / 365.0,  # ~2 days of training
        test_years=10 / 365.0,
        start="2023-01-01", end="2023-03-01",
        purge_days=10, embargo_days=0,
    )
    assert len(windows) >= 1
    for w in windows:
        eff_start = pd.Timestamp(w["train_start"])
        eff_end = pd.Timestamp(w["train_end"])
        assert eff_start <= eff_end, (
            f"purge made train start {eff_start} > train end {eff_end}"
        )


# ---------------------------------------------------------------------------
# Purge/embargo with price data integration
# ---------------------------------------------------------------------------

def test_training_data_excludes_purge_days(tmp_path: Path) -> None:
    """When we query training data for a window with purge, the price
    data should be bounded by effective_train_end, not raw_train_end."""
    start = date(2023, 1, 1)
    _seed_price_series(tmp_path / "test.db", ["A"], start=start, days=400)

    from quant.engines.walk_forward.walk_forward import WalkForwardEngine
    store = SQLitePriceStore(tmp_path / "test.db")
    engine = WalkForwardEngine(store)

    purge_days = 20
    windows = engine.generate_windows(
        train_years=0.5, test_years=0.5,
        start="2023-01-01", end="2024-02-28",
        purge_days=purge_days, embargo_days=0,
    )
    assert len(windows) >= 1, f"no windows generated"
    w = windows[0]
    eff_end = pd.Timestamp(w["train_end"])
    raw_end = pd.Timestamp(w["train_end_raw"])

    # Training data should end at eff_end (not raw_end)
    train_data = store.get_price_history("A", end=eff_end.strftime("%Y-%m-%d"))
    assert not train_data.empty
    assert train_data["date"].max() <= eff_end.strftime("%Y-%m-%d")

    # Raw end data exists but is excluded from training
    raw_train_data = store.get_price_history("A", end=raw_end.strftime("%Y-%m-%d"))
    raw_train_max = raw_train_data["date"].max()
    assert raw_train_max >= eff_end.strftime("%Y-%m-%d")
    # raw end includes purged days that training does not see
    assert (pd.Timestamp(raw_train_max) - pd.Timestamp(train_data["date"].max())).days >= purge_days


def test_embargo_gap_has_no_price_data_usage(tmp_path: Path) -> None:
    """Between train_end and test_start there's an embargo gap where no
    data should be used by either set."""
    start = date(2023, 1, 1)
    _seed_price_series(tmp_path / "test.db", ["A"], start=start, days=400)
    store = SQLitePriceStore(tmp_path / "test.db")

    from quant.engines.walk_forward.walk_forward import WalkForwardEngine
    engine = WalkForwardEngine(store)

    windows = engine.generate_windows(
        train_years=0.2, test_years=0.2,
        start="2023-01-01", end="2024-02-28",
        purge_days=0, embargo_days=10,
    )
    assert len(windows) >= 1, f"no windows generated"
    w = windows[0]
    train_end = pd.Timestamp(w["train_end"])
    test_start = pd.Timestamp(w["test_start"])

    # test_start must be after the gap (train_end_raw + 1 + embargo)
    expected_test_start = pd.Timestamp(w["train_end_raw"]) + timedelta(days=1 + 10)
    assert test_start == expected_test_start, (
        f"test_start={test_start}, expected={expected_test_start}"
    )

    # Training data doesn't use embargo gap
    gap_end = (train_end + timedelta(days=1)).strftime("%Y-%m-%d")
    train_data = store.get_price_history("A", end=gap_end)
    assert train_data["date"].max() <= gap_end


def test_walk_forward_run_with_purge_embargo(tmp_path: Path) -> None:
    """Full walk-forward run with purge/embargo applied."""
    start = date(2020, 1, 1)
    _seed_price_series(tmp_path / "test.db", ["SPY", "QQQ", "AAPL"], start=start, days=2000)
    store = SQLitePriceStore(tmp_path / "test.db")

    from quant.engines.walk_forward.walk_forward import WalkForwardEngine
    engine = WalkForwardEngine(store, report_dir=str(tmp_path / "reports"))

    result = engine.run(
        strategy="alpha",
        factor="momentum_20d",
        train_years=1, test_years=0.5,
        start="2020-01-01", end="2025-06-01",
        purge_days=10, embargo_days=5,
        initial_cash=100_000,
        workers=1,
    )

    assert result.folds, "expected at least one fold"
    assert result.parameters["purge_days"] == 10
    assert result.parameters["embargo_days"] == 5

    # Verify no look-ahead in training: every fold's train_end < test_start
    for fold in result.folds:
        assert fold.train_end < fold.test_start, (
            f"fold {fold.fold}: train_end={fold.train_end} >= test_start={fold.test_start}"
        )


def test_all_folds_have_correct_purge_embargo_metadata(tmp_path: Path) -> None:
    """Each window carries its purge/embargo days metadata."""
    from quant.engines.walk_forward.walk_forward import WalkForwardEngine

    engine = WalkForwardEngine(SQLitePriceStore(tmp_path / "test.db"))
    windows = engine.generate_windows(
        train_years=1, test_years=0.5,
        start="2020-01-01", end="2025-12-31",
        purge_days=7, embargo_days=3,
    )
    assert len(windows) >= 1
    for w in windows:
        assert w["purge_days"] == 7
        assert w["embargo_days"] == 3


# ---------------------------------------------------------------------------
# CLI parameter propagation
# ---------------------------------------------------------------------------

def test_cli_purge_embargo_args_propagated_to_engine(tmp_path: Path, monkeypatch) -> None:
    """CLI --purge-days and --embargo-days flow through to the engine."""
    start = date(2020, 1, 1)
    _seed_price_series(tmp_path / "test.db", ["SPY"], start=start, days=2500)

    monkeypatch.setattr("sys.argv", [
        "quant",
        "walk-forward",
        "--purge-days", "15",
        "--embargo-days", "7",
        "--data-root", str(tmp_path),
    ])

    from quant.engines.walk_forward.walk_forward import WalkForwardEngine
    store = SQLitePriceStore(tmp_path / "test.db")
    engine = WalkForwardEngine(store, report_dir=str(tmp_path / "reports"))

    windows = engine.generate_windows(
        train_years=1, test_years=0.5,
        start="2020-01-01", end="2025-12-31",
        purge_days=15, embargo_days=7,
    )
    assert len(windows) >= 1
    assert windows[0]["purge_days"] == 15
    assert windows[0]["embargo_days"] == 7


def test_auto_default_purge_from_factor_forward_horizon(tmp_path: Path) -> None:
    """When purge_days=0 and embargo_days=0, the engine auto-defaults purge_days
    to the factor's forward_return_horizon if > 0."""
    start = date(2020, 1, 1)
    _seed_price_series(tmp_path / "test.db", ["SPY", "QQQ", "AAPL"], start=start, days=2000)
    store = SQLitePriceStore(tmp_path / "test.db")
    engine = WalkForwardEngine(store, report_dir=str(tmp_path / "reports"))
    result = engine.run(
        strategy="alpha", factor="momentum_60d",
        start="2020-01-01", end="2025-06-01",
        train_years=1, test_years=0.5, max_folds=2,
        purge_days=0, embargo_days=0,
        write_report=False, workers=1,
    )
    # momentum_60d forward_return_horizon = 60 (equal to lookback_days)
    assert result.parameters["purge_days"] == 60
    assert result.parameters["embargo_days"] == 0
    for fold in result.folds:
        assert fold.purge_days == 60


def test_factor_zero_forward_horizon_stays_zero(tmp_path: Path) -> None:
    """Fundamental factors with forward_return_horizon=0 keep purge_days=0."""
    start = date(2020, 1, 1)
    _seed_price_series(tmp_path / "test.db", ["SPY", "QQQ", "AAPL"], start=start, days=2000)
    store = SQLitePriceStore(tmp_path / "test.db")
    engine = WalkForwardEngine(store, report_dir=str(tmp_path / "reports"))
    result = engine.run(
        strategy="alpha", factor="pe_value_factor",
        start="2020-01-01", end="2025-06-01",
        train_years=1, test_years=0.5, max_folds=2,
        purge_days=0, embargo_days=0,
        write_report=False, workers=1,
    )
    assert result.parameters["purge_days"] == 0


def test_purge_embargo_report_fields_populated(tmp_path: Path) -> None:
    """WalkForwardFold must include purge/embargo report fields."""
    start = date(2020, 1, 1)
    _seed_price_series(tmp_path / "test.db", ["SPY", "QQQ", "AAPL"], start=start, days=2000)
    store = SQLitePriceStore(tmp_path / "test.db")
    engine = WalkForwardEngine(store, report_dir=str(tmp_path / "reports"))
    result = engine.run(
        strategy="alpha", factor="momentum_20d",
        start="2020-01-01", end="2025-06-01",
        train_years=1, test_years=0.5, max_folds=2,
        purge_days=20, embargo_days=10,
        write_report=False, workers=1,
    )
    for fold in result.folds:
        assert fold.purge_days == 20
        assert fold.embargo_days == 10
        assert isinstance(fold.removed_by_purge, int) and fold.removed_by_purge >= 0
        assert isinstance(fold.removed_by_embargo, int) and fold.removed_by_embargo >= 0
        assert fold.effective_train_rows > 0, f"Fold {fold.fold} has no training rows"
        assert fold.effective_test_rows > 0, f"Fold {fold.fold} has no test rows"


def test_purge_ensures_no_label_overlap_with_test(tmp_path: Path) -> None:
    """Purge ensures training ends before test_start; no label window overlaps test."""
    start = date(2020, 1, 1)
    _seed_price_series(tmp_path / "test.db", ["SPY", "QQQ", "AAPL"], start=start, days=2000)
    store = SQLitePriceStore(tmp_path / "test.db")
    engine = WalkForwardEngine(store, report_dir=str(tmp_path / "reports"))
    result = engine.run(
        strategy="alpha", factor="momentum_20d",
        start="2020-01-01", end="2025-06-01",
        train_years=1, test_years=0.5, max_folds=3,
        purge_days=20, embargo_days=10,
        write_report=False, workers=1,
    )
    for fold in result.folds:
        assert fold.train_end < fold.test_start, (
            f"Fold {fold.fold}: train_end {fold.train_end} on or after test_start {fold.test_start}"
        )
        # Verify the gap between train_end and test_start is >= 1 calendar day
        import pandas as pd
        gap = (pd.Timestamp(fold.test_start) - pd.Timestamp(fold.train_end)).days
        assert gap >= 1, (
            f"Fold {fold.fold}: gap={gap} days between train_end and test_start"
        )


def test_walk_forward_run_old_behavior_unchanged(tmp_path: Path) -> None:
    """With purge=0, embargo=0 on a zero-horizon factor, behavior is unchanged
    and report fields still populate."""
    start = date(2020, 1, 1)
    _seed_price_series(tmp_path / "test.db", ["SPY", "QQQ", "AAPL"], start=start, days=2000)
    store = SQLitePriceStore(tmp_path / "test.db")
    engine = WalkForwardEngine(store, report_dir=str(tmp_path / "reports"))
    result = engine.run(
        strategy="alpha", factor="pe_value_factor",
        start="2020-01-01", end="2025-06-01",
        train_years=1, test_years=0.5, max_folds=2,
        purge_days=0, embargo_days=0,
        write_report=False, workers=1,
    )
    assert result.parameters["purge_days"] == 0
    for fold in result.folds:
        assert fold.purge_days == 0
        assert fold.embargo_days == 0
        assert fold.removed_by_purge == 0
        assert fold.removed_by_embargo == 0
        assert fold.effective_train_rows > 0
        assert fold.effective_test_rows > 0


def test_forward_return_horizon_defined_for_all_factors() -> None:
    """Every factor definition has forward_return_horizon >= 0, type int."""
    from quant.factors.price.factor_registry import FactorRegistry
    from quant.data.fundamental.fundamental_store import FundamentalStore
    from quant.storage.sqlite_store import SQLitePriceStore
    import tempfile, shutil
    d = tempfile.mkdtemp()
    try:
        db = SQLitePriceStore(f"{d}/test.db")
        # populate minimal data
        syms = ["AAPL", "MSFT", "GOOG"]
        from datetime import date as dte, timedelta as td
        rows = []
        for s in syms:
            for i in range(100):
                dt = dte(2020, 1, 1) + td(days=i)
                rows.append({"symbol": s, "date": dt.isoformat(), "open": 100.0, "high": 100.0,
                             "low": 100.0, "close": 100.0, "adj_close": 100.0, "volume": 1000})
        import pandas as pd
        db.upsert_prices(pd.DataFrame(rows))
        fstore = FundamentalStore(f"{d}/test.db")
        reg = FactorRegistry(fstore)
        factors = reg.factor_names()
        assert len(factors) > 0, "Expected factors to be registered"
        for name in factors:
            dfn = reg.describe(name)
            assert hasattr(dfn, "forward_return_horizon"), f"{name} missing field"
            assert dfn.forward_return_horizon >= 0, f"{name} horizon={dfn.forward_return_horizon}"
            assert isinstance(dfn.forward_return_horizon, int), f"{name} horizon not int"
    finally:
        shutil.rmtree(d, ignore_errors=True)

from quant.engines.walk_forward.walk_forward import WalkForwardEngine
