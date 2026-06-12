# Unified Protocols

`v0.29.0` adds a lightweight unified account, order, fill, position, signal, recommendation, trade, and portfolio snapshot protocol layer.

This is internal architecture for offline research, historical simulation, Agent Export, and future MCP/OpenClaw interfaces. It is not a live broker integration, not real-time execution, and not investment advice.

## Objects

- `AccountState`: account-level cash, equity, market value, PnL, costs, positions, orders, fills, timestamp, and metadata.
- `Position`: symbol, shares, average cost, market price, market value, unrealized PnL, portfolio weight, and timestamp.
- `Order`: symbol, side, quantity, target weight, signal date, creation time, status, reason, and metadata.
- `Fill`: order reference, symbol, side, quantity, price, cost, fill time, signal date, and execution date.
- `TradeRecord`: normalized executed trade data for strategy and portfolio-method attribution.
- `Signal`: symbol score, signal date, source, confidence, factor breakdown, and metadata.
- `Recommendation`: deterministic BUY/SELL/HOLD/REDUCE/INCREASE recommendation object for downstream consumers.
- `PortfolioSnapshot`: date-level cash, equity, positions, weights, drawdown, costs, and trade count.

## Order Status

Supported order statuses:

- `PENDING`
- `SUBMITTED`
- `PARTIALLY_FILLED`
- `FILLED`
- `CANCELLED`
- `REJECTED`

## Recommendation Actions

Supported recommendation actions:

- `BUY`
- `SELL`
- `HOLD`
- `REDUCE`
- `INCREASE`

## Validation

`quant/core_protocols/protocol_validation.py` provides lightweight checks:

- cash must not be negative
- shares must not be negative
- weights should sum near one when they represent target allocations
- `signal_date <= execution_date`
- fills should reference known orders
- account equity should reconcile to cash plus position market value

Each protocol object also exposes `validate()`.

## Serialization

Every protocol object supports:

- `to_dict()`
- `from_dict()` where reconstruction is useful
- JSON-safe primitive fields

These objects are intentionally small so MCP tools, future OpenClaw agents, broker adapters, and APIs can use stable payloads without depending on report-specific JSON schemas.

`v0.35.0` adds a local MCP-compatible research interface that can return JSON-safe protocol-compatible payloads. No broker adapter, live execution interface, or live trading API is implemented.

`v0.30.0` market realism fields such as requested quantity, executed quantity, rejected quantity, and execution reason are report diagnostics. They do not change the JSON-safe protocol object definitions.

## Integration Boundary

Current integration is internal:

- `PortfolioAccount` can convert account state, snapshots, and trades into protocol objects.
- `TradingSimulator` creates and validates protocol orders/fills while preserving existing trade simulation reports.
- `ExecutionEngine` creates and validates protocol orders/fills while preserving existing execution reports.
- `AgentExporter` can consume protocol objects directly through `export_protocol()`.

No existing CLI behavior or report schema is changed in this release.
