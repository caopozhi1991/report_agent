from __future__ import annotations

import json

import matplotlib.pyplot as plt
import pandas as pd

from ..base import AnalysisModule


class LLMAnalysisModule(AnalysisModule):
    name = "llm_analysis"
    display_name = "智能分析"

    def __init__(self, api_key: str = None, base_url: str = None, model: str = "gpt-4o-mini", temperature: float = 0.7):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.temperature = temperature
        self.client = None
        if api_key:
            try:
                from openai import OpenAI
                client_kwargs = {"api_key": api_key}
                if base_url:
                    client_kwargs["base_url"] = base_url
                self.client = OpenAI(**client_kwargs)
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
        return self._call_section(self._build_prompt(summary), "当前数据已提交给大模型分析。")

    def analyze_trade(self, account_state, trade_result: dict) -> dict:
        prompt = (
            "请只分析今日交易行为，输出 JSON，字段必须为 trade_logic、market_environment、risks、outlook。"
            f"交易统计：{json.dumps(trade_result, ensure_ascii=False)}。"
            "如果没有纯股票成交，请明确说明处于观望状态，ETF 不纳入分析。"
        )
        return self._call_section(prompt, "当前没有纯股票成交，策略处于观望状态。")

    def analyze_positions(self, account_state, positions: pd.DataFrame) -> dict:
        records = positions.to_dict("records") if not positions.empty else []
        prompt = (
            "请只分析当前纯股票持仓，输出 JSON，字段必须为 trade_logic、market_environment、risks、outlook。"
            f"持仓数据：{json.dumps(records, ensure_ascii=False)}。"
            "请关注集中度、浮盈亏、仓位水平和后续风险，ETF 已经剔除。"
        )
        return self._call_section(prompt, "当前纯股票持仓维持观望，重点关注仓位和个股浮盈亏变化。")

    def _call_section(self, prompt: str, offline_text: str) -> dict:
        if self.client is None:
            return {
                "trade_logic": offline_text,
                "market_environment": "离线模式，未执行外部模型推断。",
                "risks": "请结合净值回撤和个股浮盈亏人工复核。",
                "outlook": "等待下一交易日数据确认后再调整策略。",
            }
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "你是一位专业的投资分析助手，只基于提供的数据回答。"},
                {"role": "user", "content": prompt},
            ],
            temperature=self.temperature,
            response_format={"type": "json_object"},
        )
        try:
            return json.loads(response.choices[0].message.content)
        except Exception:
            return {"trade_logic": response.choices[0].message.content, "market_environment": "", "risks": "", "outlook": ""}

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
