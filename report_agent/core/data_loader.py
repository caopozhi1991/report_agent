from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pandas as pd


class DataLoader:
    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def load_account_data(self, account_id: str, date: str) -> Dict[str, Any]:
        account_file = self._find_input_file(account_id, "account")
        deals_file = self._find_input_file(account_id, "deals")
        positions_file = self._find_input_file(account_id, "positions")

        account_raw = self._read_csv(account_file)
        deals_df = self._normalize_deals(self._read_csv(deals_file))
        positions_df = self._normalize_positions(self._read_csv(positions_file))

        account_info = self._extract_account_info(account_raw)
        return {
            "account": account_info,
            "deals": deals_df,
            "positions": positions_df,
        }

    def _read_csv(self, file_path: Path) -> pd.DataFrame:
        if not file_path.exists():
            return pd.DataFrame()
        for encoding in ("utf-8-sig", "gb18030", "utf-8"):
            try:
                return pd.read_csv(file_path, encoding=encoding)
            except UnicodeDecodeError:
                continue
        return pd.read_csv(file_path)

    def _find_input_file(self, account_id: str, suffix: str) -> Path:
        direct = self.data_dir / f"{account_id}_{suffix}.csv"
        if direct.exists():
            return direct
        candidates = sorted(self.data_dir.glob(f"{account_id}_*_{suffix}.csv"))
        return candidates[0] if candidates else direct

    def _extract_account_info(self, account_df: pd.DataFrame) -> Dict[str, float]:
        if account_df.empty:
            return {
                "total_asset": 0.0,
                "available_cash": 0.0,
                "stock_mv": 0.0,
                "profit": 0.0,
            }

        row = account_df.iloc[0].copy()
        mapper = {
            "total_asset": ["total_asset", "总资产", "资产总额", "net_asset_value"],
            "available_cash": ["available_cash", "可用资金", "现金", "available_cash_balance"],
            "stock_mv": ["stock_mv", "股票市值", "持仓市值", "stock_market_value"],
            "profit": ["profit", "盈亏", "浮动盈亏", "profit_loss"],
        }
        normalized = {}
        for key, aliases in mapper.items():
            for alias in aliases:
                candidate = self._find_column_name(row, alias)
                if candidate is not None:
                    normalized[key] = self._to_float(row[candidate])
                    break
            if key not in normalized:
                normalized[key] = 0.0

        return {
            "total_asset": float(normalized.get("total_asset", 0.0)),
            "available_cash": float(normalized.get("available_cash", 0.0)),
            "stock_mv": float(normalized.get("stock_mv", 0.0)),
            "profit": float(normalized.get("profit", 0.0)),
        }

    def _find_column_name(self, row: pd.Series, alias: str):
        alias_lower = alias.lower().replace(" ", "")
        for col in row.index:
            if str(col).strip().lower().replace(" ", "") == alias_lower:
                return col
        for col in row.index:
            if alias_lower in str(col).strip().lower().replace(" ", ""):
                return col
        return None

    def _normalize_deals(self, deals_df: pd.DataFrame) -> pd.DataFrame:
        if deals_df.empty:
            return pd.DataFrame(columns=["证券代码", "操作", "成交价格", "成交数量", "成交金额"])

        renamed = deals_df.rename(
            columns={
                "证券代码": "证券代码",
                "code": "证券代码",
                "股票代码": "证券代码",
                "symbol": "证券代码",
                "security_code": "证券代码",
                "操作": "操作",
                "trade_type": "操作",
                "direction": "操作",
                "成交价格": "成交价格",
                "price": "成交价格",
                "成交数量": "成交数量",
                "quantity": "成交数量",
                "成交金额": "成交金额",
                "amount": "成交金额",
                "trade_amount": "成交金额",
            }
        )

        for column in ["证券代码", "操作", "成交价格", "成交数量", "成交金额"]:
            if column not in renamed.columns:
                continue
            if column == "操作":
                renamed[column] = renamed[column].astype(str).str.strip()
                renamed[column] = renamed[column].str.replace("买入", "买入").str.replace("卖出", "卖出")
                renamed[column] = renamed[column].str.upper().replace({"BUY": "买入", "SELL": "卖出", "B": "买入", "S": "卖出"})
            else:
                renamed[column] = pd.to_numeric(renamed[column], errors="coerce")

        final = renamed[[col for col in ["证券代码", "操作", "成交价格", "成交数量", "成交金额"] if col in renamed.columns]]
        final = final.copy()
        if "操作" in final.columns:
            final["操作"] = final["操作"].fillna("")
        return final

    def _normalize_positions(self, positions_df: pd.DataFrame) -> pd.DataFrame:
        if positions_df.empty:
            return pd.DataFrame(columns=["证券代码", "当前拥股", "成本价", "市值", "盈亏"])

        renamed = positions_df.rename(
            columns={
                "证券代码": "证券代码",
                "code": "证券代码",
                "股票代码": "证券代码",
                "symbol": "证券代码",
                "当前拥股": "当前拥股",
                "持仓数量": "当前拥股",
                "quantity": "当前拥股",
                "成本价": "成本价",
                "avg_cost": "成本价",
                "成本": "成本价",
                "市值": "市值",
                "market_value": "市值",
                "盈亏": "盈亏",
                "profit_loss": "盈亏",
                "浮动盈亏": "盈亏",
            }
        )

        for column in ["当前拥股", "成本价", "市值", "盈亏"]:
            if column in renamed.columns:
                renamed[column] = pd.to_numeric(renamed[column], errors="coerce")

        final = renamed[[col for col in ["证券代码", "当前拥股", "成本价", "市值", "盈亏"] if col in renamed.columns]]
        return final

    def _to_float(self, value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
