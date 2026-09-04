from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from report_agent.config import CONFIG
from report_agent.core.account_state import AccountState
from report_agent.core.data_loader import DataLoader

ETF_PREFIXES = ("15", "16", "50", "51", "52", "56", "58")


def stocks_only(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "证券代码" not in frame.columns:
        return frame.copy()
    filtered = frame.copy()
    codes = filtered["证券代码"].astype(str).str.split(".").str[0].str.replace(r"\D", "", regex=True).str.zfill(6)
    return filtered.loc[~codes.str.startswith(ETF_PREFIXES)].copy()


def snapshot_days(root: Path) -> list[str]:
    days: list[str] = []
    for p in root.iterdir():
        if not p.is_dir():
            continue
        name = p.name.strip()
        if len(name) == 8 and name.isdigit():
            days.append(name)
    return sorted(days)


def load_day_frames(day_dir: Path, account_id: str, loader: DataLoader) -> tuple[pd.DataFrame, pd.DataFrame]:
    deals_path = day_dir / f"{account_id}_2_deals.csv"
    positions_path = day_dir / f"{account_id}_2_positions.csv"

    deals_df = loader._normalize_deals(loader._read_csv(deals_path))
    positions_df = loader._normalize_positions(loader._read_csv(positions_path))

    deals_df = stocks_only(deals_df)
    positions_df = stocks_only(positions_df)
    return deals_df, positions_df


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def day_account_total(day_dir: Path, account_id: str, loader: DataLoader) -> float | None:
    account_path = day_dir / f"{account_id}_2_account.csv"
    account_raw = loader._read_csv(account_path)
    if account_raw.empty:
        return None
    account_info = loader._extract_account_info(account_raw)
    total_asset = float(account_info.get("total_asset", 0.0))
    return total_asset if total_asset else None


def old_cache_target_equity(account_id: str, old_cache: Path, target_day: str) -> float | None:
    old_file = old_cache / account_id / f"{target_day}.json"
    if not old_file.exists():
        return None
    payload = load_json(old_file)
    if "total_asset" in payload:
        try:
            return float(payload.get("total_asset", 0.0))
        except (TypeError, ValueError):
            return None
    nav = float(payload.get("nav_history", {}).get(target_day, 0.0) or 0.0)
    base = float(payload.get("base_total_equity", payload.get("initial_capital", 0.0)) or 0.0)
    if nav > 0 and base > 0:
        return nav * base
    return None


def merge_old_nav_history(account_id: str, old_cache: Path, start_day: str, nav_history: dict[str, float]) -> dict[str, float]:
    old_dir = old_cache / account_id
    if not old_dir.exists():
        return dict(sorted(nav_history.items()))

    merged = {}
    anchor_file = old_dir / f"{start_day}.json"
    if anchor_file.exists():
        payload = load_json(anchor_file)
        source_history = payload.get("nav_history", {}) or {}
        for day, value in source_history.items():
            day_key = str(day)
            if day_key.isdigit() and len(day_key) == 8 and day_key < start_day:
                merged[day_key] = float(value)
    else:
        for file_path in sorted(old_dir.glob("*.json")):
            day = file_path.stem
            if not (day.isdigit() and len(day) == 8 and day < start_day):
                continue
            payload = load_json(file_path)
            value = payload.get("nav_history", {}).get(day)
            if value is None and "nav" in payload:
                value = payload.get("nav")
            if value is None:
                continue
            merged[day] = float(value)

    merged.update({str(k): float(v) for k, v in nav_history.items()})
    return dict(sorted(merged.items()))


def alignment_target_for_account(account_id: str, root: Path, old_cache: Path, processed_days: list[str], payloads_by_day: dict[str, dict], loader: DataLoader) -> tuple[str, float] | None:
    if not processed_days:
        return None

    if account_id == "1219020189":
        target_day = processed_days[-1]
        total_asset = day_account_total(root / target_day, account_id, loader)
        if total_asset is None:
            return None
        return target_day, float(total_asset)

    if account_id == "1206016764":
        target_day = processed_days[0]
        total_asset = old_cache_target_equity(account_id, old_cache, target_day)
        if total_asset is None:
            return None
        return target_day, float(total_asset)

    return None


def apply_constant_equity_offset(payloads_by_day: dict[str, dict], offset: float, base_total_equity: float) -> None:
    if abs(offset) < 1e-12:
        return

    for day, payload in payloads_by_day.items():
        payload["cash_balance"] = float(payload.get("cash_balance", 0.0)) + offset
        payload["current_asset"] = float(payload.get("current_asset", 0.0)) + offset
        payload["current_profit"] = float(payload["current_asset"] - base_total_equity)

        cash_ledger = payload.get("cash_ledger", {}) or {}
        day_entries = cash_ledger.get(day, []) or []
        shifted_entries = []
        for entry in day_entries:
            updated = dict(entry)
            updated["balance_after"] = float(updated.get("balance_after", 0.0)) + offset
            shifted_entries.append(updated)
        cash_ledger[day] = shifted_entries
        payload["cash_ledger"] = cash_ledger


def refresh_nav_history(payloads_by_day: dict[str, dict], base_total_equity: float) -> None:
    running_nav = {}
    for day in sorted(payloads_by_day):
        payload = payloads_by_day[day]
        running_nav[day] = float(payload.get("current_asset", 0.0)) / base_total_equity if base_total_equity else 0.0
        payload["nav_history"] = dict(sorted(running_nav.items()))
        series = pd.Series(payload["nav_history"], dtype=float)
        payload["peak_nav"] = float(series.max()) if not series.empty else 1.0
        payload["peak_date"] = str(series.idxmax()) if not series.empty else ""


def rebuild_account(account_id: str, root: Path, target_cache: Path, old_cache: Path, stitch_before: str) -> dict:
    days = snapshot_days(root)
    if not days:
        raise RuntimeError(f"No day snapshot folders found under {root}")

    init_cap = float(CONFIG.get("initial_capital", {}).get(account_id, 0.0))
    if init_cap <= 0:
        raise RuntimeError(f"Invalid initial capital for account {account_id}")

    state = AccountState(
        account_id=account_id,
        initial_capital=init_cap,
        base_total_equity=init_cap,
        cash_balance=init_cap,
        equity_model_version=2,
    )

    out_dir = target_cache / account_id
    out_dir.mkdir(parents=True, exist_ok=True)

    loader = DataLoader(str(root))

    processed = []
    payloads_by_day: dict[str, dict] = {}
    for day in days:
        day_dir = root / day
        deals_df, positions_df = load_day_frames(day_dir, account_id, loader)
        if deals_df.empty and positions_df.empty:
            continue

        state.update(day, {}, deals_df, positions_df)
        state.trade_history[day] = deals_df.copy()
        state.position_history[day] = positions_df.copy()
        processed.append(day)
        payloads_by_day[day] = state.to_dict()

    if not processed:
        raise RuntimeError(f"No usable snapshot files for account {account_id}")

    target = alignment_target_for_account(account_id, root, old_cache, processed, payloads_by_day, loader)
    offset = 0.0
    if target is not None:
        target_day, target_equity = target
        current_equity = float(payloads_by_day[target_day].get("current_asset", 0.0))
        offset = float(target_equity - current_equity)
        state.cash_balance += offset
        state.current_asset += offset
        state.current_profit = float(state.current_asset - state.base_total_equity)
        apply_constant_equity_offset(payloads_by_day, offset, state.base_total_equity)

    refresh_nav_history(payloads_by_day, state.base_total_equity)

    for day in processed:
        payload = payloads_by_day[day]
        payload["nav_history"] = merge_old_nav_history(account_id, old_cache, stitch_before, payload["nav_history"])
        series = pd.Series(payload["nav_history"], dtype=float)
        payload["peak_nav"] = float(series.max()) if not series.empty else 1.0
        payload["peak_date"] = str(series.idxmax()) if not series.empty else ""
        out_file = out_dir / f"{day}.json"
        out_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "account_id": account_id,
        "days": processed,
        "last_day": processed[-1],
        "last_nav": float(payloads_by_day[processed[-1]]["nav_history"][processed[-1]]),
        "last_asset": float(payloads_by_day[processed[-1]]["current_asset"]),
        "last_cash": float(payloads_by_day[processed[-1]]["cash_balance"]),
        "equity_offset": float(offset),
        "out_dir": str(out_dir),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild cache from per-day snapshot folders (YYYYMMDD).")
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--root", default=".")
    parser.add_argument("--target-cache", default="cache_v2")
    parser.add_argument("--old-cache", default="cache")
    parser.add_argument("--stitch-before", default="20260901")
    args = parser.parse_args()

    result = rebuild_account(
        str(args.account_id),
        Path(args.root),
        Path(args.target_cache),
        Path(args.old_cache),
        str(args.stitch_before),
    )

    print(
        "REBUILT",
        result["account_id"],
        "days=",
        len(result["days"]),
        "range=",
        f"{result['days'][0]}->{result['last_day']}",
        "offset=",
        result["equity_offset"],
        "last_nav=",
        result["last_nav"],
        "last_asset=",
        result["last_asset"],
        "last_cash=",
        result["last_cash"],
        "out_dir=",
        result["out_dir"],
    )


if __name__ == "__main__":
    main()
