"""布林带策略"""

import numpy as np

from strategy.base import BaseStrategy


class BollingerStrategy(BaseStrategy):
    """
    布林带策略:
    - 价格触及下轨时买入
    - 价格触及上轨时卖出
    """

    def init(self):
        self.period = self.params.get("period", 20)
        self.std = self.params.get("std", 2.0)

    def next(self, i: int):
        if i < self.period + 1:
            return

        for code in self._codes:
            middle, upper, lower = self.bollinger_bands(code, self.period, self.std)
            if any(np.isnan(x) for x in [middle, upper, lower]):
                continue

            price = self.close(code)
            if price is None:
                continue

            pos = self.position_size(code)

            if price <= lower and pos == 0:
                self.buy(code, percent=1.0)

            elif price >= upper and pos > 0:
                self.sell_all(code)
