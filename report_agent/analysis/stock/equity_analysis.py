from __future__ import annotations

import matplotlib.pyplot as plt
import pandas as pd

from ..base import AnalysisModule


class EquityAnalysis(AnalysisModule):
    name = "equity"
    display_name = "持仓分析"

    def analyze(self, account_state, config) -> dict:
        positions = account_state.current_positions.copy()
        if positions.empty:
            return {
                "position_count": 0,
                "total_market_value": 0.0,
                "profit_top5": pd.DataFrame(columns=["证券代码", "盈亏", "市值"]),
                "loss_top5": pd.DataFrame(columns=["证券代码", "盈亏", "市值"]),
                "sector_distribution": pd.Series(dtype=float),
                "win_rate": 0.0,
            }

        positions = positions.fillna(0)
        total_market_value = float(positions["市值"].sum()) if "市值" in positions.columns else 0.0
        profit_top5 = positions.sort_values("盈亏", ascending=False).head(5) if "盈亏" in positions.columns else pd.DataFrame(columns=["证券代码", "盈亏", "市值"])
        loss_top5 = positions.sort_values("盈亏", ascending=True).head(5) if "盈亏" in positions.columns else pd.DataFrame(columns=["证券代码", "盈亏", "市值"])

        sector_distribution = pd.Series(dtype=float)
        if "板块" in positions.columns:
            sector_distribution = positions.groupby("板块")["市值"].sum().sort_values(ascending=False)
        elif "行业" in positions.columns:
            sector_distribution = positions.groupby("行业")["市值"].sum().sort_values(ascending=False)

        positive = float((positions["盈亏"] > 0).sum()) if "盈亏" in positions.columns else 0.0
        total = float(len(positions))
        win_rate = positive / total if total else 0.0

        return {
            "position_count": int(len(positions)),
            "total_market_value": total_market_value,
            "profit_top5": profit_top5[["证券代码", "盈亏", "市值"]].head(5) if {"证券代码", "盈亏", "市值"}.issubset(positions.columns) else profit_top5,
            "loss_top5": loss_top5[["证券代码", "盈亏", "市值"]].head(5) if {"证券代码", "盈亏", "市值"}.issubset(positions.columns) else loss_top5,
            "sector_distribution": sector_distribution,
            "win_rate": win_rate,
        }

    def render(self, analysis_result) -> plt.Figure:
        fig, axes = plt.subplots(2, 2, figsize=(12, 9))
        fig.suptitle("持仓分析", fontsize=14)

        axes[0, 0].text(0.5, 0.5, f"持仓数: {analysis_result.get('position_count', 0)}\n总市值: {analysis_result.get('total_market_value', 0):,.2f}",
                        ha="center", va="center", fontsize=12)
        axes[0, 0].axis("off")

        profit = analysis_result.get("profit_top5")
        if isinstance(profit, pd.DataFrame) and not profit.empty:
            axes[0, 1].barh(profit["证券代码"].tail(5).astype(str), profit["盈亏"].tail(5).astype(float), color="forestgreen")
            axes[0, 1].set_title("盈利 Top5")
        else:
            axes[0, 1].text(0.5, 0.5, "暂无盈利明细", ha="center", va="center")
            axes[0, 1].axis("off")

        loss = analysis_result.get("loss_top5")
        if isinstance(loss, pd.DataFrame) and not loss.empty:
            axes[1, 0].barh(loss["证券代码"].head(5).astype(str), loss["盈亏"].head(5).astype(float), color="firebrick")
            axes[1, 0].set_title("亏损 Top5")
        else:
            axes[1, 0].text(0.5, 0.5, "暂无亏损明细", ha="center", va="center")
            axes[1, 0].axis("off")

        sector = analysis_result.get("sector_distribution")
        if isinstance(sector, pd.Series) and not sector.empty and sector.sum() > 0:
            axes[1, 1].pie(sector.values, labels=sector.index.astype(str), autopct="%1.1f%%")
            axes[1, 1].set_title("板块分布")
        else:
            axes[1, 1].text(0.5, 0.5, "暂无板块分布", ha="center", va="center")
            axes[1, 1].axis("off")

        plt.tight_layout(rect=[0, 0, 1, 0.97])
        return fig
