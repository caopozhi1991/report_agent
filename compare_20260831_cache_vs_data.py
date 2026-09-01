from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import pandas as pd


TARGET = "20260831"
ACCOUNTS = ["1206016764", "1219020189"]
ETF_PREFIXES = ("15", "16", "50", "51", "52", "56", "58")


def read_csv_fallback(path: Path) -> pd.DataFrame:
    for enc in ("utf-8-sig", "gb18030", "utf-8", "gbk"):
        try:
            return pd.read_csv(path, encoding=enc)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(path)


def norm_code(value: object) -> str:
    return re.sub(r"\D", "", str(value).split(".")[0]).zfill(6)


def stocks_only(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "证券代码" not in df.columns:
        return df.copy()
    out = df.copy()
    codes = out["证券代码"].astype(str).map(norm_code)
    return out[~codes.str.startswith(ETF_PREFIXES)].copy()


def normalize_trades(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["证券代码", "操作", "成交价格", "成交数量", "成交金额", "成交日期"])

    out = df.rename(
        columns={
            "code": "证券代码",
            "股票代码": "证券代码",
            "symbol": "证券代码",
            "security_code": "证券代码",
            "trade_type": "操作",
            "direction": "操作",
            "price": "成交价格",
            "quantity": "成交数量",
            "amount": "成交金额",
            "trade_amount": "成交金额",
            "成 交价格": "成交价格",
        }
    )

    for col in ["证券代码", "操作", "成交价格", "成交数量", "成交金额", "成交日期"]:
        if col not in out.columns:
            out[col] = None

    out["证券代码"] = out["证券代码"].astype(str).map(norm_code)
    out["操作"] = out["操作"].astype(str).str.strip()
    out["成交价格"] = pd.to_numeric(out["成交价格"], errors="coerce").fillna(0.0)
    out["成交数量"] = pd.to_numeric(out["成交数量"], errors="coerce").fillna(0).astype(int)
    out["成交金额"] = pd.to_numeric(out["成交金额"], errors="coerce").fillna(0.0)
    out["成交日期"] = out["成交日期"].astype(str).str.replace(r"\D", "", regex=True).str[:8]

    out = out[out["成交日期"] == TARGET].copy()
    out = stocks_only(out)
    return out[["证券代码", "操作", "成交价格", "成交数量", "成交金额"]].reset_index(drop=True)


def normalize_positions(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["证券代码", "当前拥股", "成本价", "市值", "盈亏"])

    out = df.rename(
        columns={
            "code": "证券代码",
            "股票代码": "证券代码",
            "symbol": "证券代码",
            "持仓数量": "当前拥股",
            "quantity": "当前拥股",
            "avg_cost": "成本价",
            "成本": "成本价",
            "market_value": "市值",
            "profit_loss": "盈亏",
            "浮动盈亏": "盈亏",
        }
    )

    for col in ["证券代码", "当前拥股", "成本价", "市值", "盈亏"]:
        if col not in out.columns:
            out[col] = 0

    out["证券代码"] = out["证券代码"].astype(str).map(norm_code)
    for col in ["当前拥股", "成本价", "市值", "盈亏"]:
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)

    out = out[out["当前拥股"] > 0].copy()
    out = stocks_only(out)
    return out[["证券代码", "当前拥股", "成本价", "市值", "盈亏"]].reset_index(drop=True)


def to_counter(df: pd.DataFrame, kind: str) -> Counter:
    rows = []
    if kind == "trade":
        for _, row in df.iterrows():
            rows.append(
                (
                    row["证券代码"],
                    str(row["操作"]).strip(),
                    round(float(row["成交价格"]), 3),
                    int(row["成交数量"]),
                    round(float(row["成交金额"]), 2),
                )
            )
    else:
        for _, row in df.iterrows():
            rows.append(
                (
                    row["证券代码"],
                    int(round(float(row["当前拥股"]))),
                    round(float(row["成本价"]), 3),
                    round(float(row["市值"]), 2),
                    round(float(row["盈亏"]), 2),
                )
            )
    return Counter(rows)


def compare_account(account_id: str) -> None:
    data_dir = Path("data")
    cache_file = Path("cache") / account_id / "20260831.json"

    deals_file = sorted(data_dir.glob(f"{account_id}_*_deals.csv"))[0]
    positions_file = sorted(data_dir.glob(f"{account_id}_*_positions.csv"))[0]

    data_trades = normalize_trades(read_csv_fallback(deals_file))
    data_positions = normalize_positions(read_csv_fallback(positions_file))

    payload = json.loads(cache_file.read_text(encoding="utf-8"))
    cache_trades = pd.DataFrame(payload.get("trade_history", {}).get(TARGET, []))
    if not cache_trades.empty:
        cache_trades["成交日期"] = TARGET
    cache_trades = normalize_trades(cache_trades)
    cache_positions = normalize_positions(pd.DataFrame(payload.get("position_history", {}).get(TARGET, [])))

    tr_data = to_counter(data_trades, "trade")
    tr_cache = to_counter(cache_trades, "trade")
    po_data = to_counter(data_positions, "position")
    po_cache = to_counter(cache_positions, "position")

    tr_missing = list((tr_data - tr_cache).elements())
    tr_extra = list((tr_cache - tr_data).elements())
    po_missing = list((po_data - po_cache).elements())
    po_extra = list((po_cache - po_data).elements())

    print("ACCOUNT", account_id)
    print("TRADE data_rows", len(data_trades), "cache_rows", len(cache_trades), "match", not tr_missing and not tr_extra)
    print("TRADE missing_in_cache", len(tr_missing), "extra_in_cache", len(tr_extra))
    if tr_missing:
        print("TRADE missing sample", tr_missing[:5])
    if tr_extra:
        print("TRADE extra sample", tr_extra[:5])

    print("POSITION data_rows", len(data_positions), "cache_rows", len(cache_positions), "match", not po_missing and not po_extra)
    print("POSITION missing_in_cache", len(po_missing), "extra_in_cache", len(po_extra))
    if po_missing:
        print("POSITION missing sample", po_missing[:5])
    if po_extra:
        print("POSITION extra sample", po_extra[:5])
    print("---")


if __name__ == "__main__":
    for account in ACCOUNTS:
        compare_account(account)
