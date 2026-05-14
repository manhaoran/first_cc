"""MACD 策略"""

import numpy as np

from strategy.base import BaseStrategy


class MACDStrategy(BaseStrategy):
    """
    MACD 策略:
    - MACD 线上穿信号线时买入
    - MACD 线下穿信号线时卖出
    """

    def init(self):
        self.fast = self.params.get("fast", 12)
        self.slow = self.params.get("slow", 26)
        self.signal = self.params.get("signal", 9)
        self._prev_hist = {}

    def next(self, i: int):
        if i < self.slow + self.signal + 1:
            return

        for code in self._codes:
            dl, sl, hist = self.macd(code, self.fast, self.slow, self.signal)
            if any(np.isnan(x) for x in [dl, sl, hist]):
                continue

            prev_hist = self._prev_hist.get(code, 0)
            pos = self.position_size(code)

            # 金叉：柱状图由负转正
            if prev_hist <= 0 and hist > 0:
                if pos == 0:
                    self.buy(code, percent=1.0)

            # 死叉：柱状图由正转负
            elif prev_hist >= 0 and hist < 0:
                if pos > 0:
                    self.sell_all(code)

            self._prev_hist[code] = hist
