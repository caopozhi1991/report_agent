import json
import sys
from pathlib import Path

sys.path.insert(0, '.')
base = Path('.')
(base / 'data').mkdir(exist_ok=True)
(base / 'reports').mkdir(exist_ok=True)
(base / 'cache').mkdir(exist_ok=True)
seed_dir = base / 'seeds' / '1219020189'
seed_dir.mkdir(parents=True, exist_ok=True)
seed = {
    'account_id': '1219020189',
    'date': '20260813',
    'total_asset': 596202.77,
    'profit': -3797.23,
    'stock_mv': 218210.00,
    'nav': 0.9937,
    'peak_nav': 1.0064,
    'peak_date': '20260623',
    'initial_capital': 600000,
    'positions': [{'code': '601398', 'qty': 3200, 'cost': 7.531, 'market_value': 24320, 'profit': 221.87}],
    'nav_history': {'20260801': 0.9950, '20260813': 0.9937},
}
(seed_dir / 'seed.json').write_text(json.dumps(seed, ensure_ascii=False, indent=2), encoding='utf-8')
for acc in ['1219020189', '1206016764']:
    (base / 'data' / f'{acc}_account.csv').write_text('证券代码,总资产,可用资金,股票市值,盈亏\nA,600000,120000,460000,0\n', encoding='utf-8')
    (base / 'data' / f'{acc}_deals.csv').write_text('证券代码,操作,成交价格,成交数量,成交金额\n600000,买入,10.00,1000,10000\n600000,卖出,11.00,500,5500\n', encoding='utf-8')
    (base / 'data' / f'{acc}_positions.csv').write_text('证券代码,当前拥股,成本价,市值,盈亏\n600000,500,10.00,5000,0\n', encoding='utf-8')
from report_agent.agent import MultiAccountReportAgent
agent = MultiAccountReportAgent()
print(agent.generate_all(date='20260814'))
