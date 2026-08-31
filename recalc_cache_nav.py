import json
from pathlib import Path

ETF_PREFIXES = ('15', '16', '50', '51', '52', '56', '58')


def is_etf(code):
    return str(code).split('.')[0].zfill(6).startswith(ETF_PREFIXES)


def is_repurchase(row):
    code = str(row.get('证券代码', '')).split('.')[0].zfill(6)
    op = str(row.get('操作', ''))
    return '回购' in op or '逆回购' in op or code.startswith(('204', '1318'))


def process_trade_lots(trade_rows):
    lots = {}
    realized = 0.0
    for row in trade_rows:
        code = str(row.get('证券代码', '')).split('.')[0].zfill(6)
        if is_etf(code) or is_repurchase(row):
            continue
        op = str(row.get('操作', ''))
        qty = int(float(row.get('成交数量', 0) or 0))
        price = float(row.get('成交价格', 0) or 0)
        if qty <= 0:
            continue
        if '买入' in op or 'B' in op:
            lots.setdefault(code, []).append({'qty': qty, 'price': price})
        elif '卖出' in op or 'S' in op:
            left = qty
            while left > 0 and lots.get(code):
                lot = lots[code][0]
                take = min(left, lot['qty'])
                realized += (price * take) - (lot['price'] * take)
                lot['qty'] -= take
                left -= take
                if lot['qty'] == 0:
                    lots[code].pop(0)
    return realized


def sum_non_etf_pnl(rows):
    total = 0.0
    for row in rows or []:
        code = str(row.get('证券代码', '')).split('.')[0].zfill(6)
        if is_etf(code):
            continue
        total += float(row.get('盈亏', 0) or 0)
    return total


for account in ['1206016764', '1219020189']:
    cache_dir = Path('cache') / account
    files = sorted(cache_dir.glob('*.json'))
    print('ACCOUNT', account)

    base_data = None
    for file in files:
        data = json.loads(file.read_text(encoding='utf-8'))
        nav = data.get('nav_history', {})
        if '20260819' in nav:
            base_data = data
            break

    if base_data is None:
        print('missing 20260819 baseline')
        continue

    base_nav = float(base_data['nav_history']['20260819'])
    base_capital = float(base_data['initial_capital']) * base_nav
    prev_floating = sum_non_etf_pnl(base_data.get('position_history', {}).get('20260819', []))
    prev_strategy_capital = base_capital

    daily_pos = {}
    daily_trade = {}
    for file in files:
        data = json.loads(file.read_text(encoding='utf-8'))
        for dt, rows in data.get('position_history', {}).items():
            if dt >= '20260820':
                daily_pos[dt] = rows
        for dt, rows in data.get('trade_history', {}).items():
            if dt >= '20260820':
                daily_trade.setdefault(dt, []).extend(rows)

    recalculated = {'20260819': base_nav}
    for dt in sorted(daily_pos.keys()):
        floating = sum_non_etf_pnl(daily_pos[dt])
        realized = process_trade_lots(daily_trade.get(dt, []))
        strategy_capital = prev_strategy_capital + (floating - prev_floating) + realized
        recalculated[dt] = strategy_capital / float(base_data['initial_capital'])
        prev_strategy_capital = strategy_capital
        prev_floating = floating

    for file in files:
        data = json.loads(file.read_text(encoding='utf-8'))
        for dt, val in recalculated.items():
            if dt in data.get('nav_history', {}):
                data['nav_history'][dt] = val
        file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

    print('recalculated', recalculated)
    print()