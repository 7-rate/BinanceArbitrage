#coding utf8
import time
import math
import itertools
import threading
import configparser
from binance.client import Client
from binance.websockets import BinanceSocketManager

#TODO 実取引
#TODO 高速化対応
#TODO 起動時にasset_balancesを更新する
#TODO 切り上げ切捨て対応

# apikeyを取得
config = configparser.ConfigParser()
config.read('./config.ini')
api_key = config.get('api', 'key')
api_secret = config.get('api', 'secret')

# 手数料設定
commission = 0.00075 * 3

# 利益率設定
#minROI = 1.0003 #TODO 暫定
minROI = 0.997
minROI += commission

# 支払い用BNBの最低量設定
minBNB = 0.3

# 取引量マージン(倍率)
volumeMargin = 0.9

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

# 取引の制限量取得
exchange_info = client.get_exchange_info()
minQtyInfo = {}
for sym in exchange_info['symbols']:
    for fil in sym['filters']:
        if fil['filterType'] == 'LOT_SIZE':
            minQtyInfo[sym['symbol']] = float(fil['minQty'])
            break

# サーバ-クライアント間レイテンシ確認
def test_time():
    print('server time - client time =', client.get_server_time()['serverTime']-int(time.time()*1000))

# callback function for start_ticker_socket
def update_orderbook_dict(msg):
    for d in msg:
        orderbook_tickers_dict[d['s']] = d
    data = arbitrageCheck()
    transaction = getBestTransaction(data)
    print(transaction)

# callback function for start_user_socket
def update_user(msg):
    if msg['e'] == 'executionReport':
        pass
    else:
        balances = msg['B']
        for i in balances:
            asset_balances[i['a']] = i

# 全シンボルから有効なシンボルの組み合わせを返す
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
def arbitrageCheck():
    tgt = target
    data = []
    #start = time.time()
    for piv in pivots:
        for alt in alts:
            vd = validData(tgt, piv, alt)
            if len(vd) != 3:
                continue
            try:
                vd0, vd1, vd2 = vd
                if vd0.find(tgt) == 0:
                    tgtpiv_b = float(orderbook_tickers_dict[vd0]['b'])
                    if vd1.find(piv) == 0:
                        pivalt_b = float(orderbook_tickers_dict[vd1]['b'])
                        if vd2.find(alt) == 0:
                            alttgt_b = float(orderbook_tickers_dict[vd2]['b'])
                            roi = tgtpiv_b * pivalt_b * alttgt_b
                            if roi > minROI:
                                data.append({'serial':1, 'roi':roi, 'target':tgt,
                                        '1st':[vd0, tgtpiv_b, 'sell'],
                                        '2nd':[vd1, pivalt_b, 'sell'],
                                        '3rd':[vd2, alttgt_b, 'sell'] })
                        else:
                            tgtalt_a = float(orderbook_tickers_dict[vd2]['a'])
                            roi = (tgtpiv_b * pivalt_b) / tgtalt_a
                            if roi > minROI:
                                data.append({
                                        'serial':2, 'roi':roi, 'target':tgt,
                                        '1st':[vd0, tgtpiv_b, 'sell'],
                                        '2nd':[vd1, pivalt_b, 'sell'],
                                        '3rd':[vd2, tgtalt_a, 'buy'] })
                    else:
                        altpiv_a = float(orderbook_tickers_dict[vd1]['a'])
                        if vd2.find(alt) == 0:
                            alttgt_b = float(orderbook_tickers_dict[vd2]['b'])
                            roi = (tgtpiv_b / altpiv_a) * alttgt_b
                            if roi > minROI:
                                data.append({
                                        'serial':3, 'roi':roi, 'target':tgt,
                                        '1st':[vd0, tgtpiv_b, 'sell'],
                                        '2nd':[vd1, altpiv_a, 'buy'],
                                        '3rd':[vd2, alttgt_b, 'sell'] })
                        else:
                            tgtalt_a = float(orderbook_tickers_dict[vd2]['a'])
                            roi = (tgtpiv_b / altpiv_a) / tgtalt_a
                            if roi > minROI:
                                data.append({
                                        'serial':4, 'roi':roi, 'target':tgt,
                                        '1st':[vd0, tgtpiv_b, 'sell'],
                                        '2nd':[vd1, altpiv_a, 'buy'],
                                        '3rd':[vd2, tgtalt_a, 'buy'] })
                else:
                    pivtgt_a = float(orderbook_tickers_dict[vd0]['a'])
                    if vd1.find(piv) == 0:
                        pivalt_b = float(orderbook_tickers_dict[vd1]['b'])
                        if vd2.find(alt) == 0:
                            alttgt_b = float(orderbook_tickers_dict[vd2]['b'])
                            roi = 1 / ((pivtgt_a / pivalt_b) / alttgt_b)
                            if roi > minROI:
                                data.append({
                                        'serial':5, 'roi':roi, 'target':tgt,
                                        '1st':[vd0, pivtgt_a, 'buy'],
                                        '2nd':[vd1, pivalt_b, 'sell'],
                                        '3rd':[vd2, alttgt_b, 'sell'] })
                        else:
                            tgtalt_a = float(orderbook_tickers_dict[vd2]['a'])
                            roi = 1 / ((pivtgt_a / pivalt_b) * tgtalt_a)
                            if roi > minROI:
                                data.append({
                                        'serial':6, 'roi':roi, 'target':tgt,
                                        '1st':[vd0, pivtgt_a, 'buy'],
                                        '2nd':[vd1, pivalt_b, 'sell'],
                                        '3rd':[vd2, tgtalt_a, 'buy'] })
                    else:
                        altpiv_a = float(orderbook_tickers_dict[vd1]['a'])
                        if vd2.find(alt) == 0:
                            alttgt_b = float(orderbook_tickers_dict[vd2]['b'])
                            roi = 1 / ((pivtgt_a * altpiv_a) / alttgt_b)
                            if roi > minROI:
                                data.append({
                                        'serial':7, 'roi':roi, 'target':tgt,
                                        '1st':[vd0, pivtgt_a, 'buy'],
                                        '2nd':[vd1, altpiv_a, 'buy'],
                                        '3rd':[vd2, alttgt_b, 'sell'] })
                        else:
                            tgtalt_a = float(orderbook_tickers_dict[vd2]['a'])
                            roi = 1 / (pivtgt_a * altpiv_a * tgtalt_a)
                            if roi > minROI:
                                data.append({
                                        'serial':8, 'roi':roi, 'target':tgt,
                                        '1st':[vd0, pivtgt_a, 'buy'],
                                        '2nd':[vd1, altpiv_a, 'buy'],
                                        '3rd':[vd2, tgtalt_a, 'buy'] })
            except:
                continue
    #print('elapsed_time:{}'.format(time.time() - start) + '[sec]')
    return data

# 引数の通貨の持っている量取得
def getAssetBalance(asset):
    return 0.0000001 #TODO デバッグ用暫定
    try:
        return float(asset_balances(asset))
    except:
        return 0.0

# 手数料支払い用のBNB量が十分か
def enoughBNB():
    BNBbalance = getAssetBalance
    return True if BNBbalance > minBNB else False


# 利益が出る裁定機会の中から最適な取引を返す
def getBestTransaction(data):

    # 最良ROIから順番にチェック。板に出ている取引量が十分か？(マージン込)
    sortedData = sorted(data, key=lambda x:x['roi'], reverse=True)
    for data in sortedData:
        tgtAsset = getAssetBalance(asset=data['target']) # TODO 全量取引に回している。定数で取引量を固定したほうがいいか？
        ticker_1st = orderbook_tickers_dict[data['1st'][0]]
        ticker_2nd = orderbook_tickers_dict[data['2nd'][0]]
        ticker_3rd = orderbook_tickers_dict[data['3rd'][0]]
        #1st
        if data['1st'][2] == 'buy':
            secondAsset = tgtAsset / data['1st'][1]
            if float(ticker_1st['A']) * volumeMargin > secondAsset:
                if secondAsset < minQtyInfo[data['1st'][0]]:
                    print(f'{secondAsset}')
                    continue
        else:
            secondAsset = tgtAsset * data['1st'][1]
            if float(ticker_1st['B']) * volumeMargin > tgtAsset:
                if tgtAsset < minQtyInfo[data['1st'][0]]:
                    print(f'{secondAsset}')
                    continue
        #2nd
        if data['2nd'][2] == 'buy':
            thirdAsset = secondAsset / data['2nd'][1]
            if float(ticker_2nd['A']) * volumeMargin > thirdAsset:
                if thirdAsset < minQtyInfo[data['1st'][0]]:
                    continue
        else:
            thirdAsset = secondAsset * data['2nd'][1]
            if float(ticker_2nd['B']) * volumeMargin > secondAsset:
                if secondAsset < minQtyInfo[data['1st'][0]]:
                    continue
        #3rd
        if data['3rd'][2] == 'buy':
            newTgtAsset = thirdAsset / data['3rd'][1]
            if float(ticker_3rd['A']) * volumeMargin > newTgtAsset:
                if newTgtAsset < minQtyInfo[data['1st'][0]]:
                    continue
        else:
            newTgtAsset = thirdAsset * data['3rd'][1]
            if float(ticker_3rd['B']) * volumeMargin > thirdAsset:
                if thirdAsset < minQtyInfo[data['1st'][0]]:
                    continue
        return data
    return None

bm = BinanceSocketManager(client)
bm.start_ticker_socket(update_orderbook_dict)
bm.start_user_socket(update_user)
bm.start()


