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

def parse_current_trades(quote_currency,target_currency,size):
    # 주문 완료 가격 리스트 최근 50개
    url = f"https://api.coinone.co.kr/public/v2/trades/{quote_currency}/{target_currency}?size={size}"
    raw = urllib.request.urlopen(url).read()
    trades = json.loads(raw.decode('utf-8'))
    transactions = trades.get('transactions')
    sum_price = 0
    sum_qty = 0
    f = open('./trades/trades.txt', mode='at')
    for transaction in transactions:
        f.writelines(json.dumps(transaction) + '\n')
        sum_price += float(transaction['price'])
        sum_qty += float(transaction['qty'])
    f.close()
    avg_price = sum_price/float(size)
    avg_qty = sum_qty/float(size)
    line_notify(f"[avg] price {int(avg_price)} qty {int(avg_qty)}")

class Bot :
    def __init__(self) :
        self.current_price = float(json.loads(urllib.request.urlopen("https://api.coinone.co.kr/trades").read().decode('utf-8')).get('completeOrders')[0]['price'])
        self.time = time.time()
        self.order_last = tailer.tail(open('./orders/orders.txt'), 1)[0].split(':')  # 서버에 저장된 마지막 거래 기록

    def getAvg(self, period) :
        time = self.time - 3600 * period
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
        return float(avail)

    def record(self, action, price, orderId, qty) :
        f = open('./orders/orders.txt', mode='at')
        f.writelines("{}:{}:{}:{}:{}\n".format(action, price, self.time, orderId, qty))
        f.close()
        line_notify("{}:{}:{}:{}:{}\n".format(action, price, self.time, orderId, qty))

    def checkPastTrade(self) :
        # 이전 거래가 완료 됬었는지 확인
        res = get_response(action='v2/order/order_info', payload={
            'access_token': ACCESS_TOKEN,
            'order_id': self.order_last[3],
            'currency': 'WEMIX',
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
        qty = self.getQty("krw")/float(self.current_price)
        res = get_response(action='v2/order/limit_buy', payload={
            'access_token': ACCESS_TOKEN,
            'price': round(self.current_price),
            'qty': str(qty)[:6],
            'currency': 'WEMIX',
        })
        order = json.loads(res.decode('utf-8'))
        orderId = order.get('orderId')
        code = order.get('errorCode')
        if code == '0':
            self.record("buy", self.current_price, orderId, qty)
        if code != '0':
            message = "## buy error code  ##\n"
            message += "Code %s \n" % str(code)
            message += "errormsg {} \n".format(order.get("errorMsg"))
            message += "current_price %s \n" % str(self.current_price)
            message += str(qty)[:6]
            line_notify(message)
    def sell(self) :
        qty = self.getQty("wemix")
        res = get_response(action='v2/order/limit_sell', payload={
            'access_token': ACCESS_TOKEN,
            'price': round(self.current_price),
            'qty': str(qty)[:6],
            'currency': 'WEMIX',
        })
        print(res)
        order = json.loads(res.decode('utf-8'))
        orderId = order.get('orderId')
        code = order.get('errorCode')
        if code == '0':
            self.record("sell", self.current_price, orderId, qty)
        if code != '0':
            message = "## sell error code  ##\n"
            message += "Code %s \n" % str(code)
            message += "errormsg {} \n".format(order.get("errorMsg"))
            message += "current_price %s \n" % str(self.current_price)
            message += str(qty)[:6]
            line_notify(message)


def run() :
    parse_current_trades('krw','wemix','50')
    bot = Bot()
    action = "none"
    # 이전 거래가 완료됨
    if bot.checkPastTrade() :
        print("pass checkPastTrade")
        if bot.order_last[0] == "buy" :
            # 내가 가지고 있음 오르면 가지고 있고 내려가면 팔아야함
            # 가지고 있는것보다 크고, 상승세면 유지
            # 가지고 있는것보다 크고, 하락세면 매도
            # 가지고 있는것보다 내려가면 바로 매도
            avg24h = bot.getAvg(24)
            avg1h = bot.getAvg(24)
            if float(bot.current_price) > float(bot.order_last[1]) and avg24h > avg1h :
                action = "sell"
            if float(bot.current_price) < float(bot.order_last[1]) :
                action = "sell"
        elif bot.order_last[0] == "sell" :
            # 내가 가지고 있지 않은 상황, 낮을때 사거나 오를것 같을때 사야함
            # 상승세가 되면 매수
            if avg24h < avg1h :
                action = "buy"
    line_notify(f"[action] {action} [avg] 24h {avg24h} 1h {avg1h}")
    if action == "buy" :
        bot.buy()
    elif action == "sell" :
        bot.sell()

run()
