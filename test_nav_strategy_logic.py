import pandas as pd

from report_agent.agent import MultiAccountReportAgent
from report_agent.core.account_state import AccountState


def test_strategy_profit_includes_position_realized_and_repo_interest_minus_etf():
    positions = pd.DataFrame(
        {
            "证券代码": ["000001", "510050", "000002"],
            "盈亏": [120.0, -50.0, 80.0],
            "市值": [10000.0, 5000.0, 2000.0],
        }
    )
    deals = pd.DataFrame(
        {
            "证券代码": ["000001", "510050", "000002", "204001"],
            "操作": ["买入", "卖出", "卖出", "通用回购卖出"],
            "成交金额": [1000.0, 3000.0, 2000.0, 975000.0],
            "成交价格": [0.0, 0.0, 0.0, 1.095],
            "成交日期": ["20260827", "20260827", "20260827", "20260828"],
        }
    )

    strategy_position = float(positions[~positions["证券代码"].str.startswith(("15", "16", "50", "51", "52", "56", "58"))]["盈亏"].sum())
    realized = MultiAccountReportAgent._calculate_realized_trade_pnl(deals)
    repo_interest = MultiAccountReportAgent._calculate_reverse_repo_interest(deals)
    assert strategy_position == 200.0
    assert realized == 1000.0
    assert abs(repo_interest - 29.25) < 1e-3
    total_strategy_profit = strategy_position + realized + repo_interest
    assert abs(total_strategy_profit - 1229.25) < 1e-3

    nav = (1000000.0 + total_strategy_profit) / 1000000.0
    assert abs(nav - 1.00122925) < 1e-9


def test_nav_uses_previous_strategy_capital_as_base():
    state = AccountState("demo", 1_000_000.0, nav_history=pd.Series({"20260827": 1.0}, dtype=float))

    nav = state.calculate_nav(
        "20260828",
        prev_total_asset=1_000_000.0,
        daily_profit=5000.0,
        total_asset=1_000_000.0,
    )

    assert abs(nav - 1.005) < 1e-9
