from __future__ import annotations

import json

import matplotlib.pyplot as plt
import pandas as pd

from ..base import AnalysisModule


class LLMAnalysisModule(AnalysisModule):
    name = "llm_analysis"
    display_name = "智能分析"

    def __init__(self, api_key: str = None, model: str = "gpt-4o-mini", temperature: float = 0.7):
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.client = None
        if api_key:
            try:
                from openai import OpenAI
                self.client = OpenAI(api_key=api_key)
            except Exception:
                self.client = None

    def analyze(self, account_state, config) -> dict:
        if self.client is None:
            return {
                "trade_logic": "未启用大模型分析，当前为离线模式。",
                "market_environment": "基于现有数据，需在配置中启用 llm 并提供 OpenAI API Key。",
                "risks": "缺少外部模型推断，建议人工核对仓位与回撤风险。",
                "outlook": "继续保持监控净值与回撤趋势，待下一交易日数据确认后再调整仓位。",
            }

        summary = self._build_data_summary(account_state)
        prompt = self._build_prompt(summary)
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "你是一位专业的投资分析助手，擅长从交易数据中提炼逻辑和洞察。"},
                {"role": "user", "content": prompt},
            ],
            temperature=self.temperature,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        try:
            return json.loads(content)
        except Exception:
            return {
                "trade_logic": content,
                "market_environment": "",
                "risks": "",
                "outlook": "",
            }

    def render(self, result: dict):
        fig, ax = plt.subplots(figsize=(12, 9))
        ax.axis("off")
        lines = [
            "【交易逻辑分析】",
            "",
            result.get("trade_logic", "无交易逻辑说明"),
            "",
            "【市场环境判断】",
            "",
            result.get("market_environment", "无环境分析"),
            "",
            "【风险提示】",
            "",
            result.get("risks", "无风险提示"),
            "",
            "【后市展望】",
            "",
            result.get("outlook", "无后市展望"),
        ]
        text = "\n".join(lines)
        ax.text(0.05, 0.95, text, fontsize=10, ha="left", va="top", wrap=True, linespacing=1.8, transform=ax.transAxes)
        ax.set_title("智能分析报告", fontsize=14, fontweight="bold")
        return fig

    def _build_data_summary(self, state):
        positions = state.current_positions.copy() if not state.current_positions.empty else pd.DataFrame()
        summary = {
            "日期": str(state.nav_history.index[-1]) if not state.nav_history.empty else "",
            "当前净值": float(state.nav_history.iloc[-1]) if not state.nav_history.empty else 1.0,
            "总资产": float(state.current_asset),
            "总盈亏": float(state.current_profit),
            "股票仓位": f"{(state.current_asset / max(state.initial_capital, 1e-9) * 100):.1f}%" if state.initial_capital else "0.0%",
            "持仓数量": int(len(positions)),
            "盈利家数": int((positions["盈亏"] > 0).sum()) if not positions.empty and "盈亏" in positions.columns else 0,
            "亏损家数": int((positions["盈亏"] < 0).sum()) if not positions.empty and "盈亏" in positions.columns else 0,
            "盈利TOP3": positions.nlargest(3, "盈亏")[['证券代码', '盈亏']].to_dict('records') if not positions.empty and "盈亏" in positions.columns else [],
            "亏损TOP3": positions.nsmallest(3, "盈亏")[['证券代码', '盈亏']].to_dict('records') if not positions.empty and "盈亏" in positions.columns else [],
            "板块分布": positions['板块'].value_counts().to_dict() if not positions.empty and '板块' in positions.columns else {},
        }
        return summary

    def _build_prompt(self, summary: dict) -> str:
        return f"""
请基于以下数据，对今日投资情况进行专业分析：

【数据摘要】
- 报告日期：{summary['日期']}
- 当前净值：{summary['当前净值']:.4f}
- 总资产：{summary['总资产']:,.2f} 元
- 总盈亏：{summary['总盈亏']:,.2f} 元
- 股票仓位：{summary['股票仓位']}
- 持仓个股数：{summary['持仓数量']} 只
- 盈亏家数：盈利 {summary['盈利家数']} 只，亏损 {summary['亏损家数']} 只

【盈利TOP3】
{json.dumps(summary['盈利TOP3'], ensure_ascii=False, indent=2)}

【亏损TOP3】
{json.dumps(summary['亏损TOP3'], ensure_ascii=False, indent=2)}

【板块分布】
{json.dumps(summary['板块分布'], ensure_ascii=False, indent=2)}

请输出JSON，且必须包含以下字段：
1. trade_logic: 今日交易逻辑分析（买入/卖出操作的方向和意图）
2. market_environment: 市场环境判断（结合板块分布和盈亏情况）
3. risks: 当前持仓面临的主要风险
4. outlook: 后市展望与操作建议

要求：专业、简洁、有数据支撑。
"""
