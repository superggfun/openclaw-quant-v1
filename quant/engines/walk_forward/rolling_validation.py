"""Rolling validation helpers for offline strategy reports."""

from __future__ import annotations

import pandas as pd


class RollingValidation:
    """Compute rolling return, Sharpe, IC, Rank IC, and drawdown series."""

    @staticmethod
    def analyze(
        dated_returns: dict[str, float],
        dated_ic: dict[str, float] | None = None,
        dated_rank_ic: dict[str, float] | None = None,
        window: int = 3,
    ) -> dict:
        returns = RollingValidation._series(dated_returns)
        ic = RollingValidation._series(dated_ic or {})
        rank_ic = RollingValidation._series(dated_rank_ic or {})
        if returns.empty:
            return {
                "window": window,
                "rolling_return": {},
                "rolling_sharpe": {},
                "rolling_ic": {},
                "rolling_rank_ic": {},
                "rolling_drawdown": {},
            }
        rolling_return = (1.0 + returns).rolling(window).apply(lambda values: float(values.prod() - 1.0), raw=False)
        rolling_std = returns.rolling(window).std()
        rolling_sharpe = (returns.rolling(window).mean() / rolling_std) * (252.0 ** 0.5)
        equity = (1.0 + returns).cumprod()
        rolling_drawdown = equity / equity.rolling(window).max() - 1.0
        return {
            "window": window,
            "rolling_return": RollingValidation._to_dict(rolling_return.dropna()),
            "rolling_sharpe": RollingValidation._to_dict(rolling_sharpe.dropna()),
            "rolling_ic": RollingValidation._to_dict(ic.rolling(window).mean().dropna()),
            "rolling_rank_ic": RollingValidation._to_dict(rank_ic.rolling(window).mean().dropna()),
            "rolling_drawdown": RollingValidation._to_dict(rolling_drawdown.dropna()),
        }

    @staticmethod
    def _series(values: dict[str, float]) -> pd.Series:
        if not values:
            return pd.Series(dtype="float64")
        return pd.Series(
            {
                pd.to_datetime(date): float(value)
                for date, value in values.items()
                if value is not None and pd.notna(value)
            },
            dtype="float64",
        ).sort_index()

    @staticmethod
    def _to_dict(series: pd.Series) -> dict[str, float]:
        return {index.strftime("%Y-%m-%d"): float(value) for index, value in series.items() if pd.notna(value)}
