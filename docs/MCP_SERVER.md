# MCP Server Foundation

`v0.35.0` adds a local MCP-compatible research tool layer under `quant.interfaces.mcp_server`.

This is infrastructure for OpenClaw-style research agents. It is not a live trading API, not a broker API, not an order execution service, and not investment advice.

## Security Boundary

Every MCP tool declares exactly one capability level:

- `READ_ONLY`
- `OFFLINE_SIMULATION`
- `PAPER_TRADING_RESERVED`
- `LIVE_TRADING_FORBIDDEN`

v0.35 only enables `READ_ONLY` and `OFFLINE_SIMULATION`.

`PAPER_TRADING_RESERVED` and `LIVE_TRADING_FORBIDDEN` are documented future/blocked capability classes. They must not execute anything unless a later release adds explicit permission gates, tests, and safety review. Live trading remains disabled by default.

Explicitly forbidden tools return `NOT_SUPPORTED_LIVE_TRADING_DISABLED` before any runner implementation can execute:

- `place_order`
- `submit_order`
- `cancel_order`
- `modify_position`
- `connect_broker`
- `execute_trade`
- `live_trade`
- `rebalance_live`
- `paper_trade_live`

The MCP layer does not connect to brokers, submit orders, modify live positions, run a daemon, or schedule cron jobs.

Allowed mutations are limited to local research artifacts: generated reports, generated visualizations, and local SQLite research history produced by existing offline engines. MCP tools must not mutate real portfolios or broker state.

## Permission Enforcement

The tool registry checks `capability_level` before calling any tool runner. Disabled capabilities are blocked at the registry boundary. This ensures forbidden tools such as `place_order`, `connect_broker`, and `execute_trade` never reach portfolio, account, broker, or execution mutation paths.

OpenClaw and LLM agents should use MCP for research support, diagnostics, summaries, and offline simulations. They should not use MCP for autonomous execution.

## Prompt-Injection Posture

MCP tools are deterministic wrappers around existing engines and services.

- no arbitrary shell execution
- no arbitrary file read/write
- no broker credentials
- no binary payloads
- report paths are returned as paths, not file blobs
- visualization paths are returned as paths, not image bytes
- generated artifacts remain local

## CLI

```bash
python -m quant.cli mcp-list-tools
python -m quant.cli mcp-tool-info
python -m quant.cli mcp-tool-info detect_regime
python -m quant.cli mcp-smoke
```

## Tool Categories

- `DATA`: provider status, coverage, universe summaries
- `FACTORS`: factor listing, history, ranking, evaluation
- `REGIMES`: deterministic regime detection and diagnostics
- `RESEARCH`: scheduler status/history/report and local research pipeline runs
- `SIMULATION`: offline historical trade simulation summaries and runs
- `REPORTS`: Agent Export and report summaries
- `VISUALIZATION`: generated chart/dashboard metadata
- `SECURITY`: forbidden trading/broker actions that return `NOT_SUPPORTED`

## JSON Safety

MCP responses use JSON-safe dataclasses:

- `MCPTool`
- `MCPRequest`
- `MCPResponse`
- `MCPToolMetadata`

Every tool metadata record includes `name`, `category`, `capability_level`, `description`, argument schema, return schema, and version. Responses return paths, metadata, summaries, metrics, warnings, and recommendations. They do not return binary images or file blobs.

## Existing Engine Semantics

The MCP layer wraps existing CLI/service/engine boundaries. It does not change factor evaluation semantics, factor backtest semantics, regime detection semantics, scheduler semantics, trading simulation semantics, report schemas, or no-lookahead guarantees.

`run_research_pipeline` and `run_trade_sim` are local offline research/simulation tools. They may generate reports, but they do not modify broker state or live account state.
