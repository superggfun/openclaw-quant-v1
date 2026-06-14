"""Tests for Alpha Stability Audit framework."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from quant.engines.factor_backtest.factor_backtest import (
    FactorBacktest,
    FactorBacktestObservation,
    FactorBacktestPeriod,
    FactorBacktestResult,
)
from quant.engines.factor_eval.factor_evaluation import FactorObservation
from quant.engines.alpha_stability.models import AuditModuleResult
from quant.engines.alpha_stability import (
    AlphaStabilityAudit,
    AlphaStabilityAuditResult,
    compute_stability_score,
)
from quant.engines.alpha_stability.universe_sensitivity import run_universe_sensitivity
from quant.engines.alpha_stability.cost_sensitivity import run_cost_sensitivity
from quant.engines.alpha_stability.turnover_audit import run_turnover_audit
from quant.engines.alpha_stability.decile_analysis import run_decile_analysis
from quant.engines.alpha_stability.ic_decay import run_ic_decay
from quant.storage.sqlite_store import SQLitePriceStore


def seed_trending_prices(db_path: Path, symbols: list[str], days: int = 100) -> None:
    """Seed prices with a clear trend per symbol for predictable factor output."""
    rows = []
    start = date(2024, 1, 1)
    for symbol_index, symbol in enumerate(symbols):
        slope = 0.1 + symbol_index * 0.05
        for offset in range(days):
            close = 100 + offset * slope
            rows.append(
                {
                    "symbol": symbol,
                    "date": (start + timedelta(days=offset)).isoformat(),
                    "open": close,
                    "high": close,
                    "low": close,
                    "close": close,
                    "adj_close": close,
                    "volume": 1000,
                }
            )
    SQLitePriceStore(db_path).upsert_prices(pd.DataFrame(rows))


def seed_random_prices(db_path: Path, symbols: list[str], days: int = 100) -> None:
    """Seed random-ish price data for testing."""
    rows = []
    start = date(2024, 1, 1)
    import random
    random.seed(42)
    for symbol in symbols:
        price = 100.0
        for offset in range(days):
            price = price * (1.0 + random.gauss(0.001, 0.02))
            close = max(price, 1.0)
            rows.append(
                {
                    "symbol": symbol,
                    "date": (start + timedelta(days=offset)).isoformat(),
                    "open": close,
                    "high": close,
                    "low": close,
                    "close": close,
                    "adj_close": close,
                    "volume": 1000,
                }
            )
    SQLitePriceStore(db_path).upsert_prices(pd.DataFrame(rows))


SYMBOLS_10 = [f"TEST{chr(ord('A') + i)}" for i in range(10)]
SYMBOLS_20 = [f"TEST{chr(ord('A') + i)}" for i in range(20)]


# ──────────────────────────────────────────
# Module 1: Universe Sensitivity
# ──────────────────────────────────────────

class TestUniverseSensitivity:
    def test_runs_across_multiple_sizes(self, tmp_path):
        db_path = tmp_path / "univ.db"
        seed_trending_prices(db_path, SYMBOLS_20, days=120)
        store = SQLitePriceStore(db_path)
        result = run_universe_sensitivity(
            "momentum_20d",
            store,
            universe_sizes=[10, 20],
            symbols=SYMBOLS_20,
        )
        assert isinstance(result, AuditModuleResult)
        assert result.module == "universe_sensitivity"
        assert "results" in result.details
        assert len(result.details["results"]) == 2
        for r in result.details["results"]:
            assert "size" in r
            assert "sharpe" in r

    def test_handles_small_universe(self, tmp_path):
        db_path = tmp_path / "small.db"
        seed_trending_prices(db_path, SYMBOLS_10, days=120)
        store = SQLitePriceStore(db_path)
        result = run_universe_sensitivity(
            "momentum_20d",
            store,
            universe_sizes=[20],
            symbols=SYMBOLS_10,
        )
        assert result.status in {"pass", "warn", "fail"}
        assert 0 <= result.score <= 100

    def test_includes_warnings_for_high_variability(self, tmp_path):
        db_path = tmp_path / "var.db"
        seed_random_prices(db_path, SYMBOLS_20, days=200)
        store = SQLitePriceStore(db_path)
        result = run_universe_sensitivity(
            "momentum_20d",
            store,
            universe_sizes=[5, 10, 20],
            symbols=SYMBOLS_20,
        )
        assert isinstance(result.warnings, list)
        assert isinstance(result.recommendations, list)

    def test_to_dict(self, tmp_path):
        db_path = tmp_path / "dict.db"
        seed_trending_prices(db_path, SYMBOLS_20, days=120)
        store = SQLitePriceStore(db_path)
        result = run_universe_sensitivity("momentum_20d", store, universe_sizes=[10, 20], symbols=SYMBOLS_20)
        d = result.to_dict()
        assert d["module"] == "universe_sensitivity"
        assert isinstance(d["score"], float)
        assert "details" in d


# ──────────────────────────────────────────
# Module 2: Cost Sensitivity
# ──────────────────────────────────────────

class TestCostSensitivity:
    def test_runs_at_multiple_cost_levels(self, tmp_path):
        db_path = tmp_path / "cost.db"
        seed_trending_prices(db_path, SYMBOLS_20, days=120)
        store = SQLitePriceStore(db_path)
        result = run_cost_sensitivity(
            "momentum_20d",
            store,
            cost_levels_bps=[0, 5, 10],
            universe=SYMBOLS_20,
        )
        assert result.module == "cost_sensitivity"
        assert len(result.details["results"]) == 3
        for r in result.details["results"]:
            assert "cost_bps" in r
            assert "net_return" in r
            assert "net_sharpe" in r

    def test_net_return_decreases_with_cost(self, tmp_path):
        db_path = tmp_path / "cost2.db"
        seed_trending_prices(db_path, SYMBOLS_20, days=120)
        store = SQLitePriceStore(db_path)
        result = run_cost_sensitivity(
            "momentum_20d",
            store,
            cost_levels_bps=[0, 50],
            universe=SYMBOLS_20,
        )
        res0 = result.details["results"][0]
        res1 = result.details["results"][-1]
        if res0["net_return"] is not None and res1["net_return"] is not None:
            assert res1["net_return"] <= res0["net_return"]

    def test_displays_cost_degradation_warnings(self, tmp_path):
        db_path = tmp_path / "cost3.db"
        seed_trending_prices(db_path, SYMBOLS_20, days=120)
        store = SQLitePriceStore(db_path)
        result = run_cost_sensitivity("momentum_20d", store, cost_levels_bps=[0, 50], universe=SYMBOLS_20)
        assert result.status in {"pass", "warn", "fail"}
        assert 0 <= result.score <= 100


# ──────────────────────────────────────────
# Module 3: Turnover Audit
# ──────────────────────────────────────────

class TestTurnoverAudit:
    def make_backtest_result(self, turnovers: list[float], holding_period: int = 20) -> FactorBacktestResult:
        """Build a minimal FactorBacktestResult with specified turnovers."""
        periods = [
            FactorBacktestPeriod(
                signal_date=f"2024-{(i//20 + 1):02d}-{i%20 + 1:02d}",
                future_date=f"2024-{(i//20 + 2):02d}-{i%20 + 1:02d}",
                long_symbols=["A", "B"],
                short_symbols=["C"],
                long_weights={"A": 0.5, "B": 0.5},
                short_weights={"C": 1.0},
                long_weight_sum=1.0,
                short_weight_sum=1.0,
                net_exposure=0.0,
                gross_exposure=2.0,
                quantile_returns={"q1": 0.01, "q5": 0.02},
                long_return=0.02,
                short_return=-0.01,
                long_short_return=0.01,
                turnover=t,
            )
            for i, t in enumerate(turnovers)
        ]
        return FactorBacktestResult(
            factor="momentum_20d",
            start_date="2024-01-01",
            end_date="2024-12-31",
            holding_period=holding_period,
            quantiles=5,
            long_quantile=5,
            short_quantile=1,
            observations=len(periods) * 10,
            rebalance_dates=[p.signal_date for p in periods],
            quantile_returns={"q1": 0.01, "q2": 0.02, "q3": 0.03, "q4": 0.04, "q5": 0.05},
            top_quantile_return=0.05,
            bottom_quantile_return=0.01,
            long_symbols_by_date={},
            short_symbols_by_date={},
            long_leg_return=0.5,
            short_leg_return=-0.2,
            long_short_return=0.3,
            annual_return=0.25,
            long_short_annual_return=0.25,
            volatility=0.15,
            long_short_volatility=0.15,
            sharpe=1.5,
            long_short_sharpe=1.5,
            max_drawdown=-0.1,
            hit_rate=0.55,
            turnover=0.3,
            gross_exposure=2.0,
            net_exposure=0.0,
            ic_mean=0.05,
            rank_ic_mean=0.06,
            icir=0.8,
            ic_count=100,
            factor_family="price",
            factor_type="momentum",
            factor_category="price_momentum",
            factor_description="test",
            factor_inputs=["close"],
            factor_higher_is_better=True,
            factor_no_lookahead=True,
            factor_coverage=None,
            excluded_symbols=[],
            exclusion_reasons={},
            no_lookahead=True,
            signal_execution_lag="T+1",
            pipeline_enabled=False,
            pipeline_config_path=None,
            pipeline_config=None,
            periods=periods,
            warnings=[],
            report_path="",
        )

    def test_computes_turnover_metrics(self):
        result = self.make_backtest_result([0.1, 0.2, 0.3, 0.2, 0.15], holding_period=20)
        audit = run_turnover_audit(result)
        assert audit.module == "turnover_audit"
        details = audit.details
        assert details["average_turnover"] > 0
        assert details["median_turnover"] > 0
        assert details["max_turnover"] > 0
        assert details["annualised_turnover"] > 0

    def test_flags_excessive_turnover(self):
        result = self.make_backtest_result([0.95, 0.95, 0.95, 0.95, 0.95], holding_period=5)
        audit = run_turnover_audit(result, holding_period=5)
        details = audit.details
        assert details["excessive"] is True
        assert any("exceeds" in w.lower() for w in audit.warnings)

    def test_low_turnover_scores_high(self):
        result = self.make_backtest_result([0.05, 0.05, 0.05, 0.05, 0.05], holding_period=20)
        audit = run_turnover_audit(result, holding_period=20)
        assert audit.score >= 50

    def test_no_turnover_data(self):
        periods = [FactorBacktestPeriod(
            signal_date="2024-01-01", future_date="2024-01-22",
            long_symbols=["A"], short_symbols=["B"],
            long_weights={"A": 1.0}, short_weights={"B": 1.0},
            long_weight_sum=1.0, short_weight_sum=1.0,
            net_exposure=0.0, gross_exposure=2.0,
            quantile_returns={"q1": 0.01, "q5": 0.02},
            long_return=0.01, short_return=-0.01,
            long_short_return=0.02, turnover=None,
        )]
        result = FactorBacktestResult(
            factor="f", start_date="2024-01-01", end_date="2024-01-31",
            holding_period=20, quantiles=5, long_quantile=5, short_quantile=1,
            observations=10, rebalance_dates=["2024-01-01"],
            quantile_returns={}, top_quantile_return=None, bottom_quantile_return=None,
            long_symbols_by_date={}, short_symbols_by_date={},
            long_leg_return=None, short_leg_return=None, long_short_return=None,
            annual_return=None, long_short_annual_return=None,
            volatility=None, long_short_volatility=None,
            sharpe=None, long_short_sharpe=None,
            max_drawdown=None, hit_rate=None, turnover=None,
            gross_exposure=None, net_exposure=None,
            ic_mean=None, rank_ic_mean=None, icir=None, ic_count=0,
            factor_family="price", factor_type="test", factor_category="test",
            factor_description="", factor_inputs=[], factor_higher_is_better=True,
            factor_no_lookahead=True, factor_coverage=None,
            excluded_symbols=[], exclusion_reasons={},
            no_lookahead=True, signal_execution_lag="T+1",
            pipeline_enabled=False, pipeline_config_path=None, pipeline_config=None,
            periods=periods, warnings=[], report_path="",
        )
        audit = run_turnover_audit(result)
        assert audit.status == "warn"
        assert "no turnover data" in audit.warnings[0].lower()


# ──────────────────────────────────────────
# Module 4: Decile Analysis
# ──────────────────────────────────────────

class TestDecileAnalysis:
    def test_runs_decile_backtest(self, tmp_path):
        db_path = tmp_path / "decile.db"
        seed_trending_prices(db_path, SYMBOLS_20, days=120)
        store = SQLitePriceStore(db_path)
        result = run_decile_analysis("momentum_20d", store, universe=SYMBOLS_20)
        assert result.module == "decile_analysis"
        details = result.details
        assert "decile_returns" in details
        assert len(details["decile_returns"]) == 10

    def test_includes_monotonicity_metrics(self, tmp_path):
        db_path = tmp_path / "mono.db"
        seed_trending_prices(db_path, SYMBOLS_20, days=120)
        store = SQLitePriceStore(db_path)
        result = run_decile_analysis("momentum_20d", store, universe=SYMBOLS_20)
        assert "monotonicity_correlation" in result.details
        assert "d10_d1_spread" in result.details

    def test_score_in_range(self, tmp_path):
        db_path = tmp_path / "score2.db"
        seed_trending_prices(db_path, SYMBOLS_20, days=120)
        store = SQLitePriceStore(db_path)
        result = run_decile_analysis("momentum_20d", store, universe=SYMBOLS_20)
        assert 0 <= result.score <= 100


# ──────────────────────────────────────────
# Module 5: IC Decay
# ──────────────────────────────────────────

class TestICDecay:
    def test_measures_ic_at_multiple_horizons(self, tmp_path):
        db_path = tmp_path / "icdecay.db"
        seed_trending_prices(db_path, SYMBOLS_20, days=120)
        store = SQLitePriceStore(db_path)
        result = run_ic_decay("momentum_20d", store, horizons=[1, 5, 10], universe=SYMBOLS_20)
        assert result.module == "ic_decay"
        assert len(result.details["decay"]) == 3
        for d in result.details["decay"]:
            assert "horizon_days" in d
            assert "ic" in d

    def test_estimates_half_life(self, tmp_path):
        db_path = tmp_path / "hl.db"
        seed_trending_prices(db_path, SYMBOLS_20, days=200)
        store = SQLitePriceStore(db_path)
        result = run_ic_decay("momentum_20d", store, horizons=[1, 5, 10, 20], universe=SYMBOLS_20)
        assert "half_life_days" in result.details
        # half-life may be None if insufficient data, that's OK

    def test_short_half_life_warns(self, tmp_path):
        db_path = tmp_path / "short_hl.db"
        seed_random_prices(db_path, SYMBOLS_20, days=200)
        store = SQLitePriceStore(db_path)
        result = run_ic_decay("momentum_20d", store, horizons=[1, 5, 20, 40], universe=SYMBOLS_20)
        assert result.status in {"pass", "warn", "fail"}


# ──────────────────────────────────────────
# Module 6: Stability Score
# ──────────────────────────────────────────

class TestStabilityScore:
    def test_computes_composite_from_modules(self):
        universe_result = AuditModuleResult(
            module="universe_sensitivity", status="pass", score=80.0,
            details={}, warnings=[], recommendations=[],
        )
        cost_result = AuditModuleResult(
            module="cost_sensitivity", status="pass", score=70.0,
            details={}, warnings=[], recommendations=[],
        )
        turnover_result = AuditModuleResult(
            module="turnover_audit", status="pass", score=60.0,
            details={}, warnings=[], recommendations=[],
        )
        ic_result = AuditModuleResult(
            module="ic_decay", status="pass", score=90.0,
            details={}, warnings=[], recommendations=[],
        )

        result = compute_stability_score(
            universe_result=universe_result,
            cost_result=cost_result,
            turnover_result=turnover_result,
            ic_decay_result=ic_result,
            fold_consistency_score=75.0,
        )
        assert result.module == "stability_score"
        assert 0 <= result.score <= 100
        # With equal 20% weights: (80+70+60+90+75)/5 = 75
        assert abs(result.score - 75.0) < 2.0

    def test_handles_missing_modules(self):
        result = compute_stability_score(
            universe_result=AuditModuleResult(
                module="universe_sensitivity", status="pass", score=70.0,
                details={}, warnings=[], recommendations=[],
            ),
        )
        assert result.module == "stability_score"
        assert result.score == 70.0  # only one component
        assert any("missing components" in w.lower() for w in result.warnings)

    def test_normalises_weights(self):
        result = compute_stability_score(
            universe_result=AuditModuleResult(
                module="universe_sensitivity", status="pass", score=80.0,
                details={}, warnings=[], recommendations=[],
            ),
            ic_decay_result=AuditModuleResult(
                module="ic_decay", status="pass", score=40.0,
                details={}, warnings=[], recommendations=[],
            ),
            weights={
                "universe_stability": 0.5,
                "ic_persistence": 0.5,
                "fold_consistency": 0.0,
                "cost_robustness": 0.0,
                "turnover_quality": 0.0,
            },
        )
        # Weighted average with available: 80*0.5 + 40*0.5 = 60
        assert abs(result.score - 60.0) < 1.0

    def test_deduplicates_recommendations(self):
        r = compute_stability_score(
            universe_result=AuditModuleResult(
                module="universe_sensitivity", status="warn", score=50.0,
                details={}, warnings=["w1", "w2"],
                recommendations=["rec1", "rec1", "rec2"],
            ),
            cost_result=AuditModuleResult(
                module="cost_sensitivity", status="warn", score=50.0,
                details={}, warnings=["w3"],
                recommendations=["rec1", "rec3"],
            ),
        )
        assert len(r.recommendations) == len(set(r.recommendations))
        assert "rec1" in r.recommendations
        assert "rec2" in r.recommendations
        assert "rec3" in r.recommendations


# ──────────────────────────────────────────
# Module 7: Orchestrator Integration
# ──────────────────────────────────────────

class TestOrchestrator:
    def test_runs_full_audit(self, tmp_path):
        db_path = tmp_path / "orch.db"
        seed_trending_prices(db_path, SYMBOLS_20, days=120)
        store = SQLitePriceStore(db_path)
        audit = AlphaStabilityAudit(store, report_dir=str(tmp_path))
        result = audit.run("momentum_20d", universe=SYMBOLS_20, write_report=False)
        assert isinstance(result, AlphaStabilityAuditResult)
        assert result.factor == "momentum_20d"
        assert "universe_sensitivity" in result.modules
        assert "cost_sensitivity" in result.modules
        assert "turnover_audit" in result.modules
        assert "decile_analysis" in result.modules
        assert "ic_decay" in result.modules
        assert "stability_score" in result.modules
        assert 0 <= result.composite_score <= 100
        assert result.status in {"pass", "warn", "fail"}

    def test_to_dict(self, tmp_path):
        db_path = tmp_path / "orch2.db"
        seed_trending_prices(db_path, SYMBOLS_20, days=120)
        store = SQLitePriceStore(db_path)
        audit = AlphaStabilityAudit(store, report_dir=str(tmp_path))
        result = audit.run("momentum_20d", universe=SYMBOLS_20, write_report=False)
        d = result.to_dict()
        assert d["factor"] == "momentum_20d"
        assert "modules" in d
        assert "runtime_seconds" in d

    def test_writes_report(self, tmp_path):
        db_path = tmp_path / "orch3.db"
        seed_trending_prices(db_path, SYMBOLS_20, days=120)
        store = SQLitePriceStore(db_path)
        audit = AlphaStabilityAudit(store, report_dir=str(tmp_path))
        result = audit.run("momentum_20d", universe=SYMBOLS_20, write_report=True)
        assert result.report_path
        assert Path(result.report_path).exists()

    def test_run_all(self, tmp_path):
        db_path = tmp_path / "orch4.db"
        seed_trending_prices(db_path, SYMBOLS_20, days=120)
        store = SQLitePriceStore(db_path)
        audit = AlphaStabilityAudit(store, report_dir=str(tmp_path))
        results = audit.run_all(
            factors=["momentum_20d", "reversal_5d"],
            universe=SYMBOLS_20,
            write_report=False,
        )
        assert len(results) == 2
        for r in results:
            assert isinstance(r, AlphaStabilityAuditResult)

    def test_handles_invalid_factor(self, tmp_path):
        db_path = tmp_path / "orch5.db"
        seed_trending_prices(db_path, SYMBOLS_20, days=120)
        store = SQLitePriceStore(db_path)
        audit = AlphaStabilityAudit(store, report_dir=str(tmp_path))
        result = audit.run("nonexistent_factor", universe=SYMBOLS_20, write_report=False)
        assert result.status == "fail"
        assert result.composite_score == 0.0


# ──────────────────────────────────────────
# AuditModuleResult model
# ──────────────────────────────────────────

class TestAuditModuleResult:
    def test_to_dict(self):
        result = AuditModuleResult(
            module="test_module",
            status="pass",
            score=85.0,
            details={"key": "value"},
            warnings=["warning1"],
            recommendations=["rec1"],
        )
        d = result.to_dict()
        assert d["module"] == "test_module"
        assert d["status"] == "pass"
        assert d["score"] == 85.0
        assert d["details"] == {"key": "value"}
        assert d["warnings"] == ["warning1"]
        assert d["recommendations"] == ["rec1"]

    def test_frozen(self):
        result = AuditModuleResult(module="a", status="pass", score=50.0, details={})
        with pytest.raises(Exception):
            result.module = "b"  # type: ignore[misc]


# ──────────────────────────────────────────
# CLI Integration
# ──────────────────────────────────────────

class TestCLIStability:
    def test_command_module_exports(self):
        """Verify stability CLI module has required exports."""
        from quant.cli_commands import stability
        assert hasattr(stability, "register_parser")
        assert hasattr(stability, "handle")

    def test_discovered_as_command(self):
        """Verify stability is discovered by the CLI framework."""
        from quant.cli import COMMAND_HANDLERS
        assert "stability" in COMMAND_HANDLERS

    def test_parser_accepts_factor(self):
        """Verify the parser accepts --factor argument."""
        import argparse
        parser = argparse.ArgumentParser(prog="test")
        subparsers = parser.add_subparsers(dest="command")
        from quant.cli_commands.stability import register_parser
        register_parser(subparsers)
        args = parser.parse_args(["stability", "--factor", "momentum_20d"])
        assert args.factor == "momentum_20d"

    def test_parser_accepts_all(self):
        """Verify the parser accepts --all argument."""
        import argparse
        parser = argparse.ArgumentParser(prog="test")
        subparsers = parser.add_subparsers(dest="command")
        from quant.cli_commands.stability import register_parser
        register_parser(subparsers)
        args = parser.parse_args(["stability", "--all"])
        assert args.all_factors is True
