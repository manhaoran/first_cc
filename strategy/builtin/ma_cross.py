"""双均线交叉策略"""

import numpy as np

from strategy.base import BaseStrategy


class MACrossStrategy(BaseStrategy):
    """
    双均线交叉策略:
    - 快线上穿慢线时买入
    - 快线下穿慢线时卖出
    """

    def init(self):
        self.fast = self.params.get("fast", 5)
        self.slow = self.params.get("slow", 20)
        self._prev_fast = {}
        self._prev_slow = {}

    def next(self, i: int):
        if i < self.slow + 1:
            return

        for code in self._codes:
            sma_fast = self.sma(code, self.fast)
            sma_slow = self.sma(code, self.slow)

            if len(sma_fast) < 2:
                continue

            cur_fast = sma_fast[-1]
            cur_slow = sma_slow[-1]
            prev_fast = sma_fast[-2]
            prev_slow = sma_slow[-2]

            if any(np.isnan(x) for x in [cur_fast, cur_slow, prev_fast, prev_slow]):
                continue

            pos = self.position_size(code)

            # 金叉：快线上穿慢线
            if prev_fast <= prev_slow and cur_fast > cur_slow:
                if pos == 0:
                    self.buy(code, percent=1.0)

            # 死叉：快线下穿慢线
            elif prev_fast >= prev_slow and cur_fast < cur_slow:
                if pos > 0:
                    self.sell_all(code)
