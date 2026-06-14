"""Parallel fold execution workers for walk-forward validation.

Module-level functions are required for ProcessPoolExecutor pickling.
"""

from __future__ import annotations

from pathlib import Path

from quant.engines.walk_forward.models import WalkForwardFoldTask, WalkForwardFold


def _count_price_rows(price_store, symbols: list[str], start: str, end: str) -> int:
    """Count unique trading days across all symbols in a date range."""
    dates = set()
    for symbol in symbols:
        history = price_store.get_price_history(symbol, start=start, end=end)
        if not history.empty and "date" in history.columns:
            dates.update(str(d) for d in history["date"])
    return len(dates)


def run_fold_worker(task: WalkForwardFoldTask) -> WalkForwardFold:
    """Execute one walk-forward fold (train + test) in a worker process."""
    import pandas as pd
    from quant.storage.sqlite_store import SQLitePriceStore
    from quant.data.fundamental.fundamental_store import FundamentalStore
    from quant.factors.price.factor_registry import FactorRegistry
    from quant.engines.backtest.backtest_engine import PortfolioBacktestEngine
    from quant.engines.factor_backtest.factor_backtest import FactorBacktest

    db_path = Path(task.db_path)
    report_dir = Path(task.report_dir)
    price_store = SQLitePriceStore(db_path)
    fundamental_store = FundamentalStore(db_path)
    factor_registry = FactorRegistry(fundamental_store)
    symbols = list(task.symbols)
    purge_days = task.purge_days
    embargo_days = task.embargo_days

    if task.strategy == "alpha":
        config = dict(task.alpha_config or {})
        config["universe"] = symbols
        if task.factor and not config.get("factor_weights") and not config.get("multi_factor"):
            config["factor_weights"] = {task.factor: 1.0}
        engine = PortfolioBacktestEngine(price_store, report_dir=report_dir)
        train = engine.run(
            start=task.train_start,
            end=task.train_end,
            initial_cash=task.initial_cash,
            strategy="alpha",
            rebalance_frequency=task.rebalance_frequency,
            alpha_config=config,
            alpha_pipeline_config=task.pipeline_config,
        )
        test = engine.run(
            start=task.test_start,
            end=task.test_end,
            initial_cash=task.initial_cash,
            strategy="alpha",
            rebalance_frequency=task.rebalance_frequency,
            alpha_config=config,
            alpha_pipeline_config=task.pipeline_config,
        )
        # Purge / embargo row counts
        effective_train_rows = _count_price_rows(price_store, symbols, task.train_start, task.train_end)
        effective_test_rows = _count_price_rows(price_store, symbols, task.test_start, task.test_end)
        raw_train_end = pd.Timestamp(task.train_end) + pd.Timedelta(days=purge_days)
        removed_by_purge = 0
        if purge_days > 0:
            purge_start = (pd.Timestamp(task.train_end) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            removed_by_purge = _count_price_rows(price_store, symbols, purge_start, raw_train_end.strftime("%Y-%m-%d"))
        removed_by_embargo = 0
        if embargo_days > 0:
            embargo_start = (raw_train_end + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            embargo_end = (pd.Timestamp(task.test_start) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            removed_by_embargo = _count_price_rows(price_store, symbols, embargo_start, embargo_end)
        fold = WalkForwardFold(
            fold=task.index,
            fold_id=f"fold_{task.index:03d}",
            train_start=task.train_start,
            train_end=task.train_end,
            test_start=task.test_start,
            test_end=task.test_end,
            train_return=train.metrics.total_return,
            test_return=test.metrics.total_return,
            train_sharpe=train.metrics.sharpe_ratio,
            test_sharpe=test.metrics.sharpe_ratio,
            train_max_drawdown=-abs(train.metrics.max_drawdown),
            test_max_drawdown=-abs(test.metrics.max_drawdown),
            ic=None,
            rank_ic=None,
            icir=None,
            turnover=test.metrics.turnover,
            cost=test.metrics.total_cost,
            train_report=train.report_path,
            test_report=test.report_path,
            no_lookahead=bool(train.no_lookahead and test.no_lookahead),
            fold_warnings=[],
            purge_days=purge_days,
            embargo_days=embargo_days,
            removed_by_purge=removed_by_purge,
            removed_by_embargo=removed_by_embargo,
            effective_train_rows=effective_train_rows,
            effective_test_rows=effective_test_rows,
        )
        return _with_fold_warnings(fold, strategy="alpha")
    else:
        backtest = FactorBacktest(price_store, fundamental_store, report_dir=report_dir)
        train = backtest.run(
            factor=task.factor,
            start=task.train_start,
            end=task.train_end,
            holding_period=task.forward_days,
            universe=symbols,
            pipeline_config=task.pipeline_config,
        )
        test = backtest.run(
            factor=task.factor,
            start=task.test_start,
            end=task.test_end,
            holding_period=task.forward_days,
            universe=symbols,
            pipeline_config=task.pipeline_config,
        )
        # Purge / embargo row counts
        effective_train_rows = _count_price_rows(price_store, symbols, task.train_start, task.train_end)
        effective_test_rows = _count_price_rows(price_store, symbols, task.test_start, task.test_end)
        raw_train_end = pd.Timestamp(task.train_end) + pd.Timedelta(days=purge_days)
        removed_by_purge = 0
        if purge_days > 0:
            purge_start = (pd.Timestamp(task.train_end) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            removed_by_purge = _count_price_rows(price_store, symbols, purge_start, raw_train_end.strftime("%Y-%m-%d"))
        removed_by_embargo = 0
        if embargo_days > 0:
            embargo_start = (raw_train_end + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            embargo_end = (pd.Timestamp(task.test_start) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            removed_by_embargo = _count_price_rows(price_store, symbols, embargo_start, embargo_end)
        fold = WalkForwardFold(
            fold=task.index,
            fold_id=f"fold_{task.index:03d}",
            train_start=task.train_start,
            train_end=task.train_end,
            test_start=task.test_start,
            test_end=task.test_end,
            train_return=train.long_short_return,
            test_return=test.long_short_return,
            train_sharpe=train.long_short_sharpe,
            test_sharpe=test.long_short_sharpe,
            train_max_drawdown=train.max_drawdown,
            test_max_drawdown=test.max_drawdown,
            ic=test.ic_mean,
            rank_ic=test.rank_ic_mean,
            icir=test.icir,
            turnover=test.turnover,
            cost=0.0,
            train_report=train.report_path,
            test_report=test.report_path,
            no_lookahead=bool(train.no_lookahead and test.no_lookahead),
            fold_warnings=[],
            purge_days=purge_days,
            embargo_days=embargo_days,
            removed_by_purge=removed_by_purge,
            removed_by_embargo=removed_by_embargo,
            effective_train_rows=effective_train_rows,
            effective_test_rows=effective_test_rows,
        )
        return _with_fold_warnings(fold, strategy="factor_long_short")


def _with_fold_warnings(fold: WalkForwardFold, strategy: str) -> WalkForwardFold:
    """Attach heuristic warnings to a completed fold result."""
    import pandas as pd

    warnings_list = list(fold.fold_warnings)
    if (
        fold.test_return is not None
        and fold.test_sharpe is not None
        and fold.test_return > 1.0
        and fold.test_sharpe < 0.5
    ):
        warnings_list.append({
            "code": "WARN_COMPOUNDED_RETURN_WEAK_SHARPE",
            "reason": (
                f"{fold.fold_id} has high compounded test return but weak arithmetic Sharpe; "
                "inspect return path stability"
            ),
        })
    if strategy == "factor_long_short" and fold.test_return is not None and fold.test_return <= -0.999999:
        warnings_list.append({
            "code": "WARN_SPREAD_RETURN_WIPEOUT",
            "reason": (
                f"{fold.fold_id} factor long-short spread compounded to about -100%; "
                "research spread returns are not cash-account equity curves"
            ),
        })
    if pd.to_datetime(fold.train_end) >= pd.to_datetime(fold.test_start):
        warnings_list.append({
            "code": "WARN_TRAIN_TEST_OVERLAP",
            "reason": f"{fold.fold_id} train_end is not before test_start",
        })
    return WalkForwardFold(
        fold=fold.fold,
        fold_id=fold.fold_id,
        train_start=fold.train_start,
        train_end=fold.train_end,
        test_start=fold.test_start,
        test_end=fold.test_end,
        train_return=fold.train_return,
        test_return=fold.test_return,
        train_sharpe=fold.train_sharpe,
        test_sharpe=fold.test_sharpe,
        train_max_drawdown=fold.train_max_drawdown,
        test_max_drawdown=fold.test_max_drawdown,
        ic=fold.ic,
        rank_ic=fold.rank_ic,
        icir=fold.icir,
        turnover=fold.turnover,
        cost=fold.cost,
        train_report=fold.train_report,
        test_report=fold.test_report,
        no_lookahead=fold.no_lookahead,
        fold_warnings=warnings_list,
        purge_days=getattr(fold, "purge_days", 0),
        embargo_days=getattr(fold, "embargo_days", 0),
        removed_by_purge=getattr(fold, "removed_by_purge", 0),
        removed_by_embargo=getattr(fold, "removed_by_embargo", 0),
        effective_train_rows=getattr(fold, "effective_train_rows", 0),
        effective_test_rows=getattr(fold, "effective_test_rows", 0),
    )


def factor_stability_worker(task: dict) -> tuple:
    """Compute factor IC for one (factor, window) pair using FactorMatrixBuilder (vectorized)."""
    from quant.storage.sqlite_store import SQLitePriceStore
    from quant.data.fundamental.fundamental_store import FundamentalStore
    from quant.factors.price.factor_registry import FactorRegistry
    from quant.factor_acceleration import FactorMatrixBuilder
    import pandas as pd

    db_path = Path(task["db_path"])
    price_store = SQLitePriceStore(db_path)
    fundamental_store = FundamentalStore(db_path)
    factor_registry = FactorRegistry(fundamental_store)
    if "higher_is_better" in task:
        higher_is_better = bool(task["higher_is_better"])
    else:
        higher_is_better = bool(factor_registry.describe(task["factor"]).higher_is_better)

    matrix = FactorMatrixBuilder(price_store, factor_registry).build(
        factor=task["factor"],
        symbols=task["symbols"],
        start=task["start"],
        end=task["end"],
        forward_days=task["forward_days"],
    )

    rows = [
        {
            "signal_date": row.signal_date,
            "symbol": row.symbol,
            "factor_value": float(row.factor_value) if higher_is_better else -float(row.factor_value),
            "future_return": row.future_return,
        }
        for row in matrix.valid_rows
    ]

    if not rows:
        return (task["factor"], task["window_idx"], None, None)

    frame = pd.DataFrame(rows)
    ic_values = []
    rank_ic_values = []
    for _, group in frame.groupby("signal_date"):
        if len(group) < 2:
            continue
        if group["factor_value"].nunique() < 2 or group["future_return"].nunique() < 2:
            continue
        ic = group["factor_value"].corr(group["future_return"])
        rank_ic = group["factor_value"].rank().corr(group["future_return"].rank())
        if pd.notna(ic):
            ic_values.append(float(ic))
        if pd.notna(rank_ic):
            rank_ic_values.append(float(rank_ic))

    mean_ic = sum(ic_values) / len(ic_values) if ic_values else None
    mean_rank_ic = sum(rank_ic_values) / len(rank_ic_values) if rank_ic_values else None
    return (task["factor"], task["window_idx"], mean_ic, mean_rank_ic)
