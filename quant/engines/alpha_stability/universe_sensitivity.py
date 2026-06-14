"""Universe Sensitivity Analysis module.

Tests how factor performance changes across different universe sizes.

With bulk_matrix=True, FactorMatrixBuilder chooses the research data
provider: InMemory/COW on fork-capable platforms, single-process InMemory
on spawn platforms, and SQLite fallback when needed.

With bulk_matrix=False, the legacy module-level price cache is used only
on fork-capable platforms. Spawn platforms fall back safely without
passing large price DataFrames between workers.
"""

from __future__ import annotations

import shutil
import time
import uuid
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from quant.config import DEFAULT_SYMBOLS
from quant.core.symbols import normalize_symbols
from quant.engines.factor_backtest.factor_backtest import FactorBacktest, FactorBacktestResult
from quant.engines.alpha_stability.models import AuditModuleResult
from quant.storage.sqlite_store import SQLitePriceStore
from quant.data.fundamental.fundamental_store import FundamentalStore

DEFAULT_UNIVERSE_SIZES = [20, 50, 100, 200, 500]
_SHM_DIR = Path("/dev/shm")

# ------------------------------------------------------------------ #
#  Module-level price cache — populated by parent, shared via COW     #
# ------------------------------------------------------------------ #

_price_cache: dict[str, pd.DataFrame] | None = None
"""Full price histories loaded once by the parent before ProcessPoolExecutor fork.
After fork(), child processes share the same physical pages via COW.
DO NOT mutate DataFrames from this cache — take a .copy() first."""


class _PriceCachedBacktest(FactorBacktest):
    """FactorBacktest that reads price histories from _price_cache.

    This avoids all SQLite reads during the backtest computation path.
    The base-class SQLitePriceStore is still created (for FundamentalStore
    metadata lookups) but is never queried for price data.
    """

    def _price_histories(self, symbols: list[str]) -> dict[str, pd.DataFrame]:
        """Return price DataFrames from the pre-loaded module cache when available.

        Each DataFrame is .copy()'ed so mutations (sort / reset_index / dropna)
        in the observation pipeline don't trigger COW page faults back into
        the shared cache.
        """
        if _price_cache is None:
            return super()._price_histories(symbols)
        result: dict[str, pd.DataFrame] = {}
        for symbol in symbols:
            df = _price_cache.get(symbol)
            if df is None or df.empty:
                continue
            result[symbol] = df.copy()
        return result


# ------------------------------------------------------------------ #
#  Worker (module-level → picklable for ProcessPoolExecutor)          #
# ------------------------------------------------------------------ #


def _backtest_universe_size(
    db_path: str,
    factor: str,
    size: int,
    symbols: list[str],
    start: str | None,
    end: str | None,
    holding_period: int,
    quantiles: int,
    bulk_matrix: bool,
    matrix_workers: int,
) -> dict:
    """Process worker: backtest for one universe size.

    When bulk_matrix=False, price data comes from the legacy COW cache on
    fork-capable platforms. When bulk_matrix=True, FactorMatrixBuilder owns
    provider selection and fallback.
    """
    try:
        price_store = SQLitePriceStore(Path(db_path))
        engine = _PriceCachedBacktest(price_store, None)
        universe_slice = symbols[:size]
        result: FactorBacktestResult = engine.run(
            factor=factor,
            start=start,
            end=end,
            holding_period=holding_period,
            quantiles=quantiles,
            universe=universe_slice,
            bulk_matrix=bulk_matrix,
            max_workers=matrix_workers,
            write_report=False,
        )
        return {
            "size": size,
            "actual_size": len(universe_slice),
            "long_short_return": result.long_short_return,
            "sharpe": result.sharpe,
            "max_drawdown": result.max_drawdown,
            "turnover": result.turnover,
        }
    except Exception as e:
        return {
            "size": size,
            "actual_size": min(len(symbols), size),
            "long_short_return": None,
            "sharpe": None,
            "max_drawdown": None,
            "turnover": None,
            "error": str(e),
        }


# ------------------------------------------------------------------ #
#  Data classes                                                        #
# ------------------------------------------------------------------ #


@dataclass(frozen=True)
class UniverseSizeResult:
    """Metrics for a single universe slice."""
    size: int
    actual_size: int
    long_short_return: float | None
    sharpe: float | None
    max_drawdown: float | None
    turnover: float | None


# ------------------------------------------------------------------ #
#  Public entry point                                                  #
# ------------------------------------------------------------------ #


def run_universe_sensitivity(
    factor: str,
    price_store: SQLitePriceStore,
    fundamental_store: FundamentalStore | None = None,
    *,
    universe_sizes: list[int] | None = None,
    symbols: list[str] | None = None,
    start: str | None = None,
    end: str | None = None,
    holding_period: int = 20,
    quantiles: int = 5,
    max_workers: int | None = None,
    bulk_matrix: bool = True,
    matrix_workers: int = 1,
) -> AuditModuleResult:
    """Run *factor* across multiple universe slices and report stability.

    With ``bulk_matrix=True`` (default), FactorMatrixBuilder chooses the
    provider: InMemory/COW on fork-capable platforms, single-process
    InMemory on spawn platforms, and SQLite fallback when needed.

    With ``bulk_matrix=False``, the legacy COW price cache is used only on
    fork-capable platforms. Spawn platforms fall back safely.

    ``max_workers`` controls outer parallelism (universe sizes in parallel).
    ``matrix_workers`` controls per-backtest inner parallelism (matrix build).
    Default: ``matrix_workers=1`` to avoid over-parallelism when outer workers
    already saturate cores.
    """

    sizes = universe_sizes or DEFAULT_UNIVERSE_SIZES
    full_universe = normalize_symbols(symbols or DEFAULT_SYMBOLS)

    valid_sizes = [s for s in sizes if len(full_universe[:s]) >= 3]
    if not valid_sizes:
        return AuditModuleResult(
            module="universe_sensitivity",
            status="fail",
            score=0.0,
            details={"factor": factor, "universe_sizes": sizes, "results": []},
            warnings=["no valid universe size with >= 3 symbols"],
        )

    size_results: list[dict] = []
    sharpe_values: list[float] = []
    workers = max_workers if max_workers is not None else min(len(valid_sizes), 8)

    # Step 1: optional legacy price preload for the non-bulk path.
    # With bulk_matrix=True, FactorMatrixBuilder owns provider selection.
    global _price_cache
    if not bulk_matrix:
        t0 = time.perf_counter()
        _price_cache = price_store.get_price_history_many(full_universe)
        load_sec = time.perf_counter() - t0
        cache_sym_count = len(_price_cache)
        cache_rows = sum(len(df) for df in _price_cache.values())
        print(
            f"[universe_sensitivity] pre-loaded {cache_rows} rows / "
            f"{cache_sym_count} symbols in {load_sec:.1f}s"
        )
    else:
        load_sec = 0.0
        cache_sym_count = 0
        cache_rows = 0

    # ── Step 2: copy DB to /dev/shm (for FundamentalStore only) ──────── #
    src_db = str(price_store.db_path)
    db_size_mb = Path(src_db).stat().st_size / (1024 * 1024)

    if _SHM_DIR.exists() and db_size_mb < 1000:
        shm_db = str(_SHM_DIR / f"quant_audit_{uuid.uuid4().hex[:8]}.db")
        shutil.copy2(src_db, shm_db)
        worker_db = shm_db
    else:
        worker_db = src_db  # fallback

    try:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            future_map = {}
            for size in sizes:
                universe_slice = full_universe[:size]
                if len(universe_slice) < 3:
                    continue
                future = executor.submit(
                    _backtest_universe_size,
                    worker_db, factor, size, full_universe,
                    start, end, holding_period, quantiles,
                    bulk_matrix, matrix_workers,
                )
                future_map[future] = size

            for future in as_completed(future_map):
                entry = future.result()
                size_results.append(entry)
                if entry.get("sharpe") is not None:
                    sharpe_values.append(entry["sharpe"])
    finally:
        # Clean up
        if worker_db != src_db and Path(worker_db).exists():
            try:
                Path(worker_db).unlink()
            except OSError:
                pass
        _price_cache = None  # released when not bulk_matrix

    # Restore expected order
    size_results.sort(key=lambda r: r["size"])

    score, warnings, recommendations = _score(sharpe_values, size_results)
    status = "pass" if score >= 60 else ("warn" if score >= 30 else "fail")

    return AuditModuleResult(
        module="universe_sensitivity",
        status=status,
        score=score,
        details={
            "factor": factor,
            "universe_sizes": sizes,
            "preload_stats": {
                "rows": cache_rows,
                "symbols": cache_sym_count,
                "load_seconds": round(load_sec, 2),
            },
            "results": size_results,
        },
        warnings=warnings,
        recommendations=recommendations,
    )


# ------------------------------------------------------------------ #
#  Scoring                                                             #
# ------------------------------------------------------------------ #


def _score(
    sharpe_values: list[float],
    size_results: list[dict],
) -> tuple[float, list[str], list[str]]:
    warnings: list[str] = []
    recommendations: list[str] = []

    if len(sharpe_values) < 2:
        warnings.append("insufficient universe sizes to assess sensitivity")
        return 50.0, warnings, recommendations

    import statistics

    mean_sharpe = statistics.mean(sharpe_values)
    std_sharpe = statistics.stdev(sharpe_values) if len(sharpe_values) >= 2 else 0.0

    if abs(mean_sharpe) < 1e-9:
        cv = float("inf")
    else:
        cv = abs(std_sharpe / mean_sharpe)

    positive_ratio = sum(1 for s in sharpe_values if s > 0) / len(sharpe_values)

    consistency = max(0.0, min(1.0, 1.0 - cv))
    score = (consistency * 60.0 + positive_ratio * 40.0)
    score = max(0.0, min(100.0, score))

    # Penalise "stable loser": consistent negative Sharpe should never be PASS
    if mean_sharpe <= 0 or positive_ratio < 0.5:
        score = min(score, 30.0)
        if positive_ratio == 0:
            warnings.append("sharpe is negative across all universe sizes — factor is a stable loser, not stable alpha")

    if cv > 1.0:
        warnings.append(f"high sharpe variability across universe sizes (CV={cv:.2f})")
        recommendations.append("factor may be sensitive to universe composition")
    if positive_ratio < 0.5:
        warnings.append("sharpe is negative for majority of universe sizes")
        recommendations.append("alpha may not generalise to broader universes")

    return round(score, 2), warnings, recommendations
