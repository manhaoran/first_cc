"""示例自定义策略 - 双均线 + 成交量过滤"""

from strategy.base import BaseStrategy


class VolumeFilterMACross(BaseStrategy):
    """
    双均线交叉 + 成交量放大过滤:
    - 快线上穿慢线 且 当日成交量大于20日均量的1.5倍时买入
    - 快线下穿慢线时卖出
    """

    def init(self):
        self.fast = int(self.params.get("fast", 5))
        self.slow = int(self.params.get("slow", 20))
        self.vol_ratio = float(self.params.get("vol_ratio", 1.5))

    def next(self, i: int):
        if i < self.slow + 5:
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

            # 计算20日均量
            volumes = []
            for j in range(20):
                v = self.volume(code, -j)
                if v is not None:
                    volumes.append(v)

            if len(volumes) < 20:
                continue

            avg_vol = sum(volumes) / len(volumes)
            cur_vol = self.volume(code)
            if cur_vol is None:
                continue

            pos = self.position_size(code)

            # 金叉 + 成交量放大
            if prev_fast <= prev_slow and cur_fast > cur_slow:
                if pos == 0 and cur_vol > avg_vol * self.vol_ratio:
                    self.buy(code, percent=1.0)

            # 死叉
            elif prev_fast >= prev_slow and cur_fast < cur_slow:
                if pos > 0:
                    self.sell_all(code)
