"""Dual Thrust 突破策略"""

import numpy as np

from strategy.base import BaseStrategy


class DualThrustStrategy(BaseStrategy):
    """
    Dual Thrust 策略:
    - 价格突破上轨时买入
    - 价格跌破下轨时卖出
    适用于日内/短线交易
    """

    def init(self):
        self.lookback = int(self.params.get("lookback", 20))
        self.k1 = float(self.params.get("k1", 0.7))
        self.k2 = float(self.params.get("k2", 0.7))

    def next(self, i: int):
        if i < self.lookback + 2:
            return

        for code in self._codes:
            df = self._data.get(code)
            if df is None or len(df) < self.lookback + 1:
                continue

            # 计算 Range
            closes = self.get_closes(code, self.lookback)
            highs = [self.high(code, -j) for j in range(self.lookback, 0, -1)]
            lows = [self.low(code, -j) for j in range(self.lookback, 0, -1)]

            highs = [h for h in highs if h is not None]
            lows = [l for l in lows if l is not None]
            closes_valid = [c for c in closes if c is not None]

            if len(highs) < self.lookback or len(lows) < self.lookback:
                continue

            hh = max(highs[:-1])  # 前N日最高价（不含当日）
            ll = min(lows[:-1])   # 前N日最低价
            hc = max(closes_valid[:-1])  # 前N日最高收盘价
            lc = min(closes_valid[:-1])  # 前N日最低收盘价

            range_val = max(hh - lc, hc - ll)

            upper_bound = closes_valid[-2] + self.k1 * range_val if len(closes_valid) >= 2 else 0
            lower_bound = closes_valid[-2] - self.k2 * range_val if len(closes_valid) >= 2 else 0

            price = self.close(code)
            if price is None:
                continue

            pos = self.position_size(code)

            if price > upper_bound and pos == 0:
                self.buy(code, percent=1.0)

            elif price < lower_bound and pos > 0:
                self.sell_all(code)
