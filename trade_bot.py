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

# line notify send
def line_notify(message):
    if LINE_NOTIFY_TOKEN :
        os.system("curl -X POST -H 'Authorization: Bearer " + LINE_NOTIFY_TOKEN + "' -F 'message=" + message +"' https://notify-api.line.me/api/notify")

class Bot :
    def __init__(self) :
        self.current_price = float(json.loads(urllib.request.urlopen("https://api.coinone.co.kr/trades").read().decode('utf-8')).get('completeOrders')[0]['price'])
        self.time = time.time()
        self.order_last = tailer.tail(open('./orders/orders.txt'), 1)[0].split(':')  # 서버에 저장된 마지막 거래 기록

    def getAvg(self, period) :
        time = self.time - period
        f = open('./trades/trades.txt', mode='rt')
        trades = f.readlines()
        f.close()
        total = 0
        cnt = 0
        for list in trades :
            timestamp = int(json.loads(list).get('timestamp'))
            if time < timestamp :
                total += float(json.loads(list).get('price'))
                cnt += float(1)
        return int(total / cnt)

    def getQty(self, type="krw") :
        balance = get_response(action='v2/account/balance', payload={'access_token': ACCESS_TOKEN,})
        avail = json.loads(balance.decode('utf-8')).get(type)['avail'] # 거래 가능 원화
        return float(avail)/float(self.current_price) # 거래 가능 갯수

    def record(action, price, orderId, qty) :
        f = open('./orders/orders.txt', mode='at')
        f.writelines("{}:{}:{}:{}:{}\n".format(action, price, self.time, orderId, qty))
        f.close()

    def checkPastTrade(self) :
        # 이전 거래가 완료 됬었는지 확인
        res = get_response(action='v2/order/order_info', payload={
            'access_token': ACCESS_TOKEN,
            'order_id': self.order_last[3],
            'currency': 'BTC',
        })
        code = json.loads(res.decode('utf-8')).get('errorCode')
        # 해당 주문 아이디가 없다고 나옴 -> 거래 완료
        if code == '104':
            return True
        if code == '0':
            if json.loads(res.decode('utf-8')).get('status') == 'filled':
                return True
        return False

    def buy(self) :
        qty = self.getQty("krw")
        res = get_response(action='v2/order/limit_buy', payload={
            'access_token': ACCESS_TOKEN,
            'price': round(self.current_price),
            'qty': str(qty)[:6],
            'currency': 'BTC',
        })
        order = json.loads(res.decode('utf-8'))
        orderId = order.get('orderId')
        code = order.get('errorCode')
        if code == '0':
            record("buy", self.current_price, orderId, qty)
        if code != '0':
            message = "## buy error code  ##\n"
            message += "Code %s \n" % str(code)
            message += "errormsg {} \n".format(order.get("errorMsg"))
            message += "current_price %s \n" % str(self.current_price)
            message += str(qty)[:6]
            line_notify(message)
    def sell(self) :
        qty = self.getQty("btc")
        res = get_response(action='v2/order/limit_sell', payload={
            'access_token': ACCESS_TOKEN,
            'price': round(self.current_price),
            'qty': str(qty)[:6],
            'currency': 'BTC',
        })
        print(res)
        order = json.loads(res.decode('utf-8'))
        orderId = order.get('orderId')
        code = order.get('errorCode')
        if code == '0':
            record("sell", self.current_price, orderId, qty)
        if code != '0':
            message = "## sell error code  ##\n"
            message += "Code %s \n" % str(code)
            message += "errormsg {} \n".format(order.get("errorMsg"))
            message += "current_price %s \n" % str(self.current_price)
            message += str(qty)[:6]
            line_notify(message)


def run() :
    bot = Bot()
    action = "none"
    # 이전 거래가 완료됨
    if bot.checkPastTrade() :
        if bot.order_last[0] == "buy" :
            # 내가 가지고 있는데
            # 값이 오르고 있으면 유지
            # 값이 떨어지고 있으면 매도
            if bot.getAvg(3600*24) > bot.getAvg(3600*1) :
                action = "sell"
        elif bot.order_last[0] == "sell" :
            # 내가 안가지고 있는데,
            # 값이 오르고 있으면 매수
            if bot.getAvg(3600*24) < bot.getAvg(3600*1) :
                action = "buy"
    if action == "buy" :
        bot.buy()
    elif action == "sell" :
        bot.sell()
    line_notify(action)
run()
