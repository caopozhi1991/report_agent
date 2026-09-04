import pandas as pd

from report_agent.core.account_state import AccountState


def test_reverse_repo_opening_does_not_change_cash_or_equity():
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

    assert abs(state.cash_balance - 1_000_000.0) < 1e-9
    assert abs(state.current_repo_mv - 0.0) < 1e-9
    assert abs(state.current_asset - 1_000_000.0) < 1e-9
    assert abs(state.current_profit - 0.0) < 1e-9
    assert abs(nav - 1.0) < 1e-9


def test_reverse_repo_interest_only_hits_cash_on_maturity():
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

    empty_deals = pd.DataFrame(columns=["证券代码", "操作", "成交金额", "成交价格", "成交日期"])

    # 2026-08-29 is not the business-day maturity date for a 1-day repo opened on 2026-08-28.
    nav_before_maturity = state.update("20260829", {}, empty_deals, positions)

    # Maturity is the next business day: 2026-08-31.
    nav_maturity = state.update("20260831", {}, empty_deals, positions)

    expected_interest = 975000.0 * 1.095 / 100.0 / 365.0
    assert abs(state.current_repo_mv - 0.0) < 1e-9
    assert abs(nav_before_maturity - 1.0) < 1e-9
    assert abs(state.cash_balance - (1_000_000.0 + expected_interest)) < 1e-6
    assert abs(state.current_asset - (1_000_000.0 + expected_interest)) < 1e-6
    assert abs(nav_maturity - (1.0 + expected_interest / 1_000_000.0)) < 1e-9


def test_positions_drive_cash_and_equity_v2():
    state = AccountState("demo", 1_000_000.0)
    positions = pd.DataFrame(
        {
            "证券代码": ["600000", "600001"],
            "当前拥股": [0, 100],
            "市值": [0.0, 12_000.0],
            "盈亏": [2_500.0, -800.0],
        }
    )
    empty_deals = pd.DataFrame(columns=["证券代码", "操作", "成交金额", "成交价格", "成交日期"])

    nav = state.update("20260902", {}, empty_deals, positions)

    # Cash increases by realized daily PnL from closed positions.
    assert abs(state.cash_balance - 1_002_500.0) < 1e-9
    # Equity uses unrealized PnL for holdings, not stock market value.
    assert abs(state.current_asset - (1_002_500.0 - 800.0)) < 1e-9
    assert abs(nav - ((1_002_500.0 - 800.0) / 1_000_000.0)) < 1e-9
    # Market value is still retained for display purposes.
    assert abs(state.current_stock_mv - 12_000.0) < 1e-9


def test_stock_trade_amounts_do_not_directly_change_cash_v2():
    state = AccountState("demo", 1_000_000.0)
    deals = pd.DataFrame(
        {
            "证券代码": ["600000", "600000"],
            "操作": ["买入", "卖出"],
            "成交金额": [200_000.0, 180_000.0],
            "成交价格": [10.0, 9.0],
            "成交日期": ["20260903", "20260903"],
        }
    )
    positions = pd.DataFrame(
        {
            "证券代码": ["600000"],
            "当前拥股": [100],
            "市值": [50_000.0],
            "盈亏": [1_200.0],
        }
    )

    state.update("20260903", {}, deals, positions)

    # No closed position today -> realized daily PnL is zero; cash remains unchanged.
    assert abs(state.cash_balance - 1_000_000.0) < 1e-9
    assert abs(state.current_asset - 1_001_200.0) < 1e-9
