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

# 利益率設定
minROI = 1.0000
#手数料設定
commission = 0.00075 * 3

# 全コイン種読み込み
f = open('alts.txt')
alts = f.read().split('\n')
f.close()

# 各配列初期化
orderbook_tickers_dict = {}
trade_status_dict = {}
asset_balances = {}
symbols = []
target = 'BTC'
pivots = ['BTC', 'ETH', 'USDT', 'BUSD', 'TUSD', 'USDC', 'PAX']


# クライアント初期化
client = Client(api_key, api_secret, {'timeout':600})

# シンボル更新
orderbook_tickers = client.get_orderbook_tickers()
for ticker in orderbook_tickers:
    symbols.append(ticker['symbol'])

# サーバ-クライアント間レイテンシ確認
def test_time():
    print('server time - client time =', client.get_server_time()['serverTime']-int(time.time()*1000))

# callback function for start_ticker_socket
def update_orderbook_dict(msg):
    for d in msg:
        orderbook_tickers_dict[d['s']] = d
    data = ArbitrageCheck()
#    for element in data:
#        print(element)

# callback function for start_user_socket
def update_user(msg):
    pass

def validData(tgt, piv, alt):
    validData = []
    if tgt+piv in symbols:
        validData.append(tgt+piv)
    elif piv+tgt in symbols:
        validData.append(piv+tgt)

    if piv+alt in symbols:
        validData.append(piv+alt)
    elif alt+piv in symbols:
        validData.append(alt+piv)

    if tgt+alt in symbols:
        validData.append(tgt+alt)
    elif alt+tgt in symbols:
        validData.append(alt+tgt)

    return validData

# 3通貨間アービトラージが可能か確認
def ArbitrageCheck():
    tgt = target
    data = []
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
                            roi -= commission
                            print('-1- roi:{}'.format(roi))
                            if roi > minROI:
                                print(orderbook_tickers_dict[vd[0]])
                                print(orderbook_tickers_dict[vd[1]])
                                print(orderbook_tickers_dict[vd[2]])
                        else:
                            tgtalt_a = float(orderbook_tickers_dict[vd[2]]['a'])
                            roi = (tgtpiv_b * pivalt_b) / tgtalt_a
                            roi -= commission
                            print('-2- roi:{}'.format(roi))
                            if roi > minROI:
                                print(orderbook_tickers_dict[vd[0]])
                                print(orderbook_tickers_dict[vd[1]])
                                print(orderbook_tickers_dict[vd[2]])
                    else:
                        altpiv_a = float(orderbook_tickers_dict[vd[1]]['a'])
                        if vd[2].find(alt) == 0:
                            alttgt_b = float(orderbook_tickers_dict[vd[2]]['b'])
                            roi = (tgtpiv_b / altpiv_a) * alttgt_b
                            roi -= commission
                            print('-3- roi:{}'.format(roi))
                            if roi > minROI:
                                print(orderbook_tickers_dict[vd[0]])
                                print(orderbook_tickers_dict[vd[1]])
                                print(orderbook_tickers_dict[vd[2]])

                        else:
                            tgtalt_a = float(orderbook_tickers_dict[vd[2]]['a'])
                            roi = (tgtpiv_b / altpiv_a) / tgtalt_a
                            roi -= commission
                            print('-4- roi:{}'.format(roi))
                            if roi > minROI:
                                print(orderbook_tickers_dict[vd[0]])
                                print(orderbook_tickers_dict[vd[1]])
                                print(orderbook_tickers_dict[vd[2]])

                else:
                    pivtgt_a = float(orderbook_tickers_dict[vd[0]]['a'])
                    if vd[1].find(piv) == 0:
                        pivalt_b = float(orderbook_tickers_dict[vd[1]]['b'])
                        if vd[2].find(alt) == 0:
                            alttgt_b = float(orderbook_tickers_dict[vd[2]]['b'])
                            roi = 1 / ((pivtgt_a / pivalt_b) / alttgt_b)
                            roi -= commission
                            print('-5- roi:{}'.format(roi))
                            if roi > minROI:
                                print(orderbook_tickers_dict[vd[0]])
                                print(orderbook_tickers_dict[vd[1]])
                                print(orderbook_tickers_dict[vd[2]])

                        else:
                            tgtalt_a = float(orderbook_tickers_dict[vd[2]]['a'])
                            roi = 1 / ((pivtgt_a / pivalt_b) * tgtalt_a)
                            roi -= commission
                            print('-6- roi:{}'.format(roi))
                            if roi > minROI:
                                print(orderbook_tickers_dict[vd[0]])
                                print(orderbook_tickers_dict[vd[1]])
                                print(orderbook_tickers_dict[vd[2]])

                    else:
                        altpiv_a = float(orderbook_tickers_dict[vd[1]]['a'])
                        if vd[2].find(alt) == 0:
                            alttgt_b = float(orderbook_tickers_dict[vd[2]]['b'])
                            roi = 1 / ((pivtgt_a * altpiv_a) / alttgt_b)
                            roi -= commission
                            print('-7- roi:{}'.format(roi))
                            if roi > minROI:
                                print(orderbook_tickers_dict[vd[0]])
                                print(orderbook_tickers_dict[vd[1]])
                                print(orderbook_tickers_dict[vd[2]])

                        else:
                            tgtalt_a = float(orderbook_tickers_dict[vd[2]]['a'])
                            roi = 1 / (pivtgt_a * altpiv_a * tgtalt_a)
                            roi -= commission
                            print('-8- roi:{}'.format(roi))
                            if roi > minROI:
                                print(orderbook_tickers_dict[vd[0]])
                                print(orderbook_tickers_dict[vd[1]])
                                print(orderbook_tickers_dict[vd[2]])

            except:
                continue
            # try:
            #     tgtpiv_b, tgtpiv_a = float(orderbook_tickers_dict[tgt+piv]['b']), float(orderbook_tickers_dict[tgt+piv]['a'])
            #     altpiv_b, altpiv_a = float(orderbook_tickers_dict[alt+piv]['b']), float(orderbook_tickers_dict[alt+piv]['a'])
            #     try:
            #         alttgt_b, alttgt_a = float(orderbook_tickers_dict[alt+tgt]['b']), float(orderbook_tickers_dict[alt+tgt]['a'])
            #         # tgt → alt → piv → tgt
            #         roi = altpiv_b / (alttgt_a * tgtpiv_a)
            #         roi -= commission
            #         if roi > minROI:
            #             data.append(
            #                 {'roi':roi,
            #                 'debug':1,
            #                 'target':tgt,
            #                 '1st':[alt+tgt, alttgt_a, 'b'],
            #                 '2nd':[alt+piv, altpiv_b, 's'],
            #                 '3rd':[tgt+piv, tgtpiv_a, 'b']
            #                 })
            #         # tgt → piv → alt → tgt
            #         roi = (tgtpiv_b / altpiv_a) * alttgt_b
            #         roi -= commission
            #         if roi > minROI:
            #             data.append(
            #                 {'roi':roi,
            #                 'debug':2,
            #                 'target':tgt,
            #                 '1st':[tgt+piv, tgtpiv_b, 'b'],
            #                 '2nd':[alt+piv, altpiv_a, 'b'],
            #                 '3rd':[alt+tgt, alttgt_b, 's']
            #                 })
            #     except:
            #         alttgt_b, alttgt_a = float(orderbook_tickers_dict[tgt+alt]['b']), float(orderbook_tickers_dict[tgt+alt]['a'])
            #         # tgt → alt → piv → tgt
            #         roi = (altpiv_b * alttgt_a) / tgtpiv_a
            #         roi -= commission
            #         if roi > minROI:
            #             data.append(
            #                 {'roi':roi,
            #                 'debug':3,
            #                 'target':tgt,
            #                 '1st':[tgt+alt, alttgt_a, 's'],
            #                 '2nd':[alt+piv, altpiv_b, 's'],
            #                 '3rd':[tgt+piv, tgtpiv_a, 'b']
            #                 })
            #         # tgt → alt → piv → tgt
            #         roi = altpiv_a /( alttgt_b * tgtpiv_a )
            #         roi -= commission
            #         if roi > minROI:
            #             data.append(
            #                 {'roi':roi,
            #                 'debug':4,
            #                 'target':tgt,
            #                 '1st':[tgt+piv, tgtpiv_b, 'b'],
            #                 '2nd':[alt+piv, altpiv_a, 'b'],
            #                 '3rd':[tgt+alt, alttgt_b, 'b']
            #                 })
            # except:
            #     continue
    return data

bm = BinanceSocketManager(client)
bm.start_ticker_socket(update_orderbook_dict)
bm.start_user_socket(update_user)
bm.start()

