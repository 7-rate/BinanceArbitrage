#coding utf8

import time
import math
import itertools
import threading
import configparser
from binance.client import Client
from binance.websockets import BinanceSocketManager

config = configparser.ConfigParser()
config.read('./config.ini')
api_key = config.get('api', 'key')
api_secret = config.get('api', 'secret')

#手数料設定
commission = 0.00075 * 3

# 利益率設定
minROI = 1.0003
minROI += commission

# 全コイン種読み込み
f = open('alts.txt')
alts = f.read().split('\n')
f.close()

# 各配列初期化
orderbook_tickers_dict = {}
trade_status_dict = {}
asset_balances = {}
target = 'BTC'
pivots = ['BTC', 'ETH', 'USDT', 'BUSD', 'TUSD', 'USDC', 'PAX']

# クライアント初期化
client = Client(api_key, api_secret, {'timeout':600})

# シンボル更新
symbols = set()
orderbook_tickers = client.get_orderbook_tickers()
for ticker in orderbook_tickers:
    symbols.add(ticker['symbol'])

# サーバ-クライアント間レイテンシ確認
def test_time():
    print('server time - client time =', client.get_server_time()['serverTime']-int(time.time()*1000))

# callback function for start_ticker_socket
def update_orderbook_dict(msg):
    for d in msg:
        orderbook_tickers_dict[d['s']] = d
    data = ArbitrageCheck()
    if data.count != 0:
        print(data)

# callback function for start_user_socket
def update_user(msg):
    pass

def validData(tgt, piv, alt):
    validData = set()
    if tgt+piv in symbols:
        validData.add(tgt+piv)
    elif piv+tgt in symbols:
        validData.add(piv+tgt)

    if piv+alt in symbols:
        validData.add(piv+alt)
    elif alt+piv in symbols:
        validData.add(alt+piv)

    if tgt+alt in symbols:
        validData.add(tgt+alt)
    elif alt+tgt in symbols:
        validData.add(alt+tgt)

    return validData

# 3通貨間アービトラージが可能か確認
def ArbitrageCheck():
    tgt = target
    data = []
    start = time.time()
    for piv in pivots:
        for alt in alts:
            vd = validData(tgt, piv, alt)
            if len(vd) < 3:
                continue
            try:
                if vd[0].find(tgt) == 0:
                    tgtpiv_b = float(orderbook_tickers_dict[vd[0]]['b'])
                    if vd[1].find(piv) == 0:
                        pivalt_b = float(orderbook_tickers_dict[vd[1]]['b'])
                        if vd[2].find(alt) == 0:
                            alttgt_b = float(orderbook_tickers_dict[vd[2]]['b'])
                            roi = tgtpiv_b * pivalt_b * alttgt_b
                            if roi > minROI:
                                data.append({
                                        'serial':1,
                                        'roi':roi,
                                        'target':tgt,
                                        '1st':[vd[0], tgtpiv_b, 'sell'],
                                        '2nd':[vd[1], pivalt_b, 'sell'],
                                        '3rd':[vd[2], alttgt_b, 'sell']
                                    })
                        else:
                            tgtalt_a = float(orderbook_tickers_dict[vd[2]]['a'])
                            roi = (tgtpiv_b * pivalt_b) / tgtalt_a
                            if roi > minROI:
                                data.append({
                                        'serial':2,
                                        'roi':roi,
                                        'target':tgt,
                                        '1st':[vd[0], tgtpiv_b, 'sell'],
                                        '2nd':[vd[1], pivalt_b, 'sell'],
                                        '3rd':[vd[2], tgtalt_a, 'buy']
                                    })
                    else:
                        altpiv_a = float(orderbook_tickers_dict[vd[1]]['a'])
                        if vd[2].find(alt) == 0:
                            alttgt_b = float(orderbook_tickers_dict[vd[2]]['b'])
                            roi = (tgtpiv_b / altpiv_a) * alttgt_b
                            if roi > minROI:
                                data.append({
                                        'serial':3,
                                        'roi':roi,
                                        'target':tgt,
                                        '1st':[vd[0], tgtpiv_b, 'sell'],
                                        '2nd':[vd[1], altpiv_a, 'buy'],
                                        '3rd':[vd[2], alttgt_b, 'sell']
                                    })
                        else:
                            tgtalt_a = float(orderbook_tickers_dict[vd[2]]['a'])
                            roi = (tgtpiv_b / altpiv_a) / tgtalt_a
                            if roi > minROI:
                                data.append({
                                        'serial':4,
                                        'roi':roi,
                                        'target':tgt,
                                        '1st':[vd[0], tgtpiv_b, 'sell'],
                                        '2nd':[vd[1], altpiv_a, 'buy'],
                                        '3rd':[vd[2], tgtalt_a, 'buy']
                                    })
                else:
                    pivtgt_a = float(orderbook_tickers_dict[vd[0]]['a'])
                    if vd[1].find(piv) == 0:
                        pivalt_b = float(orderbook_tickers_dict[vd[1]]['b'])
                        if vd[2].find(alt) == 0:
                            alttgt_b = float(orderbook_tickers_dict[vd[2]]['b'])
                            roi = 1 / ((pivtgt_a / pivalt_b) / alttgt_b)
                            if roi > minROI:
                                data.append({
                                        'serial':5,
                                        'roi':roi,
                                        'target':tgt,
                                        '1st':[vd[0], pivtgt_a, 'buy'],
                                        '2nd':[vd[1], pivalt_b, 'sell'],
                                        '3rd':[vd[2], alttgt_b, 'sell']
                                    })
                        else:
                            tgtalt_a = float(orderbook_tickers_dict[vd[2]]['a'])
                            roi = 1 / ((pivtgt_a / pivalt_b) * tgtalt_a)
                            if roi > minROI:
                                data.append({
                                        'serial':6,
                                        'roi':roi,
                                        'target':tgt,
                                        '1st':[vd[0], pivtgt_a, 'buy'],
                                        '2nd':[vd[1], pivalt_b, 'sell'],
                                        '3rd':[vd[2], tgtalt_a, 'buy']
                                    })
                    else:
                        altpiv_a = float(orderbook_tickers_dict[vd[1]]['a'])
                        if vd[2].find(alt) == 0:
                            alttgt_b = float(orderbook_tickers_dict[vd[2]]['b'])
                            roi = 1 / ((pivtgt_a * altpiv_a) / alttgt_b)
                            if roi > minROI:
                                data.append({
                                        'serial':7,
                                        'roi':roi,
                                        'target':tgt,
                                        '1st':[vd[0], pivtgt_a, 'buy'],
                                        '2nd':[vd[1], altpiv_a, 'buy'],
                                        '3rd':[vd[2], alttgt_b, 'sell']
                                    })
                        else:
                            tgtalt_a = float(orderbook_tickers_dict[vd[2]]['a'])
                            roi = 1 / (pivtgt_a * altpiv_a * tgtalt_a)
                            if roi > minROI:
                                data.append({
                                        'serial':8,
                                        'roi':roi,
                                        'target':tgt,
                                        '1st':[vd[0], pivtgt_a, 'buy'],
                                        '2nd':[vd[1], altpiv_a, 'buy'],
                                        '3rd':[vd[2], tgtalt_a, 'buy']
                                    })
            except:
                continue
    print('elapsed_time:{}'.format(time.time() - start) + '[sec]')
    return data

bm = BinanceSocketManager(client)
bm.start_ticker_socket(update_orderbook_dict)
bm.start_user_socket(update_user)
bm.start()

