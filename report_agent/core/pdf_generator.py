from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages


class PDFReportGenerator:
    def __init__(self, output_path: str, account_name: str):
        self.output_path = Path(output_path)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.account_name = account_name
        self.pdf = PdfPages(str(self.output_path))
        self.pages = []

    def add_cover_page(self, stats: dict):
        fig = plt.figure(figsize=(8.5, 11))
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
        fig, ax = plt.subplots(figsize=(12, 9))
        ax.axis('off')
        ax.text(0.5, 0.96, title, fontsize=16, fontweight='bold', ha='center', va='top')
        if subtitle:
            ax.text(0.5, 0.90, subtitle, fontsize=11, ha='center', va='top', color='gray')
        ax.text(0.05, 0.82, content, fontsize=10, ha='left', va='top', wrap=True, linespacing=1.8, transform=ax.transAxes)
        self.pages.append(fig)

    def add_nav_chart(self, nav_series: pd.Series):
        fig, ax = plt.subplots(figsize=(8.5, 11))
        ax.plot(nav_series.index, nav_series.values, marker="o", linewidth=1.5)
        ax.set_title("净值曲线")
        ax.set_xlabel("日期")
        ax.set_ylabel("净值")
        ax.grid(True, linestyle="--", alpha=0.3)
        fig.autofmt_xdate()
        self.pages.append(fig)

    def add_drawdown_chart(self, drawdown_series: pd.Series):
        fig, ax = plt.subplots(figsize=(8.5, 11))
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
                pdf.savefig(fig, bbox_inches="tight")
                plt.close(fig)
