import urllib.request
import json
import time
import os
import tailer
import base64
import hashlib
import hmac
import httplib2
import math
import sys

ACCESS_TOKEN = ''   # coinone access token
SECRET_KEY = bytes('', 'utf-8') # coinone secret key
LINE_NOTIFY_TOKEN = ''   # line notify token
AVG_STANDARD_TIME = 21600   # 평균 기준 기간 6시간

def get_encoded_payload(payload):
    payload['nonce'] = int(time.time() * 1000)
    dumped_json = json.dumps(payload)
    encoded_json = base64.b64encode(bytes(dumped_json, 'utf-8'))
    return encoded_json

def get_signature(encoded_payload):
    signature = hmac.new(SECRET_KEY, encoded_payload, hashlib.sha512)
    return signature.hexdigest()

def get_response(action, payload):
    url = '{}{}'.format('https://api.coinone.co.kr/', action)
    encoded_payload = get_encoded_payload(payload)
    headers = {
        'Content-type': 'application/json',
        'X-COINONE-PAYLOAD': encoded_payload,
        'X-COINONE-SIGNATURE': get_signature(encoded_payload),
    }
    http = httplib2.Http()
    response, content = http.request(url, 'POST', body=encoded_payload, headers=headers)
    return content

def current_trade_price():
    now_trades = urllib.request.urlopen("https://api.coinone.co.kr/trades").read()  # 현재 거래 완료 리스트
    return float(json.loads(now_trades.decode('utf-8')).get('completeOrders')[0]['price'])    # 현재가

# 전체 기간 중 평균 대비 최대 증감율
def period_price_avg_rate(avg_standard_time, current_price, _time):
    f = open('./trades/trades.txt', mode='rt')
    # 라인별로 json 형태로 되어 있어 전체를 라인별 배열로 로드
    trades = f.readlines()
    f.close()
    priceTotal = 0  # 원하는 기간 동안의 거래 금액을 총합
    tradeCnt = 0
    min = 999999999999
    max = 0
    for list in trades:
            try:
                    if _time - AVG_STANDARD_TIME < int(float(json.loads(list).get('timestamp'))) :
                            price = json.loads(list).get('price')
                            priceTotal += int(float(price))
                            tradeCnt += 1
                            if float(price) > float(max):
                                max = float(price)
                            if float(price) < float(min):
                                min = float(price)
            # json 파싱 실패
            except Exception as e:
                    e
    avg =  priceTotal/tradeCnt
    current_diff = float(((current_price - avg) / avg) * 100)   # 평균 대비 현재가의 증감율
    period_price = min
    if abs(avg - min) < abs(avg - max):
        period_price = max
    period_diff = float((period_price - avg) / avg * 100)
    return period_diff

# 평균 대비 현재가의 증감율
def period_price_current_rate(avg_standard_time, current_price, _time):
    f = open('./trades/trades.txt', mode='rt')
    # 라인별로 json 형태로 되어 있어 전체를 라인별 배열로 로드
    trades = f.readlines()
    f.close()
    priceTotal = 0  # 원하는 기간 동안의 거래 금액을 총합
    tradeCnt = 0
    min = 999999999999
    max = 0
    for list in trades:
            try:
                    if _time - AVG_STANDARD_TIME < int(float(json.loads(list).get('timestamp'))) :
                            price = json.loads(list).get('price')
                            priceTotal += int(float(price))
                            tradeCnt += 1
                            if float(price) > float(max):
                                max = float(price)
                            if float(price) < float(min):
                                min = float(price)
            # json 파싱 실패
            except Exception as e:
                    e
    avg =  priceTotal/tradeCnt
    current_diff = float(((current_price - avg) / avg) * 100)
    return current_diff

# 매수 매도 기록
def record(action, price, time, orderId, qty):
    f = open('./orders/orders.txt', mode='at')
    f.writelines(str(action) + ':' +  str(price) + ':'+ str(time) + ':' + str(orderId) + ':' + str(qty) +'\n')
    f.close()

def line_notify(token, message):
    os.system("curl -X POST -H 'Authorization: Bearer " + token + "' -F 'message=" + message +"' https://notify-api.line.me/api/notify")
_time = time.time()
current_price  = current_trade_price()  # 현재 거래 가격
period_diff = period_price_avg_rate(AVG_STANDARD_TIME, current_price, _time)  # 전체 기간 중 평균 대비 최대 증감율
current_diff = period_price_current_rate(AVG_STANDARD_TIME, current_price, _time)  # 평균 대비 현재가의 증감율
if sys.argv[1] != 'buy' and sys.argv[1] != 'sell':
    lastOrders = tailer.tail(open('./orders/orders.txt'), 1)[0].split(':')  # 서버에 저장된 마지막 거래 기록
# 자산
balance = get_response(action='v2/account/balance', payload={
    'access_token': ACCESS_TOKEN,
})
krw_avail = json.loads(balance.decode('utf-8')).get('krw')['avail'] # 거래 가능 원화
qty = float(krw_avail)/float(current_price) # 거래 가능 갯수
# 거래 여부 판단
action = 'none'
if sys.argv[1] == 'buy' or sys.argv[1] == 'sell':
    action = sys.argv[1]
# 가격 차이가 정한 전체 평균 대비 증감률 보다 크고 이전 매수가격 보다 높으면 전량 매도 (이 순간 한번 이득)
if action == 'none' and lastOrders[0] == 'buy' and current_diff > period_diff and current_price > float(lastOrders[1]):
    # 이전 거래가 완료 됬었는지 확인
    pastOrderInfo = get_response(action='v2/order/order_info', payload={
        'access_token': ACCESS_TOKEN,
        'order_id': lastOrders[3],
        'currency': 'BTC',
    })
    orderCode = json.loads(pastOrderInfo.decode('utf-8')).get('errorCode')
    # 해당 주문 아이디가 없다고 나옴 -> 거래 완료
    if orderCode == '104':
        action = 'sell'
    if orderCode == '0':
        if json.loads(pastOrderInfo.decode('utf-8')).get('status') == 'filled':
            action = 'sell'
# 매수 가능 상태이고 가격 차이가 정한 전체 평균 대비 증감률 보다 낮으면 전량 매수
if action == 'none' and lastOrders[0] == 'sell' and current_diff < period_diff:
    pastOrderInfo = get_response(action='v2/order/order_info', payload={
        'access_token': ACCESS_TOKEN,
        'order_id': lastOrders[3],
        'currency': 'BTC',
    })
    orderCode = json.loads(pastOrderInfo.decode('utf-8')).get('errorCode')
    # 해당 주문 아이디가 없다고 나옴 - > 거래 완료
    if orderCode == '104':
        action = 'buy'
    if orderCode == '0':
        if json.loads(pastOrderInfo.decode('utf-8')).get('status') == 'filled':
            action = 'buy'
# 매수 및 기록
if action == 'buy':
    # 현재 금액 확인
    order = get_response(action='v2/order/limit_buy', payload={
        'access_token': ACCESS_TOKEN,
        'price': round(current_price),
        'qty': str(qty)[:6],
        'currency': 'BTC',
    })
    orderId = json.loads(order.decode('utf-8')).get('orderId')
    errorCode = json.loads(order.decode('utf-8')).get('errorCode')
    if errorCode == '0':
        record(action, current_price, _time, orderId, qty)
    if errorCode != '0':
        errorMessage = "## buy error code  ##\n"
        errorMessage += "Code %s \n" % str(errorCode)
        errorMessage += "current_price %s \n" % str(current_price)
        errorMessage += str(qty)[:6]
        line_notify(LINE_NOTIFY_TOKEN, errorMessage)
# 메도 및 기록
if action == 'sell':
    qty = json.loads(balance.decode('utf-8')).get('btc')['avail'] # 거래 가능 BTC
    order = get_response(action='v2/order/limit_sell', payload={
        'access_token': ACCESS_TOKEN,
            'price': round(current_price),
        'qty': str(qty)[:6],
        'currency': 'BTC',
    })
    orderId = json.loads(order.decode('utf-8')).get('orderId')
    errorCode = json.loads(order.decode('utf-8')).get('errorCode')
    if errorCode == '0':
        record(action, current_price, _time, orderId, qty)
    if errorCode != '0':
        errorMessage = "## sell error code  ##\n"
        errorMessage += "Code %s \n" % str(errorCode)
        errorMessage += "current_price %s \n" % str(current_price)
        errorMessage += str(qty)[:6]
        line_notify(LINE_NOTIFY_TOKEN, errorMessage)

# make result message
message = "[BTC]\n"
message += "CURRENT: %s \n" % format(current_price, ',')
message += "DIFF : %.6f%%\n" % current_diff
message += "PERIOD DIFF : %.6f%% \n" % period_diff
message += "ACTION : %s \n" % action
message += "KRW : %s\n" % krw_avail
message += "QTY: %s\n" % str(qty)[:6]
print(message)
# send line noti
line_notify(LINE_NOTIFY_TOKEN, message)
