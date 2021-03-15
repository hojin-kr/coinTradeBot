import urllib.request
import json
import time

def parse_current_trades():
	# ## 1차 개발(조회)
	# 1. 분단위로 현재 거래 가격을 확인해서 저장
	raw = urllib.request.urlopen("https://api.coinone.co.kr/trades").read()
	trades = json.loads(raw.decode('utf-8'))
	# 주문 완료 가격 리스트 최근 200개
	completeOrders = trades.get('completeOrders')
	f = open('./trades/trades.txt', mode='at')
	for list in completeOrders:
		f.writelines(json.dumps(list) + '\n')
	f.close()

parse_current_trades()
