from __future__ import annotations

import pandas as pd


class MetricsCalculator:
    @staticmethod
    def calculate(account_state) -> dict:
        nav_series = account_state.nav_history.sort_index()
        if nav_series.empty:
            nav_series = pd.Series([1.0], index=["00000000"])

        # 兼容不同初始 date 处理
        if not nav_series.index.is_monotonic_increasing:
            nav_series = nav_series.sort_index()

        peak_series = nav_series.cummax()
        drawdown_series = (nav_series - peak_series) / peak_series
        current_nav = float(nav_series.iloc[-1]) if not nav_series.empty else 1.0
        peak_nav = float(peak_series.iloc[-1]) if not peak_series.empty else current_nav
        peak_date = str(peak_series.idxmax()) if not peak_series.empty else ""
        max_drawdown = float(drawdown_series.min()) if not drawdown_series.empty else 0.0

        total_return = (current_nav / nav_series.iloc[0]) - 1.0 if len(nav_series) > 0 and nav_series.iloc[0] != 0 else 0.0
        daily_returns = nav_series.pct_change().fillna(0.0)

        sharpe_ratio = 0.0
        if len(daily_returns) > 1:
            std = daily_returns.std(ddof=1)
            sharpe_ratio = (daily_returns.mean() / std) * (252 ** 0.5) if std != 0 else 0.0

        win_rate = 0.0
        if len(daily_returns) > 0:
            win_rate = float((daily_returns > 0).mean())

        return {
            "nav_series": nav_series,
            "peak_series": peak_series,
            "drawdown_series": drawdown_series,
            "current_nav": current_nav,
            "peak_nav": peak_nav,
            "peak_date": peak_date,
            "max_drawdown": max_drawdown,
            "total_return": total_return,
            "daily_returns": daily_returns,
            "sharpe_ratio": sharpe_ratio,
            "win_rate": win_rate,
        }
