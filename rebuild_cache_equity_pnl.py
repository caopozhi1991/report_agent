from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd

from report_agent.config import CONFIG
from report_agent.core.account_state import AccountState, normalize_date_key

ETF_PREFIXES = ("15", "16", "50", "51", "52", "56", "58")


def normalize_code(value: object) -> str:
    digits = re.sub(r"\D", "", str(value).split(".")[0])
    return digits.zfill(6)


def stocks_only(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "证券代码" not in frame.columns:
        return frame.copy()
    filtered = frame.copy()
    codes = filtered["证券代码"].astype(str).map(normalize_code)
    return filtered.loc[~codes.str.startswith(ETF_PREFIXES)].copy()


def date_keys_from_payload(payload: dict) -> list[str]:
    keys = set()
    for source in (payload.get("trade_history", {}), payload.get("position_history", {})):
        for key in source.keys():
            norm = normalize_date_key(key)
            if norm.isdigit() and len(norm) == 8:
                keys.add(norm)
    return sorted(keys)


def load_latest_payload(account_dir: Path) -> tuple[dict, Path]:
    files = sorted(p for p in account_dir.glob("*.json") if p.stem.isdigit())
    if not files:
        raise RuntimeError(f"No cache files found under {account_dir}")
    latest = files[-1]
    return json.loads(latest.read_text(encoding="utf-8")), latest


def is_account_cache_dir(path: Path) -> bool:
    if not path.is_dir():
        return False
    return any(p.stem.isdigit() for p in path.glob("*.json"))


def rebuild_account(account_id: str, source_root: Path, target_root: Path) -> dict:
    source_dir = source_root / account_id
    payload, source_file = load_latest_payload(source_dir)

    initial_capital = float(CONFIG.get("initial_capital", {}).get(account_id, payload.get("initial_capital", 0.0)))
    if initial_capital <= 0:
        raise RuntimeError(f"Invalid initial capital for account {account_id}")

    trade_history = payload.get("trade_history", {}) or {}
    position_history = payload.get("position_history", {}) or {}
    dates = date_keys_from_payload(payload)
    if not dates:
        raise RuntimeError(f"No trade/position history in source cache for account {account_id}")

    state = AccountState(
        account_id=account_id,
        initial_capital=initial_capital,
        base_total_equity=initial_capital,
        cash_balance=initial_capital,
        equity_model_version=2,
    )

    account_out = target_root / account_id
    account_out.mkdir(parents=True, exist_ok=True)

    for day in dates:
        deals_df = pd.DataFrame(trade_history.get(day, []) or [])
        positions_df = pd.DataFrame(position_history.get(day, []) or [])
        deals_df = stocks_only(deals_df)
        positions_df = stocks_only(positions_df)

        state.update(day, {}, deals_df, positions_df)
        state.trade_history[day] = deals_df.copy()
        state.position_history[day] = positions_df.copy()

        out_file = account_out / f"{day}.json"
        out_file.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "account_id": account_id,
        "source": str(source_file),
        "target_dir": str(account_out),
        "dates": len(dates),
        "first_date": dates[0],
        "last_date": dates[-1],
        "last_nav": float(state.nav_history.iloc[-1]) if not state.nav_history.empty else 1.0,
        "last_asset": float(state.current_asset),
        "cash_balance": float(state.cash_balance),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild cache using positions-PnL equity model (v2).")
    parser.add_argument("--account-id", default="", help="single account id; empty means all accounts under source cache")
    parser.add_argument("--source-cache", default=CONFIG["cache_dir"], help="source cache root")
    parser.add_argument("--target-cache", default="cache_v2", help="target cache root")
    args = parser.parse_args()

    source_root = Path(args.source_cache)
    target_root = Path(args.target_cache)
    target_root.mkdir(parents=True, exist_ok=True)

    if args.account_id:
        account_ids = [str(args.account_id)]
    else:
        account_ids = sorted(p.name for p in source_root.iterdir() if is_account_cache_dir(p))

    if not account_ids:
        raise RuntimeError(f"No account directories under {source_root}")

    for account_id in account_ids:
        result = rebuild_account(account_id, source_root, target_root)
        print(
            "REBUILT",
            result["account_id"],
            "source=",
            result["source"],
            "target_dir=",
            result["target_dir"],
            "dates=",
            result["dates"],
            "range=",
            f"{result['first_date']}->{result['last_date']}",
            "last_nav=",
            result["last_nav"],
            "last_asset=",
            result["last_asset"],
            "cash=",
            result["cash_balance"],
        )


if __name__ == "__main__":
    main()
