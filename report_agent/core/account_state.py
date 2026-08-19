from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Dict

import pandas as pd


class AccountState:
    def __init__(
        self,
        account_id: str,
        initial_capital: float,
        nav_history: pd.Series | None = None,
        position_history: Dict[str, pd.DataFrame] | None = None,
        trade_history: Dict[str, pd.DataFrame] | None = None,
        current_positions: pd.DataFrame | None = None,
        current_profit: float = 0.0,
        current_asset: float = 0.0,
        peak_nav: float | None = None,
        peak_date: str | None = None,
    ):
        self.account_id = account_id
        self.initial_capital = float(initial_capital)
        self.nav_history = nav_history if nav_history is not None else pd.Series(dtype=float)
        self.position_history = position_history if position_history is not None else {}
        self.trade_history = trade_history if trade_history is not None else {}
        self.current_positions = current_positions if current_positions is not None else pd.DataFrame()
        self.current_profit = float(current_profit)
        self.current_asset = float(current_asset)
        self.peak_nav = float(peak_nav) if peak_nav is not None else (float(self.nav_history.max()) if not self.nav_history.empty else 1.0)
        self.peak_date = str(peak_date) if peak_date is not None else (str(self.nav_history.idxmax()) if not self.nav_history.empty else "")

    def update(self, date: str, account_info: Dict[str, float], deals_df: pd.DataFrame, positions_df: pd.DataFrame):
        self.current_positions = positions_df.copy() if not positions_df.empty else pd.DataFrame()
        self.current_profit = float(account_info.get("profit", 0.0))
        self.current_asset = float(account_info.get("total_asset", 0.0))

        history_date = str(date)
        prev_nav = self.get_previous_nav(date)

        if prev_nav is None:
            previous_total_asset = self.initial_capital
        else:
            previous_total_asset = prev_nav * self.initial_capital

        current_nav = self.calculate_nav(date, previous_total_asset, self.current_profit, self.current_asset)
        self.nav_history.loc[history_date] = current_nav

        if not deals_df.empty:
            self.trade_history[history_date] = deals_df.copy()
        if not positions_df.empty:
            self.position_history[history_date] = positions_df.copy()

        return current_nav

    def calculate_nav(self, date: str, prev_total_asset: float | None = None, daily_profit: float | None = None, total_asset: float | None = None) -> float:
        if prev_total_asset is None:
            prev_total_asset = self.initial_capital
        if daily_profit is None:
            daily_profit = self.current_profit
        if total_asset is None:
            total_asset = self.current_asset
        if self.initial_capital == 0:
            return 0.0
        if total_asset is not None and total_asset > 0:
            return total_asset / self.initial_capital
        return prev_total_asset / self.initial_capital

    def get_previous_nav(self, date: str) -> float | None:
        if self.nav_history.empty:
            return None
        dates = sorted(self.nav_history.index)
        for candidate in reversed(dates):
            if str(candidate) < str(date):
                return float(self.nav_history.loc[candidate])
        return None

    def get_return(self, date: str) -> float:
        if self.nav_history.empty:
            return 0.0
        current_nav = float(self.nav_history.get(str(date), self.nav_history.iloc[-1]))
        prev_nav = self.get_previous_nav(date)
        if prev_nav is None or prev_nav == 0:
            return 0.0
        return current_nav / prev_nav - 1.0

    def get_drawdown(self, date: str) -> float:
        nav_series = self.nav_history.sort_index()
        if nav_series.empty:
            return 0.0
        current_nav = float(nav_series.get(str(date), nav_series.iloc[-1]))
        peak_val = float(nav_series.loc[:str(date)].max()) if not nav_series.empty else current_nav
        if peak_val == 0:
            return 0.0
        return (current_nav - peak_val) / peak_val

    def to_dict(self) -> Dict[str, Any]:
        return {
            "account_id": self.account_id,
            "initial_capital": self.initial_capital,
            "nav_history": self.nav_history.to_dict() if not self.nav_history.empty else {},
            "position_history": {k: v.to_dict(orient="records") for k, v in self.position_history.items()},
            "trade_history": {k: v.to_dict(orient="records") for k, v in self.trade_history.items()},
            "current_positions": self.current_positions.to_dict(orient="records") if not self.current_positions.empty else [],
            "current_profit": self.current_profit,
            "current_asset": self.current_asset,
            "peak_nav": self.peak_nav,
            "peak_date": self.peak_date,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "AccountState":
        nav_history = pd.Series(payload.get("nav_history", {}), dtype=float)
        position_history = {
            k: pd.DataFrame(v) for k, v in payload.get("position_history", {}).items()
        }
        trade_history = {
            k: pd.DataFrame(v) for k, v in payload.get("trade_history", {}).items()
        }
        current_positions = pd.DataFrame(payload.get("current_positions", []))
        return cls(
            account_id=payload.get("account_id", ""),
            initial_capital=payload.get("initial_capital", 0.0),
            nav_history=nav_history,
            position_history=position_history,
            trade_history=trade_history,
            current_positions=current_positions,
            current_profit=payload.get("current_profit", 0.0),
            current_asset=payload.get("current_asset", 0.0),
            peak_nav=payload.get("peak_nav"),
            peak_date=payload.get("peak_date"),
        )

    @classmethod
    def from_seed(cls, account_id: str, seed_data: Dict[str, Any], initial_capital: float) -> "AccountState":
        nav_history = seed_data.get("nav_history", {})
        if not isinstance(nav_history, dict) or not nav_history:
            seed_date = str(seed_data.get("date", ""))
            seed_nav = float(seed_data.get("nav", 1.0))
            nav_history = {seed_date: seed_nav} if seed_date else {"19700101": 1.0}

        state = cls(
            account_id=account_id,
            initial_capital=float(initial_capital or seed_data.get("initial_capital", 0.0)),
            nav_history=pd.Series(nav_history, dtype=float),
            current_positions=pd.DataFrame(seed_data.get("positions", [])),
            current_profit=float(seed_data.get("profit", 0.0)),
            current_asset=float(seed_data.get("total_asset", 0.0)),
            peak_nav=seed_data.get("peak_nav", float(pd.Series(nav_history, dtype=float).max()) if nav_history else 1.0),
            peak_date=seed_data.get("peak_date", str(sorted(nav_history.keys())[-1]) if nav_history else ""),
        )
        if state.nav_history.empty:
            state.nav_history = pd.Series({str(seed_data.get("date", "")): float(seed_data.get("nav", 1.0))}, dtype=float)
        return state
