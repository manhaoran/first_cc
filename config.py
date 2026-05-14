"""量化回测系统配置"""

from dataclasses import dataclass, field


@dataclass
class BacktestConfig:
    """回测配置"""
    # 交易模式: T+0 或 T+1
    mode: str = "T+1"

    # 涨跌停限制
    limit_up_no_buy: bool = True   # 涨停不能买入
    limit_down_no_sell: bool = True  # 跌停不能卖出

    # 交易费用
    commission_rate: float = 0.0003   # 佣金费率 (默认万分之三)
    min_commission: float = 5.0       # 最低佣金
    stamp_tax_rate: float = 0.001     # 印花税 (卖出时收取，千分之一)

    # 资金
    initial_cash: float = 100000.0    # 初始资金

    # 数据日期范围 (None 表示使用全部数据)
    start_date: str | None = None
    end_date: str | None = None

    # 数据库路径
    db_path: str = "data/stock_data.db"


@dataclass
class StrategyConfig:
    """策略配置，用于传递参数给策略"""
    name: str = ""
    params: dict = field(default_factory=dict)
