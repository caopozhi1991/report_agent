from __future__ import annotations

import matplotlib.pyplot as plt
import pandas as pd

from ..base import AnalysisModule


class TradeAnalysis(AnalysisModule):
    name = "trade"
    display_name = "成交分析"

    def analyze(self, account_state, config) -> dict:
        all_trades = []
        for date, trade_df in account_state.trade_history.items():
            if trade_df is not None and not trade_df.empty:
                trade_df = trade_df.copy()
                trade_df["date"] = date
                all_trades.append(trade_df)

        if not all_trades:
            return {
                "buy_count": 0,
                "sell_count": 0,
                "total_buy_amount": 0.0,
                "total_sell_amount": 0.0,
                "net_investment": 0.0,
                "realized_pnl": 0.0,
            }

        trades = pd.concat(all_trades, ignore_index=True)
        trades = self._exclude_repurchase(trades)
        if trades.empty:
            return {
                "buy_count": 0,
                "sell_count": 0,
                "total_buy_amount": 0.0,
                "total_sell_amount": 0.0,
                "net_investment": 0.0,
                "realized_pnl": 0.0,
            }
        buys = trades[trades["操作"].astype(str).str.contains("买入|BUY|B", na=False)]
        sells = trades[trades["操作"].astype(str).str.contains("卖出|SELL|S", na=False)]

        total_buy_amount = float(buys["成交金额"].sum()) if "成交金额" in buys.columns else 0.0
        total_sell_amount = float(sells["成交金额"].sum()) if "成交金额" in sells.columns else 0.0
        net_investment = total_buy_amount - total_sell_amount

        realized_pnl = float((sells["成交金额"] - buys["成交金额"]).sum()) if "成交金额" in trades.columns else 0.0

        return {
            "buy_count": int(len(buys)),
            "sell_count": int(len(sells)),
            "total_buy_amount": total_buy_amount,
            "total_sell_amount": total_sell_amount,
            "net_investment": net_investment,
            "realized_pnl": realized_pnl,
        }

    @staticmethod
    def _exclude_repurchase(trades: pd.DataFrame) -> pd.DataFrame:
        if trades.empty or "证券代码" not in trades.columns:
            return trades
        codes = trades["证券代码"].astype(str).str.split(".").str[0].str.zfill(6)
        operations = trades.get("操作", pd.Series("", index=trades.index)).astype(str)
        repurchase = operations.str.contains("回购|逆回购", case=False, na=False) | codes.str.startswith(("204", "1318"))
        return trades[~repurchase].copy()

    def render(self, analysis_result) -> plt.Figure:
        fig, axes = plt.subplots(1, 2, figsize=(12, 4))
        fig.suptitle("成交分析", fontsize=14)

        buy = analysis_result.get("total_buy_amount", 0.0)
        sell = analysis_result.get("total_sell_amount", 0.0)
        labels = ["买入金额", "卖出金额"]
        values = [buy, sell]
        axes[0].bar(labels, values, color=["steelblue", "darkorange"])
        axes[0].set_title("买卖金额对比")
        axes[0].grid(True, axis="y", linestyle="--", alpha=0.3)

        buy_count = analysis_result.get("buy_count", 0)
        sell_count = analysis_result.get("sell_count", 0)
        total_count = buy_count + sell_count
        if total_count > 0:
            axes[1].pie([buy_count, sell_count], labels=["买入笔数", "卖出笔数"], autopct="%1.1f%%", colors=["steelblue", "darkorange"])
        else:
            axes[1].text(0.5, 0.5, "暂无成交记录", ha="center", va="center")
            axes[1].axis("off")
        axes[1].set_title("成交笔数")

        plt.tight_layout(rect=[0, 0, 1, 0.97])
        return fig
