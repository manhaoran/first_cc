"""通过 akshare 获取股票和ETF历史数据"""

from datetime import datetime, timedelta

import pandas as pd

from .database import Database


class DataFetcher:
    def __init__(self, db: Database):
        self.db = db

    # ========== 股票列表 ==========

    def fetch_stock_list(self) -> pd.DataFrame:
        """获取A股股票列表"""
        import akshare as ak
        df = ak.stock_zh_a_spot_em()
        df = df[["代码", "名称"]].rename(columns={"代码": "code", "名称": "name"})
        return df

    def sync_stock_list(self):
        """同步股票列表到数据库"""
        print("正在获取A股股票列表...")
        df = self.fetch_stock_list()
        for _, row in df.iterrows():
            self.db.upsert_stock(row["code"], row["name"], "stock")
        print(f"已同步 {len(df)} 只股票")

    # ========== ETF 列表 ==========

    def fetch_etf_list(self) -> pd.DataFrame:
        """获取ETF列表"""
        import akshare as ak
        df = ak.fund_etf_spot_em()
        df = df[["代码", "名称"]].rename(columns={"代码": "code", "名称": "name"})
        return df

    def sync_etf_list(self):
        """同步ETF列表到数据库"""
        print("正在获取ETF列表...")
        df = self.fetch_etf_list()
        for _, row in df.iterrows():
            self.db.upsert_stock(row["code"], row["name"], "etf")
        print(f"已同步 {len(df)} 只ETF")

    # ========== K线数据 ==========

    def fetch_stock_kline(self, code: str, start: str = "20000101", end: str | None = None) -> pd.DataFrame:
        """获取单只股票的日K线数据（多源fallback）"""
        import akshare as ak
        if end is None:
            end = datetime.now().strftime("%Y%m%d")

        # 尝试东方财富源
        try:
            df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start, end_date=end, adjust="qfq")
            if not df.empty:
                df = df.rename(columns={
                    "日期": "date", "开盘": "open", "最高": "high", "最低": "low",
                    "收盘": "close", "成交量": "volume", "成交额": "amount",
                    "振幅": "amplitude", "涨跌幅": "pct_change", "涨跌额": "change", "换手率": "turnover",
                })
                return self._normalize_kline(df, code)
        except Exception:
            pass

        # 尝试新浪源
        try:
            prefix = "sh" if code.startswith(("6", "9")) else "sz"
            df = ak.stock_zh_a_daily(symbol=f"{prefix}{code}", start_date=start, end_date=end, adjust="qfq")
            if not df.empty:
                df = df.rename(columns={
                    "date": "date", "open": "open", "high": "high", "low": "low",
                    "close": "close", "amount": "amount", "turnover": "turnover",
                })
                return self._normalize_kline(df, code)
        except Exception:
            pass

        # 尝试腾讯源
        try:
            prefix = "sz" if code.startswith(("0", "3")) else "sh"
            df = ak.stock_zh_a_hist_tx(symbol=f"{prefix}{code}", start_date=start, end_date=end)
            if not df.empty:
                df = df.rename(columns={
                    "date": "date", "open": "open", "high": "high", "low": "low",
                    "close": "close", "amount": "amount",
                })
                return self._normalize_kline(df, code)
        except Exception:
            pass

        print(f"获取 {code} K线失败: 所有数据源均不可用")
        return pd.DataFrame()

    @staticmethod
    def _normalize_kline(df: pd.DataFrame, code: str) -> pd.DataFrame:
        """统一K线数据格式，补全缺失列"""
        df["code"] = code
        df["date"] = df["date"].astype(str)

        for col in ["volume", "amplitude", "pct_change", "change", "turnover"]:
            if col not in df.columns:
                df[col] = 0.0

        # 尝试从amount反推volume
        if (df["volume"] == 0).all() and "amount" in df.columns:
            avg_price = (df["high"] + df["low"] + df["close"]) / 3
            df["volume"] = (df["amount"] / avg_price.replace(0, float("nan"))).fillna(0).round(0)

        # 计算涨跌幅
        if (df["pct_change"] == 0).all():
            df["pct_change"] = df["close"].pct_change().fillna(0) * 100

        return df[["code", "date", "open", "high", "low", "close", "volume", "amount",
                    "amplitude", "pct_change", "change", "turnover"]]

    def fetch_etf_kline(self, code: str, start: str = "20000101", end: str | None = None) -> pd.DataFrame:
        """获取单只ETF的日K线数据"""
        import akshare as ak
        if end is None:
            end = datetime.now().strftime("%Y%m%d")
        try:
            df = ak.fund_etf_hist_em(symbol=code, period="daily", start_date=start, end_date=end, adjust="qfq")
        except Exception as e:
            print(f"获取 {code} ETF K线失败: {e}")
            return pd.DataFrame()

        if df.empty:
            return df

        df = df.rename(columns={
            "日期": "date", "开盘": "open", "最高": "high", "最低": "low",
            "收盘": "close", "成交量": "volume", "成交额": "amount",
            "振幅": "amplitude", "涨跌幅": "pct_change", "涨跌额": "change", "换手率": "turnover",
        })
        df["code"] = code
        df["date"] = df["date"].astype(str)
        return df[["code", "date", "open", "high", "low", "close", "volume", "amount",
                    "amplitude", "pct_change", "change", "turnover"]]

    def _to_dicts(self, df: pd.DataFrame) -> list[dict]:
        return df.to_dict(orient="records")

    def update_kline(self, code: str, typ: str = "stock"):
        """增量更新单只标的的K线数据"""
        latest = self.db.get_latest_date(code)
        if latest:
            start = (datetime.strptime(latest, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y%m%d")
        else:
            start = "20000101"

        fetch_func = self.fetch_stock_kline if typ == "stock" else self.fetch_etf_kline
        df = fetch_func(code, start=start)
        if df.empty:
            return 0

        rows = self._to_dicts(df)
        self.db.upsert_daily_kline(rows)
        return len(rows)

    def update_all_kline(self, typ: str | None = None):
        """批量更新所有标的的K线数据"""
        codes = self.db.get_all_codes(typ)
        total = 0
        for i, code in enumerate(codes):
            stock_typ = "etf" if code.startswith("5") else "stock"
            n = self.update_kline(code, stock_typ)
            if n > 0:
                total += n
            if (i + 1) % 50 == 0:
                print(f"  进度: {i + 1}/{len(codes)}")
        print(f"K线更新完成，共新增 {total} 条记录")

    def init_database(self):
        """首次初始化：同步列表 + 下载全部历史数据"""
        self.sync_stock_list()
        self.sync_etf_list()
        self.update_all_kline()
