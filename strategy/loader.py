"""自定义策略加载器"""

import importlib.util
import os
import sys

from .base import BaseStrategy
from .builtin import BUILTIN_STRATEGIES


def load_custom_strategies(custom_dir: str | None = None) -> dict[str, type]:
    """从 custom 目录加载用户自定义策略"""
    if custom_dir is None:
        custom_dir = os.path.join(os.path.dirname(__file__), "custom")

    strategies = {}

    if not os.path.isdir(custom_dir):
        return strategies

    for filename in os.listdir(custom_dir):
        if not filename.endswith(".py") or filename.startswith("_"):
            continue

        filepath = os.path.join(custom_dir, filename)
        mod_name = f"custom_strategy_{filename[:-3]}"

        try:
            spec = importlib.util.spec_from_file_location(mod_name, filepath)
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = mod
            spec.loader.exec_module(mod)

            for attr_name in dir(mod):
                attr = getattr(mod, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, BaseStrategy)
                    and attr is not BaseStrategy
                ):
                    key = filename[:-3]
                    strategies[key] = attr
                    print(f"  已加载自定义策略: {key} -> {attr_name}")

        except Exception as e:
            print(f"  加载策略文件 {filename} 失败: {e}")

    return strategies


def get_all_strategies(custom_dir: str | None = None) -> dict[str, type]:
    """获取所有可用策略（内置 + 自定义）"""
    strategies = dict(BUILTIN_STRATEGIES)
    strategies.update(load_custom_strategies(custom_dir))
    return strategies
