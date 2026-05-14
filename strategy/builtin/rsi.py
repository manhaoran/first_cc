"""RSI 超买超卖策略"""

import numpy as np

from strategy.base import BaseStrategy


class RSIStrategy(BaseStrategy):
    """
    RSI 策略:
    - RSI 低于超卖线时买入
    - RSI 高于超买线时卖出
    """

    def init(self):
        self.period = self.params.get("period", 14)
        self.oversold = self.params.get("oversold", 30)
        self.overbought = self.params.get("overbought", 70)

    def next(self, i: int):
        if i < self.period + 2:
            return

        for code in self._codes:
            rsi_val = self.rsi(code, self.period)
            if np.isnan(rsi_val):
                continue

            pos = self.position_size(code)

            if rsi_val < self.oversold and pos == 0:
                self.buy(code, percent=1.0)

            elif rsi_val > self.overbought and pos > 0:
                self.sell_all(code)
