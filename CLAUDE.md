# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

量化策略收益回测系统。从 akshare 获取 A 股和 ETF 历史数据存入本地 SQLite，支持 T+0/T+1、涨跌停限制、佣金印花税配置，内置 5 个策略并支持用户自定义 Python 策略。

## 常用命令

```bash
# 初始化数据库（首次使用，下载全部A股+ETF历史K线，耗时长）
python main.py init-db

# 增量更新数据
python main.py update-db
python main.py update-db --type etf    # 只更新ETF

# 列出策略和标的
python main.py list-strategies
python main.py list-stocks

# 运行回测
python main.py run -s ma_cross -c 000001
python main.py run -s ma_cross -c 000001,600519 -p "fast=10,slow=30"
python main.py run -s macd -c 510050 --mode T+0 --stamp-tax 0
python main.py run -s rsi -c 000001 --commission 2.5 --cash 200000 -o result

# 语法检查（无正式测试套件）
python -m py_compile main.py
python -m py_compile strategy/base.py
```

## 架构

```
main.py (CLI: argparse, 5个子命令)
  ├── config.py — BacktestConfig 数据类
  ├── data/
  │   ├── database.py — SQLite CRUD (stock_list + daily_kline 表)
  │   └── fetcher.py — akshare 封装 (ak.stock_zh_a_hist / ak.fund_etf_hist_em)
  ├── engine/
  │   ├── broker.py — 资金/持仓/费用/T+1交割结算
  │   └── backtest.py — 逐bar回测循环 + 绩效报告
  └── strategy/
      ├── base.py — 策略基类 (数据访问/指标/下单便捷方法)
      ├── loader.py — importlib 加载 custom/ 下的策略类
      ├── builtin/ — 5个内置策略
      └── custom/ — 用户策略目录 (自动扫描)
```

**数据流**: `DataFetcher` → `Database` (SQLite) → `BacktestEngine.load_data()` → `Broker` + `Strategy.next(i)` → 绩效报告

**关键约定**:
- 策略类继承 `BaseStrategy`，实现 `init()` 和 `next(i)`
- `Broker.buy/sell` 以当日收盘价成交，股数自动取整到 100 股
- T+1 模式：买入进入 `unsettled` 仓，次日 `settle()` 后转为可卖
- 涨停判断阈值 `pct_change >= 9.8`，跌停 `<= -9.8`
- 用户策略文件放在 `strategy/custom/*.py`，类名任意，只需继承 `BaseStrategy`
