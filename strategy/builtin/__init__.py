from .ma_cross import MACrossStrategy
from .macd import MACDStrategy
from .rsi import RSIStrategy
from .bollinger import BollingerStrategy
from .dual_thrust import DualThrustStrategy

BUILTIN_STRATEGIES = {
    "ma_cross": MACrossStrategy,
    "macd": MACDStrategy,
    "rsi": RSIStrategy,
    "bollinger": BollingerStrategy,
    "dual_thrust": DualThrustStrategy,
}
