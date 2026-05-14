#!/usr/bin/env python
"""量化策略收益回测系统 - 入口"""

import argparse
import sys

from config import BacktestConfig
from data import Database, DataFetcher
from engine import BacktestEngine
from strategy.loader import get_all_strategies


def cmd_init_db(args):
    """初始化数据库：下载股票/ETF列表和历史K线数据"""
    db = Database(args.db)
    fetcher = DataFetcher(db)
    fetcher.init_database()
    print("数据库初始化完成。")


def cmd_update_db(args):
    """增量更新K线数据"""
    db = Database(args.db)
    fetcher = DataFetcher(db)

    typ = args.type  # "stock", "etf", or None for both
    if typ:
        fetcher.update_all_kline(typ)
    else:
        fetcher.sync_stock_list()
        fetcher.sync_etf_list()
        fetcher.update_all_kline()
    print("数据更新完成。")


def cmd_list_strategies(args):
    """列出所有可用策略"""
    strategies = get_all_strategies()
    print("\n可用策略:")
    print("-" * 50)
    for name, cls in strategies.items():
        doc = cls.__doc__ or ""
        doc_line = doc.strip().split("\n")[0] if doc.strip() else "(无描述)"
        print(f"  {name:20s} - {doc_line}")
    print("-" * 50)


def cmd_list_stocks(args):
    """列出数据库中的标的"""
    db = Database(args.db)
    df = db.get_stock_list(args.type)
    if df.empty:
        print("数据库中无数据，请先运行 init-db")
        return
    print(f"\n共 {len(df)} 只标的:")
    for _, row in df.iterrows():
        print(f"  {row['code']}  {row['name']}  [{row['type']}]")


def cmd_run(args):
    """运行回测"""
    db = Database(args.db)

    # 获取策略
    strategies = get_all_strategies()
    if args.strategy not in strategies:
        print(f"未知策略: {args.strategy}")
        print(f"可用策略: {', '.join(strategies.keys())}")
        sys.exit(1)

    strategy_cls = strategies[args.strategy]

    # 解析参数
    params = {}
    if args.params:
        for p in args.params.split(","):
            k, v = p.split("=")
            try:
                v = float(v)
            except ValueError:
                pass
            params[k] = v

    # 获取标的列表
    if args.codes:
        codes = args.codes.split(",")
    else:
        codes = db.get_all_codes(args.type)

    if not codes:
        print("无可用标的，请先运行 init-db")
        sys.exit(1)

    print(f"回测标的: {len(codes)} 只")
    if len(codes) > 50:
        print("标的过多，建议使用 --codes 指定具体标的")
        sys.exit(1)

    # 配置
    config = BacktestConfig(
        mode=args.mode,
        limit_up_no_buy=not args.no_limit_check,
        limit_down_no_sell=not args.no_limit_check,
        commission_rate=args.commission / 10000,  # 万X 转为小数
        min_commission=args.min_commission,
        stamp_tax_rate=args.stamp_tax / 1000 if args.stamp_tax > 0 else 0,
        initial_cash=args.cash,
        start_date=args.start,
        end_date=args.end,
        db_path=args.db,
    )

    # 引擎
    engine = BacktestEngine(config, db)
    engine.load_data(codes, start=args.start, end=args.end)

    if not engine.dates:
        print("加载数据为空，请先运行 update-db")
        sys.exit(1)

    # 策略实例
    strategy = strategy_cls(params)
    print(f"\n策略: {args.strategy}")
    print(f"参数: {params}")
    print(f"模式: {config.mode}  |  佣金: 万{args.commission}  |  印花税: {args.stamp_tax}/1000  |  初始资金: {config.initial_cash:.0f}")
    print(f"日期范围: {engine.dates[0]} ~ {engine.dates[-1]}")
    print()

    # 运行
    results = engine.run(strategy)

    # 输出
    engine.print_report()

    # 保存结果
    if args.output:
        trades_df = engine.get_trades_df()
        equity_df = engine.get_equity_df()
        trades_df.to_csv(f"{args.output}_trades.csv", index=False)
        equity_df.to_csv(f"{args.output}_equity.csv", index=False)
        print(f"\n交易记录已保存至: {args.output}_trades.csv")
        print(f"权益曲线已保存至: {args.output}_equity.csv")


def main():
    parser = argparse.ArgumentParser(description="量化策略收益回测系统")
    sub = parser.add_subparsers(dest="command", help="子命令")

    # init-db
    p_init = sub.add_parser("init-db", help="初始化数据库（下载股票列表+历史数据）")
    p_init.add_argument("--db", default="data/stock_data.db", help="数据库路径")

    # update-db
    p_update = sub.add_parser("update-db", help="增量更新数据库")
    p_update.add_argument("--db", default="data/stock_data.db", help="数据库路径")
    p_update.add_argument("--type", choices=["stock", "etf"], default=None, help="更新类型")

    # list-strategies
    sub.add_parser("list-strategies", help="列出所有可用策略")

    # list-stocks
    p_list = sub.add_parser("list-stocks", help="列出数据库中的标的")
    p_list.add_argument("--db", default="data/stock_data.db", help="数据库路径")
    p_list.add_argument("--type", choices=["stock", "etf"], default=None, help="类型")

    # run
    p_run = sub.add_parser("run", help="运行回测")
    p_run.add_argument("--strategy", "-s", required=True, help="策略名称")
    p_run.add_argument("--params", "-p", default="", help='策略参数, 格式: "fast=5,slow=20"')
    p_run.add_argument("--codes", "-c", default="", help="标的代码, 逗号分隔 (默认全部)")
    p_run.add_argument("--type", choices=["stock", "etf"], default=None, help="标的类型")
    p_run.add_argument("--mode", choices=["T+0", "T+1"], default="T+1", help="交易模式")
    p_run.add_argument("--commission", type=float, default=3.0, help="佣金费率 (万分之X, 默认万分之三)")
    p_run.add_argument("--min-commission", type=float, default=5.0, help="最低佣金")
    p_run.add_argument("--stamp-tax", type=float, default=1.0, help="印花税 (千分之X, 默认千分之一)")
    p_run.add_argument("--no-limit-check", action="store_true", help="禁用涨跌停限制")
    p_run.add_argument("--cash", type=float, default=100000.0, help="初始资金")
    p_run.add_argument("--start", default=None, help="开始日期 YYYY-MM-DD")
    p_run.add_argument("--end", default=None, help="结束日期 YYYY-MM-DD")
    p_run.add_argument("--output", "-o", default="", help="输出文件前缀")
    p_run.add_argument("--db", default="data/stock_data.db", help="数据库路径")

    args = parser.parse_args()

    if args.command == "init-db":
        cmd_init_db(args)
    elif args.command == "update-db":
        cmd_update_db(args)
    elif args.command == "list-strategies":
        cmd_list_strategies(args)
    elif args.command == "list-stocks":
        cmd_list_stocks(args)
    elif args.command == "run":
        cmd_run(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
