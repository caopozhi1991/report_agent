from __future__ import annotations

from pathlib import Path
import re
from typing import Iterable, List, Optional

import pandas as pd

from .analysis.registry import ModuleRegistry
from .analysis.stock.equity_analysis import EquityAnalysis
from .analysis.stock.summary_analysis import SummaryAnalysis
from .analysis.stock.trade_analysis import TradeAnalysis
from .config import CONFIG
from .core.account_state import AccountState
from .core.benchmark_loader import BenchmarkLoader
from .core.cache_manager import CacheManager
from .core.data_loader import DataLoader
from .core.metrics_calculator import MetricsCalculator
from .core.pdf_generator import PDFReportGenerator


class MultiAccountReportAgent:
    def __init__(self, config: dict | None = None):
        self.config = {**CONFIG, **(config or {})}
        self.data_loader = DataLoader(self.config["data_dir"])
        self.cache_manager = CacheManager(self.config["cache_dir"])
        bench_cfg = self.config.get("benchmarks", {})
        self.benchmark_loader = BenchmarkLoader(
            cache_dir=self.config["cache_dir"],
            symbols=bench_cfg.get("symbols"),
            api_key=bench_cfg.get("api_key", ""),
            enabled=bool(bench_cfg.get("enabled", True)),
        )
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
                base_url=llm_cfg.get("base_url", ""),
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
        date = self.cache_manager.normalize_date(date)
        data_dir = data_dir or self.config["data_dir"]
        self.data_loader = DataLoader(data_dir)

        account_data = self.data_loader.load_account_data(account_id, date)
        account_info = account_data.get("account", {})
        deals_df = account_data.get("deals", pd.DataFrame())
        positions_df = account_data.get("positions", pd.DataFrame())
        positions_df = self._stocks_only(positions_df)
        deals_df = self._stocks_only(deals_df)
        initial_capital = float(self.config["initial_capital"].get(account_id, 0.0))
        account_info = dict(account_info)
        account_info["stock_mv"] = float(positions_df.get("市值", pd.Series(dtype=float)).sum())

        # Idempotency on same-day reruns:
        # - If a previous date exists, always rebuild today from that previous snapshot.
        # - If only today's cache exists, reuse it without replaying today's deals.
        existing_today = self.cache_manager.load_state(account_id, date)
        prev_date = self.cache_manager.get_previous_date(account_id, date)
        prev_state = self.cache_manager.load_state(account_id, prev_date) if prev_date else None

        should_update = True
        if prev_state is not None:
            state = prev_state
        elif existing_today is not None:
            state = existing_today
            should_update = False
        else:
            restored = self.cache_manager.load_or_seed(account_id, date)
            if restored is None:
                state = AccountState(account_id=account_id, initial_capital=initial_capital)
            elif isinstance(restored, AccountState):
                state = restored
            else:
                state = AccountState.from_dict(restored) if isinstance(restored, dict) else AccountState.from_seed(account_id, restored, initial_capital)
        # 以 config 入金为准，避免历史缓存里的旧本金把净值算偏
        state.initial_capital = initial_capital

        if self.config.get("account_types", {}).get(account_id, self.config.get("default_asset_type", "stock")) == "stock":
            asset_type = "stock"
        else:
            asset_type = self.config.get("default_asset_type", "stock")

        if should_update:
            state.update(date, account_info, deals_df, positions_df)

        metrics = MetricsCalculator.calculate(state)
        report_dir = Path(self.config["output_dir"])
        report_dir.mkdir(parents=True, exist_ok=True)
        account_name = self.config.get("account_names", {}).get(account_id, account_id)
        safe_name = re.sub(r"[\\/:*?\"<>|]", "_", str(account_name)).strip() or account_id
        output_path = report_dir / f"股票实盘复盘报告_{safe_name}_{date}.pdf"

        self.cache_manager.save_state(account_id, date, state)

        report = PDFReportGenerator(str(output_path), account_name)
        benchmarks = self.benchmark_loader.get_normalized_series(metrics["nav_series"])
        report.add_nav_and_metrics(
            metrics["nav_series"],
            metrics,
            initial_capital,
            float(positions_df.get("市值", pd.Series(dtype=float)).sum()),
            benchmarks=benchmarks,
        )
        trade_result = TradeAnalysis().analyze(state, self.config)
        trade_result["initial_capital"] = initial_capital
        llm_results = None
        if self.llm_module is not None:
            llm_results = {
                "trade": self.llm_module.analyze_trade(state, trade_result),
                "positions": self.llm_module.analyze_positions(state, positions_df),
            }
        report.add_stock_review(trade_result, deals_df, positions_df, llm_results)

        report.save()
        return str(output_path)

    @staticmethod
    def _calculate_realized_trade_pnl(deals_df: pd.DataFrame) -> float:
        if deals_df is None or deals_df.empty:
            return 0.0
        filtered = deals_df.copy()
        if "证券代码" in filtered.columns:
            codes = filtered["证券代码"].astype(str).str.split(".").str[0].str.zfill(6)
            etf_prefixes = ("15", "16", "50", "51", "52", "56", "58")
            filtered = filtered[~codes.str.startswith(etf_prefixes)].copy()
        if "证券代码" in filtered.columns:
            repo_mask = filtered["证券代码"].astype(str).str.split(".").str[0].str.zfill(6).str.startswith(("204", "1318"))
            filtered = filtered[~repo_mask].copy()
        if "操作" not in filtered.columns or "成交金额" not in filtered.columns:
            return 0.0

        buy_mask = filtered["操作"].astype(str).str.contains("买入|BUY|B", na=False)
        sell_mask = filtered["操作"].astype(str).str.contains("卖出|SELL|S", na=False)
        buy_amount = float(pd.to_numeric(filtered.loc[buy_mask, "成交金额"], errors="coerce").fillna(0.0).sum())
        sell_amount = float(pd.to_numeric(filtered.loc[sell_mask, "成交金额"], errors="coerce").fillna(0.0).sum())
        return sell_amount - buy_amount

    @staticmethod
    def _calculate_reverse_repo_interest(deals_df: pd.DataFrame) -> float:
        if deals_df is None or deals_df.empty:
            return 0.0
        filtered = deals_df.copy()
        if "证券代码" in filtered.columns:
            codes = filtered["证券代码"].astype(str).str.split(".").str[0].str.zfill(6)
            etf_prefixes = ("15", "16", "50", "51", "52", "56", "58")
            filtered = filtered[~codes.str.startswith(etf_prefixes)].copy()
        if filtered.empty:
            return 0.0

        repo_mask = pd.Series(False, index=filtered.index)
        if "证券代码" in filtered.columns:
            repo_mask |= filtered["证券代码"].astype(str).str.split(".").str[0].str.zfill(6).str.startswith(("204", "1318"))
        if "操作" in filtered.columns:
            repo_mask |= filtered["操作"].astype(str).str.contains("回购|逆回购", case=False, na=False)
        repo = filtered[repo_mask].copy()
        if repo.empty:
            return 0.0

        principal = pd.to_numeric(repo.get("成交金额", pd.Series(0.0, index=repo.index)), errors="coerce").fillna(0.0)
        annual_rate = pd.to_numeric(repo.get("成交价格", pd.Series(0.0, index=repo.index)), errors="coerce").fillna(0.0)
        dates = repo.get("成交日期", pd.Series("", index=repo.index)).astype(str)
        day_counts = []
        for value in dates:
            text = str(value).strip()
            try:
                if len(text) >= 8 and text.isdigit():
                    dt = pd.to_datetime(text, format="%Y%m%d")
                    day_counts.append(1.0)
                else:
                    day_counts.append(1.0)
            except Exception:
                day_counts.append(1.0)
        day_counts = pd.Series(day_counts, index=repo.index, dtype=float)
        return float(((principal * (annual_rate / 100.0) * day_counts / 365.0).sum()))

    @staticmethod
    def _stocks_only(frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty or "证券代码" not in frame.columns:
            return frame
        filtered = frame.copy()
        codes = filtered["证券代码"].astype(str).str.split(".").str[0].str.zfill(6)
        etf_prefixes = ("15", "16", "50", "51", "52", "56", "58")
        return filtered[~codes.str.startswith(etf_prefixes)].copy()

    @staticmethod
    def _exclude_repurchase(frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty or "证券代码" not in frame.columns:
            return frame
        filtered = frame.copy()
        codes = filtered["证券代码"].astype(str).str.split(".").str[0].str.zfill(6)
        operations = filtered.get("操作", pd.Series("", index=filtered.index)).astype(str)
        repurchase = operations.str.contains("回购|逆回购", case=False, na=False) | codes.str.startswith(("204", "1318"))
        return filtered[~repurchase].copy()

    def generate_all(self, date: str | None = None, data_dir: str | None = None) -> List[str]:
        date = date or pd.Timestamp.today().strftime("%Y%m%d")
        account_ids = list(self.config.get("initial_capital", {}).keys())
        outputs = []
        for account_id in account_ids:
            outputs.append(self.generate_for_account(account_id, date, data_dir=data_dir))
        return outputs
