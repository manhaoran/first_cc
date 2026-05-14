"""回测引擎"""

import time
from datetime import datetime

import numpy as np
import pandas as pd

from config import BacktestConfig
from data.database import Database
from .broker import Broker


class BacktestEngine:
    def __init__(self, config: BacktestConfig, db: Database):
        self.config = config
        self.db = db
        self.broker = Broker(config)
        self.strategy = None

        # 回测数据
        self.data: dict[str, pd.DataFrame] = {}       # code -> DataFrame
        self.dates: list[str] = []
        self.codes: list[str] = []

        # 结果
        self.equity_curve: list[dict] = []
        self._final_results: dict | None = None

    def load_data(self, codes: list[str], start: str | None = None, end: str | None = None):
        """加载回测数据"""
        self.codes = codes
        self.data = self.db.get_multi_kline(codes, start, end)

        # 找出所有标的共有的交易日期
        all_dates = set()
        for df in self.data.values():
            all_dates.update(df["date"].dt.strftime("%Y-%m-%d").tolist())
        self.dates = sorted(all_dates)

        # 按配置过滤日期
        if self.config.start_date:
            self.dates = [d for d in self.dates if d >= self.config.start_date]
        if self.config.end_date:
            self.dates = [d for d in self.dates if d <= self.config.end_date]

        print(f"加载 {len(self.codes)} 只标的, {len(self.dates)} 个交易日")

    def _get_bar(self, code: str, date: str) -> dict | None:
        """获取某只标的在某日的数据"""
        df = self.data.get(code)
        if df is None:
            return None
        rows = df[df["date"] == date]
        if rows.empty:
            return None
        return rows.iloc[0].to_dict()

    def _get_prices(self, date: str) -> dict[str, float]:
        """获取当日所有标的的收盘价"""
        prices = {}
        for code in self.codes:
            bar = self._get_bar(code, date)
            if bar is not None and not (np.isnan(bar["close"]) or bar["close"] is None):
                prices[code] = float(bar["close"])
        return prices

    def run(self, strategy):
        """运行回测"""
        self.strategy = strategy
        self.broker.reset()
        self.equity_curve = []

        strategy._engine = self
        strategy._broker = self.broker
        strategy._data = self.data
        strategy._dates = self.dates
        strategy._codes = self.codes

        strategy.init()

        total_dates = len(self.dates)
        start_time = time.time()

        for i, date in enumerate(self.dates):
            # 结算 T+1 持仓
            self.broker.settle()

            strategy._current_idx = i
            strategy._current_date = date

            # 调用策略
            strategy.next(i)

            # 记录权益曲线
            prices = self._get_prices(date)
            equity = self.broker.get_equity(prices)
            self.equity_curve.append({
                "date": date,
                "equity": equity,
                "cash": self.broker.cash,
            })

        elapsed = time.time() - start_time
        print(f"回测完成，耗时 {elapsed:.2f}s")

        return self._generate_results()

    def _generate_results(self) -> dict:
        """生成回测结果报告"""
        if not self.equity_curve:
            return {}

        equity_df = pd.DataFrame(self.equity_curve)
        equity_df["date"] = pd.to_datetime(equity_df["date"])
        equity_df.set_index("date", inplace=True)

        initial = self.config.initial_cash
        final = equity_df["equity"].iloc[-1]

        # 日收益率
        equity_df["return"] = equity_df["equity"].pct_change()

        # 累计收益率
        total_return = (final - initial) / initial

        # 年化收益率
        days = len(equity_df)
        years = days / 252
        annual_return = (final / initial) ** (1 / years) - 1 if years > 0 else 0

        # 最大回撤
        cummax = equity_df["equity"].cummax()
        drawdown = (equity_df["equity"] - cummax) / cummax
        max_drawdown = drawdown.min()

        # 夏普比率
        daily_rf = 0.02 / 252  # 假设无风险利率2%
        excess = equity_df["return"].dropna() - daily_rf
        sharpe = np.sqrt(252) * excess.mean() / excess.std() if excess.std() > 0 else 0

        # 胜率
        trades = self.broker.trades
        sell_trades = [t for t in trades if t.action == "sell"]
        buy_trades = [t for t in trades if t.action == "buy"]

        win_count = 0
        total_trades = 0
        # 按买卖配对计算胜率
        paired = self._pair_trades(trades)
        win_count = sum(1 for p in paired if p["pnl"] > 0)
        total_trades = len(paired)
        win_rate = win_count / total_trades if total_trades > 0 else 0

        # 总费用
        total_commission = sum(t.commission for t in trades)
        total_stamp_tax = sum(t.stamp_tax for t in trades)
        total_fees = total_commission + total_stamp_tax

        self._final_results = {
            "initial_cash": initial,
            "final_equity": round(final, 2),
            "total_return": round(total_return * 100, 2),
            "annual_return": round(annual_return * 100, 2),
            "max_drawdown": round(max_drawdown * 100, 2),
            "sharpe_ratio": round(sharpe, 2),
            "total_trades": total_trades,
            "win_rate": round(win_rate * 100, 2),
            "total_commission": round(total_commission, 2),
            "total_stamp_tax": round(total_stamp_tax, 2),
            "total_fees": round(total_fees, 2),
            "trade_count_buy": len(buy_trades),
            "trade_count_sell": len(sell_trades),
        }
        return self._final_results

    def _pair_trades(self, trades: list) -> list[dict]:
        """将买卖配对，计算每笔交易的盈亏"""
        paired = []
        holdings: dict[str, list] = {}  # code -> [(size, cost)]

        for t in trades:
            if t.action == "buy":
                if t.code not in holdings:
                    holdings[t.code] = []
                holdings[t.code].append((t.size, t.price, t.commission))
            else:
                if t.code not in holdings:
                    continue
                remaining = t.size
                sell_amount = 0
                buy_amount = 0
                while remaining > 0 and holdings[t.code]:
                    h_size, h_price, h_comm = holdings[t.code][0]
                    match_size = min(remaining, h_size)
                    buy_cost = match_size * h_price + h_comm * (match_size / h_size)
                    sell_rev = match_size * t.price - t.commission * (match_size / t.size) - t.stamp_tax * (match_size / t.size)
                    pnl = sell_rev - buy_cost
                    paired.append({
                        "code": t.code,
                        "buy_date": "",
                        "sell_date": t.date,
                        "size": match_size,
                        "buy_price": h_price,
                        "sell_price": t.price,
                        "pnl": round(pnl, 2),
                        "pnl_pct": round((t.price - h_price) / h_price * 100, 2),
                    })
                    buy_amount += buy_cost
                    sell_amount += sell_rev
                    remaining -= match_size
                    if match_size >= h_size:
                        holdings[t.code].pop(0)
                    else:
                        holdings[t.code][0] = (h_size - match_size, h_price, h_comm * (h_size - match_size) / h_size)

        return paired

    def get_trades_df(self) -> pd.DataFrame:
        trades = self.broker.trades
        if not trades:
            return pd.DataFrame()
        return pd.DataFrame([{
            "date": t.date, "code": t.code, "action": t.action,
            "size": t.size, "price": t.price,
            "commission": t.commission, "stamp_tax": t.stamp_tax,
        } for t in trades])

    def get_equity_df(self) -> pd.DataFrame:
        if not self.equity_curve:
            return pd.DataFrame()
        return pd.DataFrame(self.equity_curve)

    def print_report(self):
        if not self._final_results:
            return
        r = self._final_results
        print("\n" + "=" * 50)
        print("  回测结果报告")
        print("=" * 50)
        print(f"  初始资金:       {r['initial_cash']:>12.2f}")
        print(f"  最终权益:       {r['final_equity']:>12.2f}")
        print(f"  累计收益率:     {r['total_return']:>11.2f}%")
        print(f"  年化收益率:     {r['annual_return']:>11.2f}%")
        print(f"  最大回撤:       {r['max_drawdown']:>11.2f}%")
        print(f"  夏普比率:       {r['sharpe_ratio']:>11.2f}")
        print(f"  交易次数:       {r['total_trades']:>12}")
        print(f"  胜率:           {r['win_rate']:>11.2f}%")
        print(f"  总佣金:         {r['total_commission']:>12.2f}")
        print(f"  总印花税:       {r['total_stamp_tax']:>12.2f}")
        print(f"  总费用:         {r['total_fees']:>12.2f}")
        print("=" * 50)
