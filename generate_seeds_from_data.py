from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from report_agent.config import CONFIG
from report_agent.core.data_loader import DataLoader


ETF_PREFIXES = ("15", "16", "50", "51", "52", "56", "58")


def normalize_date(value: object) -> str:
    text = str(value).strip().replace("-", "").replace("/", "")
    if len(text) >= 8 and text[:8].isdigit():
        return text[:8]
    return ""


def stocks_only(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "证券代码" not in frame.columns:
        return frame.copy()
    filtered = frame.copy()
    codes = filtered["证券代码"].astype(str).str.split(".").str[0].str.zfill(6)
    return filtered[~codes.str.startswith(ETF_PREFIXES)].copy()


def safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_seed(account_id: str) -> dict:
    data_dir = Path(CONFIG["data_dir"])
    loader = DataLoader(str(data_dir))

    account_file = loader._find_input_file(account_id, "account")
    deals_file = loader._find_input_file(account_id, "deals")
    positions_file = loader._find_input_file(account_id, "positions")

    account_raw = loader._read_csv(account_file)
    deals_df = stocks_only(loader._normalize_deals(loader._read_csv(deals_file)))
    positions_df = stocks_only(loader._normalize_positions(loader._read_csv(positions_file)))
    if not positions_df.empty and "证券代码" in positions_df.columns:
        positions_df = positions_df.copy()
        positions_df["证券代码"] = (
            positions_df["证券代码"].astype(str).str.split(".").str[0].str.replace(r"\D", "", regex=True).str.zfill(6)
        )

    account_info = loader._extract_account_info(account_raw)
    trade_date = ""
    if not account_raw.empty and "交易日" in account_raw.columns:
        trade_date = normalize_date(account_raw.iloc[0].get("交易日", ""))
    if not trade_date and not deals_df.empty and "成交日期" in deals_df.columns:
        date_series = deals_df["成交日期"].astype(str).map(normalize_date)
        trade_date = max([d for d in date_series if d], default="")
    if not trade_date:
        trade_date = pd.Timestamp.today().strftime("%Y%m%d")

    initial_capital = safe_float(CONFIG.get("initial_capital", {}).get(account_id, 0.0), 0.0)
    total_asset = safe_float(account_info.get("total_asset", 0.0), 0.0)
    stock_mv = safe_float(positions_df.get("市值", pd.Series(dtype=float)).sum(), 0.0)
    available_cash = safe_float(account_info.get("available_cash", 0.0), 0.0)
    seed_cash = initial_capital if initial_capital > 0 else available_cash
    profit = safe_float(account_info.get("profit", total_asset - initial_capital), total_asset - initial_capital)

    nav = (total_asset / initial_capital) if initial_capital else 1.0
    nav = safe_float(nav, 1.0)

    seed = {
        "account_id": account_id,
        "date": trade_date,
        "total_asset": total_asset,
        "profit": profit,
        "stock_mv": stock_mv,
        "nav": nav,
        "peak_nav": nav,
        "peak_date": trade_date,
        "initial_capital": initial_capital,
        "positions": positions_df.to_dict(orient="records") if not positions_df.empty else [],
        "nav_history": {trade_date: nav},
        "cash_balance": seed_cash,
        "repo_positions": [],
        "cash_ledger": {
            trade_date: [
                {
                    "date": trade_date,
                    "type": "seed_init",
                    "amount": 0.0,
                    "balance_after": seed_cash,
                    "security_code": "",
                    "note": "from data csv",
                }
            ]
        },
        "base_total_equity": initial_capital if initial_capital else max(total_asset, 1.0),
        "repo_mv": 0.0,
        "equity_model_version": 2,
    }
    return seed


def main() -> None:
    seeds_root = Path("seeds")
    account_ids = list(CONFIG.get("initial_capital", {}).keys())
    for account_id in account_ids:
        seed = build_seed(account_id)
        target = seeds_root / account_id / "seed.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(seed, ensure_ascii=False, indent=2), encoding="utf-8")
        print(
            "UPDATED",
            target,
            "date=",
            seed["date"],
            "nav=",
            round(float(seed["nav"]), 8),
            "positions=",
            len(seed["positions"]),
        )


if __name__ == "__main__":
    main()
