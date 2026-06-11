# Decisions

## 2026-06-11: Start With SQLite

SQLite is the local source of truth for v0.1.0 because it is simple, durable, testable, and easy for AI assistants to inspect.

## 2026-06-11: Keep Broker Integration Out of Scope

The portfolio module is a simulated state engine only. It does not connect to brokers, manage credentials, or place orders.

## 2026-06-11: Use Services as Boundaries

CLI commands should call service classes. Services should coordinate rules and persistence. Storage classes should own SQL and schema details.

## 2026-06-11: Use Latest Close for Portfolio Valuation

Portfolio valuation reads the latest `close` from the existing `prices` table. If no price exists for a held symbol, the CLI displays `N/A` for current price, market value, and unrealized PnL.

## 2026-06-11: Backtests Use Stored Prices Only

The backtest engine reads from the existing `prices` table and never downloads data. Data refresh remains the job of `update-prices`.

## 2026-06-11: Deterministic Position Sizing

The V0.2 SMA crossover backtest uses deterministic code to calculate trade quantity from available cash, close price, and commission. LLMs and future OpenClaw callers must not directly decide quantities.

## 2026-06-11: Generated Reports Stay Out of Git

Backtest JSON reports are written under `reports/` and ignored by git. The repository keeps only `reports/.gitkeep`.
