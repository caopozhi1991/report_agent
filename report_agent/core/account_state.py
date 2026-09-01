from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd


def normalize_date_key(value: object) -> str:
    """统一为 YYYYMMDD，避免 2026-07-20 与 20260720 混用导致对齐失败。"""
    text = str(value).strip().replace("-", "").replace("/", "").replace(".", "")
    if len(text) >= 8 and text[:8].isdigit():
        return text[:8]
    return str(value)


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
        cash_balance: float | None = None,
        repo_positions: List[Dict[str, Any]] | None = None,
        cash_ledger: Dict[str, List[Dict[str, Any]]] | None = None,
        base_total_equity: float | None = None,
        current_stock_mv: float = 0.0,
        current_repo_mv: float = 0.0,
        peak_nav: float | None = None,
        peak_date: str | None = None,
    ):
        self.account_id = account_id
        self.initial_capital = float(initial_capital)
        self.nav_history = self._normalize_nav_history(nav_history)
        self.position_history = {normalize_date_key(k): v for k, v in (position_history or {}).items()}
        self.trade_history = {normalize_date_key(k): v for k, v in (trade_history or {}).items()}
        self.current_positions = current_positions if current_positions is not None else pd.DataFrame()
        self.current_profit = float(current_profit)
        self.current_asset = float(current_asset)
        self.cash_balance = float(cash_balance) if cash_balance is not None else float(self.initial_capital)
        self.repo_positions = self._normalize_repo_positions(repo_positions)
        self.cash_ledger = {normalize_date_key(k): list(v) for k, v in (cash_ledger or {}).items()}
        self.current_stock_mv = float(current_stock_mv)
        self.current_repo_mv = float(current_repo_mv)
        self.base_total_equity = self._resolve_base_total_equity(base_total_equity)
        self.peak_nav = float(peak_nav) if peak_nav is not None else (float(self.nav_history.max()) if not self.nav_history.empty else 1.0)
        self.peak_date = normalize_date_key(peak_date) if peak_date is not None else (str(self.nav_history.idxmax()) if not self.nav_history.empty else "")

    @staticmethod
    def _normalize_nav_history(nav_history: pd.Series | None) -> pd.Series:
        if nav_history is None or (isinstance(nav_history, pd.Series) and nav_history.empty):
            return pd.Series(dtype=float)
        series = nav_history if isinstance(nav_history, pd.Series) else pd.Series(nav_history, dtype=float)
        normalized = pd.Series(
            {normalize_date_key(k): float(v) for k, v in series.items()},
            dtype=float,
        )
        return normalized.groupby(level=0).last().sort_index()

    def _resolve_base_total_equity(self, base_total_equity: float | None) -> float:
        if base_total_equity is not None and float(base_total_equity) > 0:
            return float(base_total_equity)

        if self.current_asset > 0 and not self.nav_history.empty:
            latest_nav = float(self.nav_history.iloc[-1])
            if latest_nav > 0:
                return self.current_asset / latest_nav

        if self.initial_capital > 0:
            return self.initial_capital

        return max(float(self.current_asset), 1.0)

    @staticmethod
    def _normalize_repo_positions(repo_positions: List[Dict[str, Any]] | None) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for item in repo_positions or []:
            principal = float(item.get("principal", 0.0))
            if principal <= 0:
                continue
            normalized.append(
                {
                    "principal": principal,
                    "rate": float(item.get("rate", 0.0)),
                    "trade_date": normalize_date_key(item.get("trade_date", "")),
                    "maturity_date": normalize_date_key(item.get("maturity_date", "")),
                    "term_days": int(item.get("term_days", 1) or 1),
                    "security_code": str(item.get("security_code", "")),
                }
            )
        return normalized

    @staticmethod
    def _is_reverse_repo_trade(code: str, operation: str) -> bool:
        normalized_code = str(code).split(".")[0].zfill(6)
        text = str(operation)
        return normalized_code.startswith(("204", "1318")) or ("回购" in text or "逆回购" in text)

    @staticmethod
    def _parse_repo_term_days(code: str) -> int:
        normalized_code = str(code).split(".")[0].zfill(6)
        suffix = normalized_code[-3:]
        known = {"001": 1, "002": 2, "003": 3, "004": 4, "007": 7, "014": 14, "028": 28, "091": 91, "182": 182}
        return known.get(suffix, 1)

    @staticmethod
    def _add_days(date_key: str, days: int) -> str:
        try:
            return (pd.to_datetime(date_key, format="%Y%m%d") + pd.Timedelta(days=int(days))).strftime("%Y%m%d")
        except Exception:
            return date_key

    @staticmethod
    def _to_numeric(series_or_value: Any) -> float:
        if isinstance(series_or_value, pd.Series):
            return float(pd.to_numeric(series_or_value, errors="coerce").fillna(0.0).sum())
        try:
            return float(series_or_value)
        except (TypeError, ValueError):
            return 0.0

    def _record_cash_entry(self, entries: List[Dict[str, Any]], entry_type: str, amount: float, balance_after: float, date_key: str, note: str = "", security_code: str = ""):
        entries.append(
            {
                "date": normalize_date_key(date_key),
                "type": entry_type,
                "amount": float(amount),
                "balance_after": float(balance_after),
                "security_code": str(security_code),
                "note": str(note),
            }
        )

    def update(self, date: str, account_info: Dict[str, float], deals_df: pd.DataFrame, positions_df: pd.DataFrame):
        self.current_positions = positions_df.copy() if not positions_df.empty else pd.DataFrame()
        history_date = normalize_date_key(date)

        entries: List[Dict[str, Any]] = []
        remaining_repo_positions: List[Dict[str, Any]] = []
        for repo in self.repo_positions:
            if repo.get("maturity_date", "") <= history_date:
                principal = float(repo.get("principal", 0.0))
                term_days = int(repo.get("term_days", 1) or 1)
                rate = float(repo.get("rate", 0.0))
                interest = principal * (rate / 100.0) * term_days / 365.0
                self.cash_balance += principal
                self._record_cash_entry(entries, "repo_maturity_principal_in", principal, self.cash_balance, history_date, note="逆回购到期本金回款", security_code=repo.get("security_code", ""))
                self.cash_balance += interest
                self._record_cash_entry(entries, "repo_maturity_interest_in", interest, self.cash_balance, history_date, note="逆回购到期利息入账", security_code=repo.get("security_code", ""))
            else:
                remaining_repo_positions.append(repo)
        self.repo_positions = remaining_repo_positions

        if deals_df is not None and not deals_df.empty:
            trade_rows = deals_df.copy()
            for _, row in trade_rows.iterrows():
                operation = str(row.get("操作", ""))
                security_code = str(row.get("证券代码", ""))
                amount = self._to_numeric(row.get("成交金额", 0.0))
                if amount <= 0:
                    continue

                if self._is_reverse_repo_trade(security_code, operation):
                    term_days = self._parse_repo_term_days(security_code)
                    maturity_date = self._add_days(history_date, term_days)
                    rate = self._to_numeric(row.get("成交价格", 0.0))
                    self.cash_balance -= amount
                    self._record_cash_entry(entries, "repo_open_principal_out", -amount, self.cash_balance, history_date, note="逆回购成交，转入逆回购资产", security_code=security_code)
                    self.repo_positions.append(
                        {
                            "principal": amount,
                            "rate": rate,
                            "trade_date": history_date,
                            "maturity_date": maturity_date,
                            "term_days": term_days,
                            "security_code": security_code,
                        }
                    )
                    continue

                op_upper = operation.upper()
                if "买入" in operation or "BUY" in op_upper or op_upper == "B":
                    self.cash_balance -= amount
                    self._record_cash_entry(entries, "stock_buy_out", -amount, self.cash_balance, history_date, note="股票买入现金流出", security_code=security_code)
                elif "卖出" in operation or "SELL" in op_upper or op_upper == "S":
                    self.cash_balance += amount
                    self._record_cash_entry(entries, "stock_sell_in", amount, self.cash_balance, history_date, note="股票卖出现金流入", security_code=security_code)

        self.cash_ledger[history_date] = entries

        self.current_stock_mv = self._to_numeric(positions_df.get("市值", pd.Series(dtype=float))) if positions_df is not None else 0.0
        self.current_repo_mv = float(sum(float(item.get("principal", 0.0)) for item in self.repo_positions))
        self.current_asset = float(self.cash_balance + self.current_stock_mv + self.current_repo_mv)
        self.current_profit = float(self.current_asset - self.base_total_equity)

        current_nav = self.calculate_nav(history_date, total_asset=self.current_asset)
        self.nav_history.loc[history_date] = current_nav

        if self.peak_nav is None or current_nav > self.peak_nav:
            self.peak_nav = current_nav
            self.peak_date = history_date

        if not deals_df.empty:
            self.trade_history[history_date] = deals_df.copy()
        if not positions_df.empty:
            self.position_history[history_date] = positions_df.copy()

        return current_nav

    def calculate_nav(self, date: str, prev_total_asset: float | None = None, daily_profit: float | None = None, total_asset: float | None = None) -> float:
        if self.base_total_equity == 0:
            return 0.0
        current_total_asset = float(total_asset) if total_asset is not None else float(self.current_asset)
        if current_total_asset <= 0 and prev_total_asset is not None:
            current_total_asset = float(prev_total_asset) + float(daily_profit or 0.0)
        return current_total_asset / self.base_total_equity

    def get_previous_nav(self, date: str) -> float | None:
        if self.nav_history.empty:
            return None
        target = normalize_date_key(date)
        dates = sorted(str(d) for d in self.nav_history.index)
        for candidate in reversed(dates):
            if candidate < target:
                return float(self.nav_history.loc[candidate])
        return None

    def get_return(self, date: str) -> float:
        if self.nav_history.empty:
            return 0.0
        target = normalize_date_key(date)
        current_nav = float(self.nav_history.get(target, self.nav_history.iloc[-1]))
        prev_nav = self.get_previous_nav(target)
        if prev_nav is None or prev_nav == 0:
            return 0.0
        return current_nav / prev_nav - 1.0

    def get_drawdown(self, date: str) -> float:
        nav_series = self.nav_history.sort_index()
        if nav_series.empty:
            return 0.0
        target = normalize_date_key(date)
        current_nav = float(nav_series.get(target, nav_series.iloc[-1]))
        peak_val = float(nav_series.loc[:target].max()) if not nav_series.empty else current_nav
        if peak_val == 0:
            return 0.0
        return (current_nav - peak_val) / peak_val

    def to_dict(self) -> Dict[str, Any]:
        return {
            "account_id": self.account_id,
            "initial_capital": self.initial_capital,
            "nav_history": self.nav_history.to_dict() if not self.nav_history.empty else {},
            "position_history": {normalize_date_key(k): v.to_dict(orient="records") for k, v in self.position_history.items()},
            "trade_history": {normalize_date_key(k): v.to_dict(orient="records") for k, v in self.trade_history.items()},
            "current_positions": self.current_positions.to_dict(orient="records") if not self.current_positions.empty else [],
            "current_profit": self.current_profit,
            "current_asset": self.current_asset,
            "cash_balance": self.cash_balance,
            "repo_positions": self.repo_positions,
            "cash_ledger": self.cash_ledger,
            "base_total_equity": self.base_total_equity,
            "current_stock_mv": self.current_stock_mv,
            "current_repo_mv": self.current_repo_mv,
            "peak_nav": self.peak_nav,
            "peak_date": normalize_date_key(self.peak_date) if self.peak_date else "",
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
            cash_balance=payload.get("cash_balance"),
            repo_positions=payload.get("repo_positions", []),
            cash_ledger=payload.get("cash_ledger", {}),
            base_total_equity=payload.get("base_total_equity"),
            current_stock_mv=payload.get("current_stock_mv", 0.0),
            current_repo_mv=payload.get("current_repo_mv", 0.0),
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
            cash_balance=seed_data.get("cash_balance", initial_capital),
            repo_positions=seed_data.get("repo_positions", []),
            cash_ledger=seed_data.get("cash_ledger", {}),
            base_total_equity=seed_data.get("base_total_equity", initial_capital),
            current_stock_mv=float(seed_data.get("stock_mv", 0.0)),
            current_repo_mv=float(seed_data.get("repo_mv", 0.0)),
            peak_nav=seed_data.get("peak_nav", float(pd.Series(nav_history, dtype=float).max()) if nav_history else 1.0),
            peak_date=seed_data.get("peak_date", str(sorted(nav_history.keys())[-1]) if nav_history else ""),
        )
        if state.nav_history.empty:
            state.nav_history = pd.Series(
                {normalize_date_key(seed_data.get("date", "")): float(seed_data.get("nav", 1.0))},
                dtype=float,
            )
        return state
