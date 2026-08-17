from __future__ import annotations

import matplotlib.pyplot as plt
import pandas as pd

from ..base import AnalysisModule


class SummaryAnalysis(AnalysisModule):
    name = "summary"
    display_name = "汇总统计"

    def analyze(self, account_state, config) -> dict:
        nav_series = account_state.nav_history.sort_index()
        current_nav = float(nav_series.iloc[-1]) if not nav_series.empty else 1.0
        initial_nav = float(nav_series.iloc[0]) if not nav_series.empty else 1.0
        total_return = (current_nav / initial_nav) - 1.0 if initial_nav else 0.0

        peak_series = nav_series.cummax()
        drawdown = (nav_series - peak_series) / peak_series
        max_drawdown = float(drawdown.min()) if not drawdown.empty else 0.0
        return {
            "nav": current_nav,
            "cumulative_return": total_return,
            "max_drawdown": max_drawdown,
            "current_profit": account_state.current_profit,
            "current_asset": account_state.current_asset,
            "position_count": len(account_state.current_positions) if not account_state.current_positions.empty else 0,
        }

    def render(self, analysis_result) -> plt.Figure:
        fig, axes = plt.subplots(1, 2, figsize=(10, 4))
        fig.suptitle("汇总统计", fontsize=14)

        labels = ["净值", "累计收益", "最大回撤", "当前盈亏"]
        values = [
            analysis_result.get("nav", 0.0),
            analysis_result.get("cumulative_return", 0.0),
            analysis_result.get("max_drawdown", 0.0),
            analysis_result.get("current_profit", 0.0),
        ]
        axes[0].bar(labels, values, color=["#4C72B0", "#55A868", "#C44E52", "#8172B3"])
        axes[0].set_title("关键指标")
        axes[0].grid(True, axis="y", linestyle="--", alpha=0.3)

        text = (
            f"当前资产: {analysis_result.get('current_asset', 0.0):,.2f}\n"
            f"持仓数: {analysis_result.get('position_count', 0)}\n"
            f"累计收益: {analysis_result.get('cumulative_return', 0.0):.2%}\n"
            f"最大回撤: {analysis_result.get('max_drawdown', 0.0):.2%}"
        )
        axes[1].text(0.5, 0.5, text, ha="center", va="center", fontsize=11)
        axes[1].axis("off")

        plt.tight_layout(rect=[0, 0, 1, 0.97])
        return fig
