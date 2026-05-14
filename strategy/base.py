"""策略基类"""

import numpy as np
import pandas as pd


class BaseStrategy:
    """所有策略的基类。用户自定义策略需继承此类并实现 init() 和 next(i)。"""

    def __init__(self, params: dict | None = None):
        self.params = params or {}

        # 由引擎注入
        self._engine = None
        self._broker = None
        self._data: dict[str, pd.DataFrame] = {}
        self._dates: list[str] = []
        self._codes: list[str] = []
        self._current_idx: int = 0
        self._current_date: str = ""

    # ---- 便捷属性 ----

    @property
    def cash(self) -> float:
        return self._broker.cash

    @property
    def positions(self):
        return self._broker.positions

    @property
    def trades(self):
        return self._broker.trades

    # ---- 数据访问 ----

    def get_bar(self, code: str, offset: int = 0) -> dict | None:
        """获取某标的当前(或偏移)bar的数据。offset=-1 表示上一个bar。"""
        idx = self._current_idx + offset
        if idx < 0 or idx >= len(self._dates):
            return None
        date = self._dates[idx]
        df = self._data.get(code)
        if df is None:
            return None
        rows = df[df["date"] == date]
        if rows.empty:
            return None
        return rows.iloc[0].to_dict()

    def close(self, code: str, offset: int = 0) -> float | None:
        bar = self.get_bar(code, offset)
        if bar is None:
            return None
        v = bar.get("close")
        return float(v) if v is not None and not np.isnan(v) else None

    def open(self, code: str, offset: int = 0) -> float | None:
        bar = self.get_bar(code, offset)
        if bar is None:
            return None
        v = bar.get("open")
        return float(v) if v is not None and not np.isnan(v) else None

    def high(self, code: str, offset: int = 0) -> float | None:
        bar = self.get_bar(code, offset)
        if bar is None:
            return None
        v = bar.get("high")
        return float(v) if v is not None and not np.isnan(v) else None

    def low(self, code: str, offset: int = 0) -> float | None:
        bar = self.get_bar(code, offset)
        if bar is None:
            return None
        v = bar.get("low")
        return float(v) if v is not None and not np.isnan(v) else None

    def volume(self, code: str, offset: int = 0) -> float | None:
        bar = self.get_bar(code, offset)
        if bar is None:
            return None
        v = bar.get("volume")
        return float(v) if v is not None and not np.isnan(v) else None

    def pct_change(self, code: str, offset: int = 0) -> float:
        bar = self.get_bar(code, offset)
        if bar is None:
            return 0.0
        v = bar.get("pct_change")
        return float(v) if v is not None and not np.isnan(v) else 0.0

    def get_closes(self, code: str, lookback: int | None = None) -> list[float]:
        """获取某标的的收盘价序列（到当前bar为止）"""
        df = self._data.get(code)
        if df is None:
            return []
        current = self._current_idx + 1
        start = 0 if lookback is None else max(0, current - lookback)
        vals = df["close"].iloc[start:current].tolist()
        return [float(v) for v in vals if v is not None and not np.isnan(v)]

    def sma(self, code: str, period: int) -> list[float]:
        """简单移动平均"""
        closes = self.get_closes(code)
        if len(closes) < period:
            return [np.nan] * len(closes)
        s = pd.Series(closes)
        return s.rolling(window=period).mean().tolist()

    def ema(self, code: str, period: int) -> list[float]:
        """指数移动平均"""
        closes = self.get_closes(code)
        if len(closes) < period:
            return [np.nan] * len(closes)
        s = pd.Series(closes)
        return s.ewm(span=period, adjust=False).mean().tolist()

    def macd(self, code: str, fast: int = 12, slow: int = 26, signal: int = 9):
        """返回 (macd_line, signal_line, histogram) 的最后一个值"""
        closes = self.get_closes(code)
        if len(closes) < slow + signal:
            return np.nan, np.nan, np.nan
        s = pd.Series(closes)
        ema_fast = s.ewm(span=fast, adjust=False).mean()
        ema_slow = s.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        return (float(macd_line.iloc[-1]), float(signal_line.iloc[-1]), float(histogram.iloc[-1]))

    def rsi(self, code: str, period: int = 14) -> float:
        """RSI 指标的最后一个值"""
        closes = self.get_closes(code)
        if len(closes) < period + 1:
            return np.nan
        s = pd.Series(closes)
        delta = s.diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return float(rsi.iloc[-1]) if not np.isnan(rsi.iloc[-1]) else np.nan

    def bollinger_bands(self, code: str, period: int = 20, std: float = 2.0):
        """返回 (middle, upper, lower) 最后一个值"""
        closes = self.get_closes(code)
        if len(closes) < period:
            return np.nan, np.nan, np.nan
        s = pd.Series(closes)
        middle = s.rolling(window=period).mean()
        std_dev = s.rolling(window=period).std()
        upper = middle + std * std_dev
        lower = middle - std * std_dev
        return (float(middle.iloc[-1]), float(upper.iloc[-1]), float(lower.iloc[-1]))

    def get_position(self, code: str):
        return self._broker.get_position(code)

    def position_size(self, code: str) -> int:
        return self._broker.get_total_size(code)

    # ---- 交易 ----

    def buy(self, code: str, size: int | None = None, percent: float | None = None):
        """买入。指定 size(股数) 或 percent(资金比例)。"""
        price = self.close(code)
        if price is None:
            return

        pct = self.pct_change(code)

        if percent is not None:
            # 按可用资金的百分比计算买入金额
            amount = self._broker.cash * percent
            size = int(amount / price)

        if size is None or size <= 0:
            return

        self._broker.buy(code, price, size, self._current_date, pct)

    def sell(self, code: str, size: int | None = None, percent: float | None = None):
        """卖出。指定 size(股数) 或 percent(持仓比例)。"""
        price = self.close(code)
        if price is None:
            return

        pct = self.pct_change(code)

        if percent is not None:
            pos = self._broker.get_position(code)
            size = int(pos.size * percent)

        if size is None or size <= 0:
            return

        self._broker.sell(code, price, size, self._current_date, pct)

    def sell_all(self, code: str):
        """清仓某标的"""
        pos = self._broker.get_position(code)
        if pos.size > 0:
            self.sell(code, size=pos.size)

    # ---- 子类实现 ----

    def init(self):
        """策略初始化，子类重写"""
        pass

    def next(self, i: int):
        """每个bar调用一次，子类必须重写"""
        raise NotImplementedError("子类必须实现 next(i) 方法")
