from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional

import pandas as pd

from .analysis.registry import ModuleRegistry
from .analysis.stock.equity_analysis import EquityAnalysis
from .analysis.stock.summary_analysis import SummaryAnalysis
from .analysis.stock.trade_analysis import TradeAnalysis
from .config import CONFIG
from .core.account_state import AccountState
from .core.cache_manager import CacheManager
from .core.data_loader import DataLoader
from .core.metrics_calculator import MetricsCalculator
from .core.pdf_generator import PDFReportGenerator


class MultiAccountReportAgent:
    def __init__(self, config: dict | None = None):
        self.config = {**CONFIG, **(config or {})}
        self.data_loader = DataLoader(self.config["data_dir"])
        self.cache_manager = CacheManager(self.config["cache_dir"])
        self.module_registry = ModuleRegistry()
        self.llm_module = None
        self._register_default_modules()
        self._register_llm_module()

    def _register_default_modules(self):
        self.module_registry.register(EquityAnalysis(), asset_types=["stock"])
        self.module_registry.register(TradeAnalysis(), asset_types=["stock"])
        self.module_registry.register(SummaryAnalysis(), asset_types=["stock"])

    def _register_llm_module(self):
        llm_cfg = self.config.get("llm", {})
        if not llm_cfg.get("enabled", False):
            return
        try:
            from .analysis.llm.llm_analysis import LLMAnalysisModule
            self.llm_module = LLMAnalysisModule(
                api_key=llm_cfg.get("api_key", ""),
                model=llm_cfg.get("model", "gpt-4o-mini"),
                temperature=llm_cfg.get("temperature", 0.7),
            )
            self.module_registry.register(self.llm_module, asset_types=["stock"])
        except Exception as exc:
            print(f"⚠️ LLM分析模块未启用: {exc}")
            self.llm_module = None

    def generate_for_account(self, account_id: str, date: str | None = None, data_dir: str | None = None) -> str:
        if date is None:
            date = pd.Timestamp.today().strftime("%Y%m%d")
        data_dir = data_dir or self.config["data_dir"]
        self.data_loader = DataLoader(data_dir)

        account_data = self.data_loader.load_account_data(account_id, date)
        account_info = account_data.get("account", {})
        deals_df = account_data.get("deals", pd.DataFrame())
        positions_df = account_data.get("positions", pd.DataFrame())

        initial_capital = float(self.config["initial_capital"].get(account_id, 0.0))
        restored = self.cache_manager.load_or_seed(account_id, date)
        if restored is None:
            state = AccountState(account_id=account_id, initial_capital=initial_capital)
        elif isinstance(restored, AccountState):
            state = restored
        else:
            state = AccountState.from_dict(restored) if isinstance(restored, dict) else AccountState.from_seed(account_id, restored, initial_capital)

        if self.config.get("account_types", {}).get(account_id, self.config.get("default_asset_type", "stock")) == "stock":
            asset_type = "stock"
        else:
            asset_type = self.config.get("default_asset_type", "stock")

        previous_date = self.cache_manager.get_previous_date(account_id, date)
        prev_state = None
        if previous_date is not None:
            prev_state = self.cache_manager.load_state(account_id, previous_date)
        elif restored is not None and hasattr(restored, "nav_history"):
            prev_state = restored

        if prev_state is not None and hasattr(prev_state, "current_asset"):
            previous_total_asset = float(prev_state.current_asset)
        elif prev_state is not None and not prev_state.nav_history.empty:
            previous_total_asset = float(prev_state.nav_history.iloc[-1] * prev_state.initial_capital)
        else:
            previous_total_asset = initial_capital

        state.update(date, account_info, deals_df, positions_df)

        nav_value = state.calculate_nav(date, previous_total_asset, state.current_profit, state.current_asset)
        state.nav_history.loc[date] = nav_value
        if state.peak_nav is None or nav_value > state.peak_nav:
            state.peak_nav = nav_value
            state.peak_date = date

        metrics = MetricsCalculator.calculate(state)
        report_dir = Path(self.config["output_dir"])
        report_dir.mkdir(parents=True, exist_ok=True)
        output_path = report_dir / f"{account_id}_{date}_report.pdf"

        self.cache_manager.save_state(account_id, date, state)

        enabled_names = self.config.get("enabled_modules", {}).get(account_id, [])
        modules = self.module_registry.get_enabled_modules(asset_type, enabled_names)

        report = PDFReportGenerator(str(output_path), account_id)
        report.add_cover_page({
            "date": date,
            "nav": metrics["current_nav"],
            "total_return": metrics["total_return"],
            "max_drawdown": metrics["max_drawdown"],
            "current_asset": state.current_asset,
        })
        report.add_nav_chart(metrics["nav_series"])
        report.add_drawdown_chart(metrics["drawdown_series"])

        for module in modules:
            analysis_result = module.analyze(state, self.config)
            report.add_analysis_module(module, analysis_result)

        report.save()
        return str(output_path)

    def generate_all(self, date: str | None = None, data_dir: str | None = None) -> List[str]:
        date = date or pd.Timestamp.today().strftime("%Y%m%d")
        account_ids = list(self.config.get("initial_capital", {}).keys())
        outputs = []
        for account_id in account_ids:
            outputs.append(self.generate_for_account(account_id, date, data_dir=data_dir))
        return outputs
