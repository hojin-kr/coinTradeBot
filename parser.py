import urllib.request
import json
import time

def parse_current_trades():
	# ## 1차 개발(조회)
	# 1. 분단위로 현재 거래 가격을 확인해서 저장
	raw = urllib.request.urlopen("https://api.coinone.co.kr/public/v2/trades/krw/wemix").read()
	trades = json.loads(raw.decode('utf-8'))
	# 주문 완료 가격 리스트 최근 200개
	completeOrders = trades.get('transactions')
	f = open('./trades/trades.txt', mode='at')
	for list in completeOrders:
		f.writelines(json.dumps(list) + '\n')
	f.close()

def parse_current_trades(quote_currency,target_currency,size):
    # 주문 완료 가격 리스트 최근 50개
    url = f"https://api.coinone.co.kr/public/v2/trades/{quote_currency}/{target_currency}?size={size}"
    raw = urllib.request.urlopen(url).read()
    trades = json.loads(raw.decode('utf-8'))
    transactions = trades.get('transactions')
    sum_price = 0
    sum_qty = 0
    for transaction in transactions:
        sum_price += float(transaction['price'])
        sum_qty += float(transaction['qty'])
    avg_price = sum_price/float(size)
    avg_qty = sum_qty/float(size)
    line_notify(f"[avg] price {int(avg_price)} qty {int(avg_qty)}")

parse_current_trades('krw','wemix','200')
