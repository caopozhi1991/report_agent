import pandas as pd

from report_agent.core.account_state import AccountState


def test_reverse_repo_t_day_is_asset_and_no_interest_recognized():
    state = AccountState("demo", 1_000_000.0)
    deals = pd.DataFrame(
        {
            "证券代码": ["204001"],
            "操作": ["通用回购卖出"],
            "成交金额": [975000.0],
            "成交价格": [1.095],
            "成交日期": ["20260828"],
        }
    )
    positions = pd.DataFrame(columns=["证券代码", "当前拥股", "成本价", "市值", "盈亏"])

    nav = state.update("20260828", {}, deals, positions)

    assert abs(state.cash_balance - 25_000.0) < 1e-9
    assert abs(state.current_repo_mv - 975_000.0) < 1e-9
    assert abs(state.current_asset - 1_000_000.0) < 1e-9
    assert abs(state.current_profit - 0.0) < 1e-9
    assert abs(nav - 1.0) < 1e-9


def test_reverse_repo_interest_is_recognized_on_maturity_t_plus_1():
    state = AccountState("demo", 1_000_000.0)
    day_t_deals = pd.DataFrame(
        {
            "证券代码": ["204001"],
            "操作": ["通用回购卖出"],
            "成交金额": [975000.0],
            "成交价格": [1.095],
            "成交日期": ["20260828"],
        }
    )
    positions = pd.DataFrame(columns=["证券代码", "当前拥股", "成本价", "市值", "盈亏"])
    state.update("20260828", {}, day_t_deals, positions)

    day_t1_deals = pd.DataFrame(columns=["证券代码", "操作", "成交金额", "成交价格", "成交日期"])
    nav_t1 = state.update("20260829", {}, day_t1_deals, positions)

    expected_interest = 975000.0 * 1.095 / 100.0 / 365.0
    assert abs(state.current_repo_mv - 0.0) < 1e-9
    assert abs(state.cash_balance - (1_000_000.0 + expected_interest)) < 1e-6
    assert abs(state.current_asset - (1_000_000.0 + expected_interest)) < 1e-6
    assert abs(nav_t1 - (1.0 + expected_interest / 1_000_000.0)) < 1e-9
