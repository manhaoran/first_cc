"""交易模拟器 - 管理资金、持仓、订单执行和费用计算"""

from dataclasses import dataclass, field
from datetime import datetime

from config import BacktestConfig


@dataclass
class Order:
    code: str
    action: str       # "buy" or "sell"
    size: int         # 股数 (100的整数倍)
    price: float      # 成交价
    date: str         # 成交日期
    filled: bool = False


@dataclass
class Trade:
    code: str
    action: str
    size: int
    price: float
    date: str
    commission: float = 0.0
    stamp_tax: float = 0.0


@dataclass
class Position:
    code: str
    size: int = 0            # 当前可卖股数
    unsettled: int = 0       # T+1 模式下当天买入未交割的股数
    avg_cost: float = 0.0    # 持仓均价


class Broker:
    def __init__(self, config: BacktestConfig):
        self.config = config
        self.cash: float = config.initial_cash
        self.positions: dict[str, Position] = {}
        self.orders: list[Order] = []
        self.trades: list[Trade] = []
        self._pending_settlements: list[tuple[str, int]] = []  # (code, size) to settle next bar

    # ---- 查询 ----

    def get_position(self, code: str) -> Position:
        if code not in self.positions:
            self.positions[code] = Position(code=code)
        return self.positions[code]

    def get_available(self, code: str) -> int:
        """可卖股数"""
        return self.get_position(code).size

    def get_total_size(self, code: str) -> int:
        """总持仓 (含未交割)"""
        pos = self.get_position(code)
        return pos.size + pos.unsettled

    def get_total_value(self, prices: dict[str, float]) -> float:
        """当前持仓总市值"""
        total = 0.0
        for code, pos in self.positions.items():
            total_size = pos.size + pos.unsettled
            if total_size > 0 and code in prices:
                total += total_size * prices[code]
        return total

    def get_equity(self, prices: dict[str, float]) -> float:
        return self.cash + self.get_total_value(prices)

    # ---- 订单 ----

    def _calc_commission(self, amount: float) -> float:
        fee = amount * self.config.commission_rate
        return max(fee, self.config.min_commission)

    def _calc_stamp_tax(self, amount: float) -> float:
        return amount * self.config.stamp_tax_rate

    def _is_limit_up(self, pct_change: float) -> bool:
        """判断是否涨停 (A股10%，科创板/创业板20%)"""
        return pct_change >= 9.8  # 实际涨停约9.9%-10%，留有容差

    def _is_limit_down(self, pct_change: float) -> bool:
        """判断是否跌停"""
        return pct_change <= -9.8

    def buy(self, code: str, price: float, size: int, date: str, pct_change: float = 0.0):
        """买入下单"""
        if size <= 0:
            return

        # 涨停检查
        if self.config.limit_up_no_buy and self._is_limit_up(pct_change):
            return

        # 确保是100的整数倍
        size = (size // 100) * 100
        if size == 0:
            return

        amount = price * size
        commission = self._calc_commission(amount)
        total_cost = amount + commission

        if self.cash < total_cost:
            # 资金不足，按可买数量调整
            affordable_size = int((self.cash - self._calc_commission(0)) / (price * 1.001))
            size = (affordable_size // 100) * 100
            if size == 0:
                return
            amount = price * size
            commission = self._calc_commission(amount)
            total_cost = amount + commission

        if self.cash < total_cost:
            return

        self.cash -= total_cost

        # 更新持仓
        pos = self.get_position(code)
        old_total = pos.size + pos.unsettled
        old_cost = pos.avg_cost

        if self.config.mode == "T+1":
            # T+1: 买入进入未交割，次日可卖
            new_total = old_total + size
            pos.avg_cost = ((old_cost * old_total) + amount) / new_total if new_total > 0 else price
            pos.unsettled += size
            self._pending_settlements.append((code, size))
        else:
            # T+0: 买入即可卖
            new_total = pos.size + size
            pos.avg_cost = ((old_cost * pos.size) + amount) / new_total if new_total > 0 else price
            pos.size += size

        trade = Trade(code=code, action="buy", size=size, price=price, date=date,
                      commission=commission, stamp_tax=0.0)
        self.trades.append(trade)

    def sell(self, code: str, price: float, size: int, date: str, pct_change: float = 0.0):
        """卖出下单"""
        if size <= 0:
            return

        # 跌停检查
        if self.config.limit_down_no_sell and self._is_limit_down(pct_change):
            return

        pos = self.get_position(code)
        size = min(size, pos.size)  # 不能超过可卖数量
        size = (size // 100) * 100
        if size == 0:
            return

        amount = price * size
        commission = self._calc_commission(amount)
        stamp_tax = self._calc_stamp_tax(amount)
        net_amount = amount - commission - stamp_tax

        self.cash += net_amount
        pos.size -= size

        # 如果清仓，重置均价
        if pos.size == 0 and pos.unsettled == 0:
            pos.avg_cost = 0.0

        trade = Trade(code=code, action="sell", size=size, price=price, date=date,
                      commission=commission, stamp_tax=stamp_tax)
        self.trades.append(trade)

    # ---- 每日结算 ----

    def settle(self):
        """结算：T+1模式中将上一日的未交割持仓转为可卖"""
        for code, size in self._pending_settlements:
            pos = self.get_position(code)
            pos.unsettled -= size
            pos.size += size
        self._pending_settlements.clear()

    def reset(self):
        self.cash = self.config.initial_cash
        self.positions.clear()
        self.orders.clear()
        self.trades.clear()
        self._pending_settlements.clear()
