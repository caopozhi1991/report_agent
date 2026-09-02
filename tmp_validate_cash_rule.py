import csv

with open('data/1219020189_2_account.csv', newline='', encoding='gbk') as f:
    account_rows = list(csv.DictReader(f))
account = account_rows[0]

with open('data/1219020189_2_deals.csv', newline='', encoding='gbk') as f:
    deals = list(csv.DictReader(f))

repo_rows = [row for row in deals if row.get('成交日期') == '20260902' and row.get('证券代码') == '204001']
repo_principal = sum(float(row['成交金额']) for row in repo_rows)
available_cash = float(account['可用资金'])
stock_mv = float(account['股票市值'])
total_asset = float(account['总资产'])
interest = total_asset - (available_cash + repo_principal + stock_mv)

assert abs((available_cash + repo_principal + stock_mv + interest) - total_asset) < 1e-6
print({
    'available_cash': available_cash,
    'repo_principal': repo_principal,
    'stock_mv': stock_mv,
    'interest': interest,
    'total_asset': total_asset,
})
