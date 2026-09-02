from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd

from report_agent.analysis.stock.trade_analysis import TradeAnalysis
from report_agent.config import CONFIG
from report_agent.core.account_state import AccountState, normalize_date_key
from report_agent.core.benchmark_loader import BenchmarkLoader
from report_agent.core.metrics_calculator import MetricsCalculator
from report_agent.core.pdf_generator import PDFReportGenerator


ETF_PREFIXES = ("15", "16", "50", "51", "52", "56", "58")


def normalize_code(value: object) -> str:
    digits = re.sub(r"\D", "", str(value).split(".")[0])
    return digits.zfill(6)


def is_repo_trade(row: dict) -> bool:
    code = normalize_code(row.get("证券代码", ""))
    op = str(row.get("操作", ""))
    return code.startswith(("204", "1318")) or ("回购" in op or "逆回购" in op)


def parse_term_days(code: str) -> int:
    suffix = normalize_code(code)[-3:]
    known = {
        "001": 1,
        "002": 2,
        "003": 3,
        "004": 4,
        "007": 7,
        "014": 14,
        "028": 28,
        "091": 91,
        "182": 182,
    }
    return int(known.get(suffix, 1))


def add_days(date_key: str, days: int) -> str:
    return (pd.to_datetime(date_key, format="%Y%m%d") + pd.Timedelta(days=int(days))).strftime("%Y%m%d")


def to_float(value: object) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def stock_mv_of(position_history: dict, date_key: str) -> float:
    rows = position_history.get(date_key, []) or []
    total = 0.0
    for row in rows:
        code = normalize_code(row.get("证券代码", ""))
        if code.startswith(ETF_PREFIXES):
            continue
        total += to_float(row.get("市值", 0.0))
    return float(total)


def recalc_account(account_id: str, target_date: str, start_date: str, generate_pdf: bool = True) -> dict:
    cache_file = Path("cache") / account_id / f"{target_date}.json"
    if not cache_file.exists():
        raise FileNotFoundError(f"Cache file not found: {cache_file}")

    payload = json.loads(cache_file.read_text(encoding="utf-8"))
    initial_capital = float(payload.get("initial_capital", 0.0))
    old_nav_history = {normalize_date_key(k): float(v) for k, v in payload.get("nav_history", {}).items()}
    position_history = {normalize_date_key(k): v for k, v in payload.get("position_history", {}).items()}
    trade_history = {normalize_date_key(k): v for k, v in payload.get("trade_history", {}).items()}

    if start_date not in old_nav_history:
        raise RuntimeError(f"{start_date} missing in nav_history for account {account_id}")

    base_total_equity = float(payload.get("base_total_equity", initial_capital or 1.0))
    all_dates = sorted(
        set(
            [d for d in position_history.keys() if d >= start_date]
            + [d for d in trade_history.keys() if d >= start_date]
        )
    )
    if not all_dates:
        raise RuntimeError(f"No dates to recalc from {start_date} for account {account_id}")

    start_nav = float(old_nav_history[start_date])
    start_equity = start_nav * base_total_equity

    def day_trades(date_key: str) -> list[dict]:
        return list(trade_history.get(date_key, []) or [])

    repo_positions: list[dict] = []
    for row in day_trades(start_date):
        if not is_repo_trade(row):
            continue
        principal = to_float(row.get("成交金额", 0.0))
        if principal <= 0:
            continue
        code = normalize_code(row.get("证券代码", ""))
        term_days = parse_term_days(code)
        repo_positions.append(
            {
                "principal": principal,
                "rate": to_float(row.get("成交价格", 0.0)),
                "trade_date": start_date,
                "maturity_date": add_days(start_date, term_days),
                "term_days": term_days,
                "security_code": code,
            }
        )

    start_repo_mv = sum(float(item["principal"]) for item in repo_positions)
    start_stock_mv = stock_mv_of(position_history, start_date)
    # User accounting rule: reverse repo principal stays in cash for equity calculation; only the
    # repo interest is added to equity, while the principal is used as a funding base for interest.
    cash_balance = start_equity - start_stock_mv

    recalculated_nav = {k: v for k, v in old_nav_history.items() if k < start_date}
    recalculated_nav[start_date] = start_nav
    cash_ledger: dict[str, list[dict]] = {
        start_date: [
            {
                "date": start_date,
                "type": "day_start_inferred",
                "amount": 0.0,
                "balance_after": float(cash_balance),
                "security_code": "",
                "note": "由权益恒等式反推期末现金",
            }
        ]
    }

    for date_key in [d for d in all_dates if d > start_date]:
        entries: list[dict] = []

        remaining_repo: list[dict] = []
        for repo in repo_positions:
            if str(repo.get("maturity_date", "")) <= date_key:
                principal = float(repo.get("principal", 0.0))
                rate = float(repo.get("rate", 0.0))
                term_days = int(repo.get("term_days", 1) or 1)
                interest = principal * (rate / 100.0) * term_days / 365.0
                cash_balance += principal
                cash_balance += interest
            else:
                remaining_repo.append(repo)
        repo_positions = remaining_repo

        for row in day_trades(date_key):
            code = normalize_code(row.get("证券代码", ""))
            amount = to_float(row.get("成交金额", 0.0))
            if amount <= 0:
                continue

            operation = str(row.get("操作", ""))
            op_upper = operation.upper()

            if is_repo_trade(row):
                cash_balance += amount
                term_days = parse_term_days(code)
                repo_positions.append(
                    {
                        "principal": amount,
                        "rate": to_float(row.get("成交价格", 0.0)),
                        "trade_date": date_key,
                        "maturity_date": add_days(date_key, term_days),
                        "term_days": term_days,
                        "security_code": code,
                    }
                )
                continue

            if code.startswith(ETF_PREFIXES):
                continue

            if ("买入" in operation) or ("BUY" in op_upper) or (op_upper == "B"):
                cash_balance -= amount
                entries.append(
                    {
                        "date": date_key,
                        "type": "stock_buy_out",
                        "amount": -amount,
                        "balance_after": float(cash_balance),
                        "security_code": code,
                        "note": "股票买入现金流出",
                    }
                )
            elif ("卖出" in operation) or ("SELL" in op_upper) or (op_upper == "S"):
                cash_balance += amount
                entries.append(
                    {
                        "date": date_key,
                        "type": "stock_sell_in",
                        "amount": amount,
                        "balance_after": float(cash_balance),
                        "security_code": code,
                        "note": "股票卖出现金流入",
                    }
                )

        stock_mv = stock_mv_of(position_history, date_key)
        accrued_interest = float(
            sum(
                float(item.get("principal", 0.0)) * float(item.get("rate", 0.0)) / 100.0 * int(item.get("term_days", 1) or 1) / 365.0
                for item in repo_positions
                if str(item.get("trade_date", "")) < date_key
            )
        )
        total_equity = float(cash_balance + stock_mv + accrued_interest)
        recalculated_nav[date_key] = total_equity / base_total_equity if base_total_equity else 0.0
        cash_ledger[date_key] = entries

    for key, value in old_nav_history.items():
        recalculated_nav.setdefault(key, value)

    payload["nav_history"] = dict(sorted(recalculated_nav.items()))
    payload["base_total_equity"] = base_total_equity
    payload["cash_ledger"] = cash_ledger
    payload["repo_positions"] = repo_positions
    payload["cash_balance"] = float(cash_balance)

    last_stock_mv = stock_mv_of(position_history, target_date)
    last_repo_mv = float(sum(float(item.get("principal", 0.0)) for item in repo_positions))
    last_interest = float(
        sum(
            float(item.get("principal", 0.0)) * float(item.get("rate", 0.0)) / 100.0 * int(item.get("term_days", 1) or 1) / 365.0
            for item in repo_positions
            if str(item.get("trade_date", "")) < target_date
        )
    )
    last_total_equity = float(cash_balance + last_stock_mv + last_interest)
    payload["current_stock_mv"] = last_stock_mv
    payload["current_repo_mv"] = last_repo_mv
    payload["current_asset"] = last_total_equity
    payload["current_profit"] = last_total_equity - base_total_equity

    cache_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    output_pdf = ""
    if generate_pdf:
        state = AccountState.from_dict(payload)
        metrics = MetricsCalculator.calculate(state)

        bench_cfg = CONFIG.get("benchmarks", {})
        benchmark_loader = BenchmarkLoader(
            cache_dir=CONFIG["cache_dir"],
            symbols=bench_cfg.get("symbols"),
            api_key=bench_cfg.get("api_key", ""),
            enabled=bool(bench_cfg.get("enabled", True)),
        )
        benchmarks = benchmark_loader.get_normalized_series(metrics["nav_series"])

        report_dir = Path(CONFIG["output_dir"])
        report_dir.mkdir(parents=True, exist_ok=True)
        account_name = CONFIG.get("account_names", {}).get(account_id, account_id)
        safe_name = re.sub(r"[\\/:*?\"<>|]", "_", str(account_name)).strip() or account_id
        output_path = report_dir / f"股票实盘复盘报告_{safe_name}_{target_date}.pdf"

        report = PDFReportGenerator(str(output_path), account_name)
        report.add_nav_and_metrics(
            metrics["nav_series"],
            metrics,
            initial_capital,
            last_stock_mv,
            benchmarks=benchmarks,
        )

        trade_result = TradeAnalysis().analyze(state, CONFIG)
        trade_result["initial_capital"] = initial_capital
        daily_trades = state.trade_history.get(target_date, pd.DataFrame())
        report.add_stock_review(trade_result, daily_trades, state.current_positions, llm_results=None)
        report.save()
        output_pdf = str(output_path)

    return {
        "account_id": account_id,
        "cache_file": str(cache_file),
        "pdf": output_pdf,
        "nav_start": payload["nav_history"].get(start_date),
        "nav_target": payload["nav_history"].get(target_date),
        "current_asset": payload.get("current_asset"),
        "cash_balance": payload.get("cash_balance"),
        "repo_positions_count": len(payload.get("repo_positions", [])),
        "recalc_dates": [d for d in sorted(payload["nav_history"].keys()) if d >= start_date],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Recalculate nav_history with cash-ledger and reverse repo T+1 logic.")
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--target-date", required=True)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--no-pdf", action="store_true")
    args = parser.parse_args()

    result = recalc_account(
        account_id=str(args.account_id),
        target_date=normalize_date_key(args.target_date),
        start_date=normalize_date_key(args.start_date),
        generate_pdf=not args.no_pdf,
    )

    print("UPDATED_CACHE", result["cache_file"])
    if result["pdf"]:
        print("PDF", result["pdf"])
    print("NAV_START", result["nav_start"])
    print("NAV_TARGET", result["nav_target"])
    print("CURRENT_ASSET", result["current_asset"])
    print("CASH_BALANCE", result["cash_balance"])
    print("REPO_POSITIONS_COUNT", result["repo_positions_count"])
    print("RECALC_DATES", result["recalc_dates"])


if __name__ == "__main__":
    main()
