from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages


class PDFReportGenerator:
    PAGE_SIZE = (8.27, 11.69)

    def __init__(self, output_path: str, account_name: str):
        self.output_path = Path(output_path)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.account_name = account_name
        self.pdf = PdfPages(str(self.output_path))
        self.pages = []

    def add_cover_page(self, stats: dict):
        fig = plt.figure(figsize=self.PAGE_SIZE)
        fig.suptitle(f"{self.account_name} 投资报告", fontsize=18, y=0.95)
        fig.text(0.5, 0.8, f"日期: {stats.get('date', '')}", ha="center", fontsize=12)
        fig.text(0.5, 0.7, f"净值: {stats.get('nav', 0.0):.4f}", ha="center", fontsize=12)
        fig.text(0.5, 0.64, f"累计收益: {stats.get('total_return', 0.0):.2%}", ha="center", fontsize=12)
        fig.text(0.5, 0.58, f"最大回撤: {stats.get('max_drawdown', 0.0):.2%}", ha="center", fontsize=12)
        fig.text(0.5, 0.52, f"当前资产: {stats.get('current_asset', 0.0):,.2f}", ha="center", fontsize=12)
        fig.text(0.5, 0.2, "报告生成 by report_agent", ha="center", fontsize=10, color="gray")
        self.pages.append(fig)

    def add_analysis_module(self, module, result: dict):
        fig = module.render(result)
        self.pages.append(fig)

    def add_text_page(self, title: str, content: str, subtitle: str | None = None):
        fig, ax = plt.subplots(figsize=self.PAGE_SIZE)
        ax.axis('off')
        ax.text(0.5, 0.96, title, fontsize=16, fontweight='bold', ha='center', va='top')
        if subtitle:
            ax.text(0.5, 0.90, subtitle, fontsize=11, ha='center', va='top', color='gray')
        ax.text(0.05, 0.82, content, fontsize=10, ha='left', va='top', wrap=True, linespacing=1.8, transform=ax.transAxes)
        self.pages.append(fig)

    def add_nav_chart(self, nav_series: pd.Series):
        fig, ax = plt.subplots(figsize=self.PAGE_SIZE)
        nav_series = nav_series.sort_index()
        ax.plot(nav_series.index.astype(str), nav_series.values, marker="o", linewidth=1.8, color="#2E75B6")
        ax.set_title("一、净值与权益变化（纯股票策略）\n历史净值曲线", pad=18)
        ax.set_xlabel("日期")
        ax.set_ylabel("净值")
        ax.grid(True, linestyle="--", alpha=0.3)
        ax.tick_params(axis="x", rotation=45)
        if not nav_series.empty:
            ax.annotate(f"{nav_series.iloc[-1]:.4f}", (len(nav_series) - 1, nav_series.iloc[-1]),
                        xytext=(8, 8), textcoords="offset points", fontsize=10)
        self.pages.append(fig)

    def add_nav_and_metrics(self, nav_series: pd.Series, metrics: dict, initial_capital: float, stock_mv: float):
        fig = plt.figure(figsize=self.PAGE_SIZE)
        chart_ax = fig.add_axes([0.10, 0.49, 0.80, 0.39])
        nav_series = nav_series.sort_index()
        chart_ax.plot(nav_series.index.astype(str), nav_series.values, marker="o", linewidth=1.8, color="#2E75B6")
        chart_ax.set_title("一、净值与权益变化（纯股票策略）", fontsize=14, fontweight="bold", pad=12)
        chart_ax.set_ylabel("单位净值")
        chart_ax.grid(True, linestyle="--", alpha=0.3)
        chart_ax.tick_params(axis="x", rotation=35, labelsize=8)
        if not nav_series.empty:
            chart_ax.annotate(f"{nav_series.iloc[-1]:.4f}", (len(nav_series) - 1, nav_series.iloc[-1]),
                              xytext=(8, 8), textcoords="offset points", fontsize=9)

        peak_date = metrics.get("peak_date", "")
        low_date = str(nav_series.idxmin()) if not nav_series.empty else ""
        rows = [
            ["指标", "数值"],
            ["策略初始本金", f"{initial_capital:,.2f} 元"],
            ["历史最高净值", f"{metrics.get('peak_nav', 1.0):.4f}（{peak_date}）"],
            ["历史最低净值", f"{nav_series.min():.4f}（{low_date}）" if not nav_series.empty else "1.0000"],
            ["当前单位净值", f"{metrics.get('current_nav', 1.0):.4f}"],
            ["累计策略收益率", f"{metrics.get('total_return', 0.0):+.2%}"],
            ["期间最大回撤", f"{abs(metrics.get('max_drawdown', 0.0)):.2%}"],
            ["当前股票仓位", f"{stock_mv / initial_capital:.1%}" if initial_capital else "0.0%"],
        ]
        table_ax = fig.add_axes([0.12, 0.08, 0.76, 0.31])
        table_ax.axis("off")
        table = table_ax.table(cellText=rows[1:], colLabels=rows[0], loc="center", cellLoc="center",
                               bbox=[0, 0, 1, 1], colWidths=[0.45, 0.55])
        table.auto_set_font_size(False)
        table.set_fontsize(9)
        for (row_index, _), cell in table.get_celld().items():
            cell.set_edgecolor("#D9E2F3")
            if row_index == 0:
                cell.set_facecolor("#2E75B6")
                cell.get_text().set_color("white")
                cell.get_text().set_weight("bold")
        fig.text(0.5, 0.43, "策略核心指标汇总", ha="center", va="center", fontsize=12, fontweight="bold")
        self.pages.append(fig)

    def add_stock_review(self, stats: dict, trades: pd.DataFrame, positions: pd.DataFrame, llm_results: dict | None = None):
        trade_text = (
            f"当日共 {stats.get('buy_count', 0) + stats.get('sell_count', 0)} 笔纯股票成交："
            f"{stats.get('buy_count', 0)} 笔买入，{stats.get('sell_count', 0)} 笔卖出。\n\n"
            "纯股票部分无交易，策略处于持仓观望状态。所有 ETF 和逆回购成交均不纳入本报告。"
            if trades.empty
            else "当日纯股票成交已按买入、卖出分类统计，ETF 和逆回购成交不纳入本报告。"
        )
        trade_llm_text = self._llm_text(llm_results.get("trade", llm_results)) if llm_results else ""
        self._add_trade_page(stats, trade_text, trade_llm_text)
        market_value = float(positions.get("市值", pd.Series(dtype=float)).sum())
        profit_count = int((positions.get("盈亏", pd.Series(dtype=float)) > 0).sum())
        sector_count = positions["板块"].nunique() if "板块" in positions.columns else 0
        position_subtitle = (
            f"当前持有 {len(positions)} 只个股，股票总市值 {market_value:,.2f} 元；"
            f"浮动总盈亏 {positions.get('盈亏', pd.Series(dtype=float)).sum():+,.2f} 元；"
            f"持仓胜率 {profit_count / len(positions):.1%}；板块数 {sector_count}；"
            f"策略占用仓位 {market_value / stats.get('initial_capital', 100000.0):.1%}"
            if len(positions) else "当前无纯股票持仓。"
        )
        position_llm_text = self._llm_text(llm_results.get("positions", llm_results)) if llm_results else ""
        self._add_position_pages(self._position_rows(positions), position_subtitle, position_llm_text)

    def _add_trade_page(self, stats: dict, trade_text: str, llm_text: str = ""):
        fig = plt.figure(figsize=self.PAGE_SIZE)
        ax = fig.add_axes([0.07, 0.06, 0.86, 0.88])
        ax.axis("off")
        ax.text(0.5, 0.98, "二、当日交易分析", ha="center", va="top", fontsize=16, fontweight="bold", transform=ax.transAxes)
        ax.text(0.5, 0.925, "成交总览（仅统计纯股票，ETF 已剔除）", ha="center", va="top", fontsize=10, color="dimgray", transform=ax.transAxes)
        rows = [
            ["类型", "笔数", "成交金额"],
            ["买入", str(stats.get("buy_count", 0)), f"{stats.get('total_buy_amount', 0.0):,.2f} 元"],
            ["卖出", str(stats.get("sell_count", 0)), f"{stats.get('total_sell_amount', 0.0):,.2f} 元"],
            ["净投入", "—", f"{stats.get('net_investment', 0.0):+,.2f} 元"],
        ]
        table = ax.table(cellText=rows[1:], colLabels=rows[0], cellLoc="center", bbox=[0.02, 0.70, 0.96, 0.17])
        self._style_table(table, 9)
        ax.text(0.02, 0.64, "交易逻辑说明", fontsize=12, fontweight="bold", transform=ax.transAxes)
        ax.text(0.02, 0.60, trade_text, fontsize=10, va="top", wrap=True, linespacing=1.5, transform=ax.transAxes)
        if llm_text:
            ax.text(0.02, 0.43, "交易分析（大模型）", fontsize=12, fontweight="bold", transform=ax.transAxes)
            ax.text(0.02, 0.39, llm_text, fontsize=9.5, va="top", wrap=True, linespacing=1.45, transform=ax.transAxes)
        self.pages.append(fig)

    def _add_position_pages(self, rows: list[list[str]], subtitle: str, llm_text: str = ""):
        data_rows = rows[1:]
        chunk_size = 11
        chunks = [data_rows[index:index + chunk_size] for index in range(0, len(data_rows), chunk_size)]
        if not chunks:
            chunks = [[['-', '-', '-', '-', '暂无纯股票持仓']]]
        for index, chunk in enumerate(chunks):
            title = "三、股票持仓分析（无 ETF 持仓）"
            if len(chunks) > 1:
                title += f"（{index + 1}/{len(chunks)}）"
            fig = plt.figure(figsize=self.PAGE_SIZE)
            ax = fig.add_axes([0.07, 0.06, 0.86, 0.88])
            ax.axis("off")
            ax.text(0.5, 0.98, title, ha="center", va="top", fontsize=15, fontweight="bold", transform=ax.transAxes)
            ax.text(0.5, 0.925, subtitle, ha="center", va="top", fontsize=9.5, color="dimgray", transform=ax.transAxes)
            table = ax.table(cellText=chunk, colLabels=rows[0], cellLoc="center", bbox=[0.01, 0.88 - len(chunk) * 0.055, 0.98, len(chunk) * 0.055 + 0.035])
            self._style_table(table, 8.5)
            if index == len(chunks) - 1 and llm_text:
                llm_top = 0.88 - len(chunk) * 0.055 - 0.08
                ax.text(0.01, llm_top, "持仓分析（大模型）", fontsize=12, fontweight="bold", transform=ax.transAxes)
                ax.text(0.01, llm_top - 0.04, llm_text, fontsize=9.2, va="top", wrap=True, linespacing=1.4, transform=ax.transAxes)
            self.pages.append(fig)

    @staticmethod
    def _llm_text(result: dict) -> str:
        return "\n\n".join([
            f"交易逻辑：{result.get('trade_logic', '无')}",
            f"市场环境：{result.get('market_environment', '无')}",
            f"风险提示：{result.get('risks', '无')}",
            f"后市展望：{result.get('outlook', '无')}",
        ])

    def _position_rows(self, positions: pd.DataFrame) -> list[list[str]]:
        rows = [["代码", "持仓", "成本价", "市值（元）", "浮盈（元）"]]
        for _, row in positions.iterrows():
            code = str(row.get("证券代码", "")).split(".")[0].zfill(6)
            rows.append([
                code,
                f"{row.get('当前拥股', 0):g}",
                f"{row.get('成本价', 0.0):.3f}",
                f"{row.get('市值', 0.0):,.2f}",
                f"{row.get('盈亏', 0.0):+,.2f}",
            ])
        return rows

    def _add_table_page(self, title: str, rows: list[list[str]], subtitle: str = ""):
        fig, ax = plt.subplots(figsize=self.PAGE_SIZE)
        ax.axis("off")
        ax.set_title(title, fontsize=16, fontweight="bold", pad=24)
        if subtitle:
            ax.text(0.5, 0.92, subtitle, ha="center", va="top", fontsize=10, color="dimgray", transform=ax.transAxes)
        if len(rows) > 1:
            row_height = min(0.055, 0.72 / len(rows))
            table_height = row_height * len(rows)
            table = ax.table(cellText=rows[1:], colLabels=rows[0], loc="upper center", cellLoc="center",
                             bbox=[0.04, 0.88 - table_height, 0.92, table_height])
            self._style_table(table, 9)
        self.pages.append(fig)

    @staticmethod
    def _style_table(table, font_size: float):
        table.auto_set_font_size(False)
        table.set_fontsize(font_size)
        for (row_index, _), cell in table.get_celld().items():
            cell.set_edgecolor("#D9E2F3")
            cell.set_linewidth(0.6)
            if row_index == 0:
                cell.set_facecolor("#2E75B6")
                cell.get_text().set_color("white")
                cell.get_text().set_weight("bold")

    def add_drawdown_chart(self, drawdown_series: pd.Series):
        fig, ax = plt.subplots(figsize=self.PAGE_SIZE)
        ax.plot(drawdown_series.index, drawdown_series.values, linewidth=1.5, color="tomato")
        ax.set_title("回撤曲线")
        ax.set_xlabel("日期")
        ax.set_ylabel("回撤率")
        ax.grid(True, linestyle="--", alpha=0.3)
        fig.autofmt_xdate()
        self.pages.append(fig)

    def save(self):
        with self.pdf as pdf:
            for fig in self.pages:
                pdf.savefig(fig)
                plt.close(fig)
