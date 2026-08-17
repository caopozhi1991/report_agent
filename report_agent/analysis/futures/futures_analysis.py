from __future__ import annotations

import matplotlib.pyplot as plt
import pandas as pd

from ..base import AnalysisModule


class FuturesEquityAnalysis(AnalysisModule):
    name = "futures_equity"
    display_name = "期货持仓分析"

    def analyze(self, account_state, config) -> dict:
        positions = account_state.current_positions.copy()
        if positions.empty:
            return {"contract_count": 0, "margin_usage": 0.0, "direction": "neutral"}
        positions = positions.fillna(0)
        margin_usage = float(positions["市值"].sum()) if "市值" in positions.columns else 0.0
        long = positions[positions.get("方向", "").astype(str).str.contains("多", na=False)] if "方向" in positions.columns else pd.DataFrame()
        short = positions[positions.get("方向", "").astype(str).str.contains("空", na=False)] if "方向" in positions.columns else pd.DataFrame()
        direction = "long" if len(long) >= len(short) else "short"
        return {
            "contract_count": int(len(positions)),
            "margin_usage": margin_usage,
            "direction": direction,
        }

    def render(self, analysis_result) -> plt.Figure:
        fig, ax = plt.subplots(figsize=(8, 4))
        fig.suptitle("期货持仓分析", fontsize=14)
        ax.text(0.5, 0.5,
                f"合约数: {analysis_result.get('contract_count', 0)}\n"
                f"保证金占用: {analysis_result.get('margin_usage', 0.0):,.2f}\n"
                f"方向偏好: {analysis_result.get('direction', 'neutral')}",
                ha="center", va="center", fontsize=12)
        ax.axis("off")
        return fig
