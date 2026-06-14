CREATE TABLE IF NOT EXISTS factor_definitions (
    factor_name TEXT PRIMARY KEY,
    category TEXT,
    description TEXT,
    higher_is_better INTEGER NOT NULL,
    fundamental_required INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS factor_values (
    factor_name TEXT NOT NULL,
    symbol TEXT NOT NULL,
    signal_date TEXT NOT NULL,
    value REAL,
    coverage REAL,
    version TEXT NOT NULL DEFAULT 'v1',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (factor_name, symbol, signal_date, version)
);

CREATE TABLE IF NOT EXISTS factor_evaluation_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    factor_name TEXT NOT NULL,
    ic REAL,
    rank_ic REAL,
    icir REAL,
    ic_count INTEGER,
    rank_ic_count INTEGER,
    coverage REAL,
    missing_pct REAL,
    warnings TEXT,
    report_path TEXT,
    evaluation_date TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS factor_backtest_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    factor_name TEXT NOT NULL,
    -- Correct spread-semantics metrics (additive, non-compounding)
    cumulative_forward_spread REAL,
    spread_sharpe_like REAL,
    spread_max_drawdown REAL,
    return_type TEXT,
    investable_equity INTEGER,
    cumulative_method TEXT,
    metric_semantics TEXT,
    -- Legacy metric aliases (kept for backward compat; prefer *_ columns above)
    long_short_return REAL,
    sharpe REAL,
    drawdown REAL,
    turnover REAL,
    coverage REAL,
    warnings TEXT,
    report_path TEXT,
    evaluation_date TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS factor_walk_forward_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    factor_name TEXT NOT NULL,
    fold TEXT,
    train_return REAL,
    test_return REAL,
    train_sharpe REAL,
    test_sharpe REAL,
    warnings TEXT,
    report_path TEXT,
    evaluation_date TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS factor_stability_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    factor_name TEXT NOT NULL,
    stability_score REAL,
    coverage_score REAL,
    confidence_score REAL,
    factor_decay_score REAL,
    overall_score REAL,
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS factor_versions (
    factor_name TEXT NOT NULL,
    version TEXT NOT NULL,
    description TEXT,
    change_reason TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (factor_name, version)
);

CREATE TABLE IF NOT EXISTS factor_regime_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    factor_name TEXT NOT NULL,
    regime TEXT NOT NULL,
    metric_type TEXT,
    ic REAL,
    rank_ic REAL,
    icir REAL,
    mean_spread_return REAL,
    return_ir REAL,
    positive_ic_rate REAL,
    coverage REAL,
    regime_observation_share REAL,
    stability REAL,
    samples INTEGER,
    sample_days INTEGER,
    sample_observations INTEGER,
    evaluation_date TEXT NOT NULL,
    report_path TEXT
);

CREATE INDEX IF NOT EXISTS idx_factor_regime_history_factor
ON factor_regime_history (factor_name, regime, evaluation_date);
