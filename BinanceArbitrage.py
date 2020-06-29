#coding utf8
import time
import math
import itertools
import threading
import configparser
from binance.client import Client
from binance.websockets import BinanceSocketManager
import logging

class BinanceArbitrage:
    def __init__(self, client, target, startingAmount, minROI, commission, transact):
        self.client = client
        self.target = target                    # target coin
        self.startingAmount = startingAmount    # 最初の取引に使う量
        self.minROI = minROI + (commission * 3) # 手数料を考慮した利益率設定
        self.volumeMargin = 0.9                 # 板に出ているコイン量のマージン倍率(少なめに見積る)
        self.transact = transact

        # ロガー初期化
        self.logger = logging.getLogger('BinanceArbitrage')
        self.logger.setLevel(logging.DEBUG)
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s\t[%(levelname)s]\t%(message)s')
        ch.setFormatter(formatter)
        self.logger.addHandler(ch)

        # 全コイン種取得
        with open('alts.txt') as f:
            self.alts = f.read().split('\n')

        self.orderbook_tickers_dict = {}
        self.trade_status_dict = {}
        self.pivots = ['BTC', 'ETH', 'USDT', 'BUSD', 'TUSD', 'USDC', 'PAX']
        self.minBNB = 0.3 # 支払い用BNBの最低量設定

        # シンボル取得
        self.symbols = set()
        orderbook_tickers = client.get_orderbook_tickers()
        for ticker in orderbook_tickers:
            self.symbols.add(ticker['symbol'])

        # 取引の最小数取得
        exchange_info = client.get_exchange_info()
        self.minQtyInfo = {}
        for sym in exchange_info['symbols']:
            for fil in sym['filters']:
                if fil['filterType'] == 'LOT_SIZE':
                    self.minQtyInfo[sym['symbol']] = float(fil['minQty'])
                    break

        # アカウント情報の更新。普段はコールバックから呼ばれるが、初期化タイミングでも呼ぶ。
        self.update_user()

        # ソケットの確立
        # 開始はstartArbitrage()で行う
        self.bm = BinanceSocketManager(client)
        self.bm.start_ticker_socket(self.update_orderbook_dict)
        self.bm.start_user_socket(self.update_user)

    # ログ出力ラッパー
    def log_debug(self, msg):
        self.logger.debug(msg)

    def log_info(self, msg):
        self.logger.info(msg)

    def log_warn(self, msg):
        self.logger.warn(msg)

    def log_error(self, msg):
        self.logger.error(msg)

    # BinanceSocketManagerからコールバックされる
    # ここでメイン処理をラッチする
    def update_orderbook_dict(self, msg):
        for d in msg:
            self.orderbook_tickers_dict[d['s']] = d
        data = self.arbitrageCheck()                 # 裁定機会を探す
        transaction = self.getBestTransaction(data)  # 最も優れた裁定機会を取得
        if transaction:
            self.log_debug(transaction)
            if self.transact:
                # TODO 本取引。ここで行うのではなく、別スレッドを立てる
                pass


    # BinanceSocketManagerからコールバックされる
    # ここでアカウントの資産を更新する
    def update_user(self, msg=0):
        self.asset_balance = client.get_account()['balances']
            
        # 所持金と手数料用のBNBチェック
        targetAmount = float(self.getFreeAssetBalance(self.target))
        self.log_info('{} Amount = {}'.format(self.target, targetAmount))
        
        bnbAmount = float(self.getFreeAssetBalance('BNB'))
        self.log_info('BNB Amount = {}'.format(bnbAmount))

        if self.transact:
            if self.startingAmount > targetAmount:
                raise Exception('所持金が少ないです')
            if self.minBNB > bnbAmount:
                raise Exception('手数料用BNBが少ないです')

    # 裁定取引を開始()
    def startArbitrage(self):
        self.bm.start()

    # サーバ-クライアントの時間差分確認
    def test_time(self):
        self.log_info('server time - client time ={}'.format(client.get_server_time()['serverTime']-int(time.time()*1000)) + '[msec]')

    # 所持金の取得
    def getFreeAssetBalance(self, asset):
        for ab in self.asset_balance:
            if ab['asset'] == asset:
                return ab['free']

    # 全シンボルから有効なシンボルの組み合わせを返す
    def validData(self, tgt, piv, alt):
        validData = []
        if tgt+piv in self.symbols:
            validData.append(tgt+piv)
        elif piv+tgt in self.symbols:
            validData.append(piv+tgt)

        if piv+alt in self.symbols:
            validData.append(piv+alt)
        elif alt+piv in self.symbols:
            validData.append(alt+piv)

        if tgt+alt in self.symbols:
            validData.append(tgt+alt)
        elif alt+tgt in self.symbols:
            validData.append(alt+tgt)

        return validData

    # 3通貨間アービトラージが可能か確認
    def arbitrageCheck(self):
        tgt = self.target
        data = []
        start = time.time()
        for piv in self.pivots:
            for alt in self.alts:
                vd = self.validData(tgt, piv, alt)
                if len(vd) != 3:
                    continue
                try:
                    vd0, vd1, vd2 = vd
                    if vd0.find(tgt) == 0:
                        tgtpiv_b = float(self.orderbook_tickers_dict[vd0]['b'])
                        if vd1.find(piv) == 0:
                            pivalt_b = float(self.orderbook_tickers_dict[vd1]['b'])
                            if vd2.find(alt) == 0:
                                alttgt_b = float(self.orderbook_tickers_dict[vd2]['b'])
                                roi = tgtpiv_b * pivalt_b * alttgt_b
                                if roi > self.minROI:
                                    data.append({'serial':1, 'roi':roi, 'target':tgt,
                                            '1st':[vd0, tgtpiv_b, 'sell'],
                                            '2nd':[vd1, pivalt_b, 'sell'],
                                            '3rd':[vd2, alttgt_b, 'sell'] })
                            else:
                                tgtalt_a = float(self.orderbook_tickers_dict[vd2]['a'])
                                roi = (tgtpiv_b * pivalt_b) / tgtalt_a
                                if roi > self.minROI:
                                    data.append({
                                            'serial':2, 'roi':roi, 'target':tgt,
                                            '1st':[vd0, tgtpiv_b, 'sell'],
                                            '2nd':[vd1, pivalt_b, 'sell'],
                                            '3rd':[vd2, tgtalt_a, 'buy'] })
                        else:
                            altpiv_a = float(self.orderbook_tickers_dict[vd1]['a'])
                            if vd2.find(alt) == 0:
                                alttgt_b = float(self.orderbook_tickers_dict[vd2]['b'])
                                roi = (tgtpiv_b / altpiv_a) * alttgt_b
                                if roi > self.minROI:
                                    data.append({
                                            'serial':3, 'roi':roi, 'target':tgt,
                                            '1st':[vd0, tgtpiv_b, 'sell'],
                                            '2nd':[vd1, altpiv_a, 'buy'],
                                            '3rd':[vd2, alttgt_b, 'sell'] })
                            else:
                                tgtalt_a = float(self.orderbook_tickers_dict[vd2]['a'])
                                roi = (tgtpiv_b / altpiv_a) / tgtalt_a
                                if roi > self.minROI:
                                    data.append({
                                            'serial':4, 'roi':roi, 'target':tgt,
                                            '1st':[vd0, tgtpiv_b, 'sell'],
                                            '2nd':[vd1, altpiv_a, 'buy'],
                                            '3rd':[vd2, tgtalt_a, 'buy'] })
                    else:
                        pivtgt_a = float(self.orderbook_tickers_dict[vd0]['a'])
                        if vd1.find(piv) == 0:
                            pivalt_b = float(self.orderbook_tickers_dict[vd1]['b'])
                            if vd2.find(alt) == 0:
                                alttgt_b = float(self.orderbook_tickers_dict[vd2]['b'])
                                roi = 1 / ((pivtgt_a / pivalt_b) / alttgt_b)
                                if roi > self.minROI:
                                    data.append({
                                            'serial':5, 'roi':roi, 'target':tgt,
                                            '1st':[vd0, pivtgt_a, 'buy'],
                                            '2nd':[vd1, pivalt_b, 'sell'],
                                            '3rd':[vd2, alttgt_b, 'sell'] })
                            else:
                                tgtalt_a = float(self.orderbook_tickers_dict[vd2]['a'])
                                roi = 1 / ((pivtgt_a / pivalt_b) * tgtalt_a)
                                if roi > self.minROI:
                                    data.append({
                                            'serial':6, 'roi':roi, 'target':tgt,
                                            '1st':[vd0, pivtgt_a, 'buy'],
                                            '2nd':[vd1, pivalt_b, 'sell'],
                                            '3rd':[vd2, tgtalt_a, 'buy'] })
                        else:
                            altpiv_a = float(self.orderbook_tickers_dict[vd1]['a'])
                            if vd2.find(alt) == 0:
                                alttgt_b = float(self.orderbook_tickers_dict[vd2]['b'])
                                roi = 1 / ((pivtgt_a * altpiv_a) / alttgt_b)
                                if roi > self.minROI:
                                    data.append({
                                            'serial':7, 'roi':roi, 'target':tgt,
                                            '1st':[vd0, pivtgt_a, 'buy'],
                                            '2nd':[vd1, altpiv_a, 'buy'],
                                            '3rd':[vd2, alttgt_b, 'sell'] })
                            else:
                                tgtalt_a = float(self.orderbook_tickers_dict[vd2]['a'])
                                roi = 1 / (pivtgt_a * altpiv_a * tgtalt_a)
                                if roi > self.minROI:
                                    data.append({
                                            'serial':8, 'roi':roi, 'target':tgt,
                                            '1st':[vd0, pivtgt_a, 'buy'],
                                            '2nd':[vd1, altpiv_a, 'buy'],
                                            '3rd':[vd2, tgtalt_a, 'buy'] })
                except:
                    continue
        self.log_debug('arbitrageCheck elapsed_time:{}'.format((time.time() - start)*1000) + '[msec]')
        return data

    # 利益が出る裁定機会の中から最適な取引を返す
    def getBestTransaction(self, data):
        # 最良ROIから順番にチェック。板に出ている取引量が十分かの確認(マージン込)
        sortedData = sorted(data, key=lambda x:x['roi'], reverse=True)
        for data in sortedData:
            tgtAsset = self.startingAmount
            ticker_1st = self.orderbook_tickers_dict[data['1st'][0]]
            ticker_2nd = self.orderbook_tickers_dict[data['2nd'][0]]
            ticker_3rd = self.orderbook_tickers_dict[data['3rd'][0]]
            #1st
            if data['1st'][2] == 'buy':
                secondAsset = tgtAsset / data['1st'][1]
                if float(ticker_1st['A']) * self.volumeMargin > secondAsset:
                    if secondAsset < self.minQtyInfo[data['1st'][0]]:
                        continue
            else:
                secondAsset = tgtAsset * data['1st'][1]
                if float(ticker_1st['B']) * self.volumeMargin > tgtAsset:
                    if tgtAsset < self.minQtyInfo[data['1st'][0]]:
                        continue
            #2nd
            if data['2nd'][2] == 'buy':
                thirdAsset = secondAsset / data['2nd'][1]
                if float(ticker_2nd['A']) * self.volumeMargin > thirdAsset:
                    if thirdAsset < self.minQtyInfo[data['1st'][0]]:
                        continue
            else:
                thirdAsset = secondAsset * data['2nd'][1]
                if float(ticker_2nd['B']) * self.volumeMargin > secondAsset:
                    if secondAsset < self.minQtyInfo[data['1st'][0]]:
                        continue
            #3rd
            if data['3rd'][2] == 'buy':
                newTgtAsset = thirdAsset / data['3rd'][1]
                if float(ticker_3rd['A']) * self.volumeMargin > newTgtAsset:
                    if newTgtAsset < self.minQtyInfo[data['1st'][0]]:
                        continue
            else:
                newTgtAsset = thirdAsset * data['3rd'][1]
                if float(ticker_3rd['B']) * self.volumeMargin > thirdAsset:
                    if thirdAsset < self.minQtyInfo[data['1st'][0]]:
                        continue
            return data
        return None

#TODO 実取引(成り行き注文)
#TODO 切り上げ切捨て対応
#TODO テスト作成
#TODO ログファイル出力(order, order history, asset balance)
#TODO 安全装置(資産が減る or 約定しない時にプログラム停止)

if __name__ == "__main__":
    # apikeyを取得
    config = configparser.ConfigParser()
    config.read('./config.ini')
    api_key = config.get('api', 'key')
    api_secret = config.get('api', 'secret')

    # クライアント初期化
    client = Client(api_key, api_secret, {'timeout':600})

    #利益率、手数料、裁定取引に回す量の設定
    minROI = 1.0002
    commission = 0.00075
    startingAmount = 0.1

    ba = BinanceArbitrage(client, 'ETH', startingAmount, minROI, commission, False)
    ba.test_time()
    ba.startArbitrage()

