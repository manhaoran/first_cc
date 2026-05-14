"""SQLite 数据库管理"""

import sqlite3
from datetime import datetime, timedelta

import pandas as pd


class Database:
    def __init__(self, db_path: str = "data/stock_data.db"):
        import os
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
        self.db_path = db_path
        self._init_tables()

    def _get_conn(self):
        return sqlite3.connect(self.db_path)

    def _init_tables(self):
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS stock_list (
                    code TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL DEFAULT 'stock'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS daily_kline (
                    code TEXT NOT NULL,
                    date TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume REAL NOT NULL DEFAULT 0,
                    amount REAL NOT NULL DEFAULT 0,
                    amplitude REAL DEFAULT 0,
                    pct_change REAL DEFAULT 0,
                    change REAL DEFAULT 0,
                    turnover REAL DEFAULT 0,
                    PRIMARY KEY (code, date)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_daily_kline_code
                ON daily_kline(code)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_daily_kline_date
                ON daily_kline(date)
            """)
            conn.commit()

    # ---- stock_list ----

    def upsert_stock(self, code: str, name: str, typ: str = "stock"):
        with self._get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO stock_list (code, name, type) VALUES (?, ?, ?)",
                (code, name, typ),
            )
            conn.commit()

    def get_stock_list(self, typ: str | None = None) -> pd.DataFrame:
        with self._get_conn() as conn:
            if typ:
                return pd.read_sql_query(
                    "SELECT code, name, type FROM stock_list WHERE type = ?", conn, params=(typ,)
                )
            return pd.read_sql_query("SELECT code, name, type FROM stock_list", conn)

    def get_all_codes(self, typ: str | None = None) -> list[str]:
        df = self.get_stock_list(typ)
        return df["code"].tolist() if not df.empty else []

    # ---- daily_kline ----

    def upsert_daily_kline(self, rows: list[dict]):
        """批量插入或更新日K线数据"""
        if not rows:
            return
        with self._get_conn() as conn:
            conn.executemany(
                """INSERT OR REPLACE INTO daily_kline
                   (code, date, open, high, low, close, volume, amount, amplitude, pct_change, change, turnover)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        r["code"], r["date"],
                        r["open"], r["high"], r["low"], r["close"],
                        r.get("volume", 0), r.get("amount", 0),
                        r.get("amplitude", 0), r.get("pct_change", 0),
                        r.get("change", 0), r.get("turnover", 0),
                    )
                    for r in rows
                ],
            )
            conn.commit()

    def get_kline(self, code: str, start: str | None = None, end: str | None = None) -> pd.DataFrame:
        """获取单只股票的日K线数据，按日期升序"""
        with self._get_conn() as conn:
            sql = "SELECT * FROM daily_kline WHERE code = ?"
            params = [code]
            if start:
                sql += " AND date >= ?"
                params.append(start)
            if end:
                sql += " AND date <= ?"
                params.append(end)
            sql += " ORDER BY date ASC"
            df = pd.read_sql_query(sql, conn, params=params)
            if not df.empty:
                df["date"] = pd.to_datetime(df["date"])
            return df

    def get_latest_date(self, code: str) -> str | None:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT MAX(date) FROM daily_kline WHERE code = ?", (code,)
            ).fetchone()
            return row[0] if row and row[0] else None

    def get_trading_dates(self, codes: list[str] | None = None) -> list[str]:
        """获取所有（或指定股票）的交易日期，去重排序"""
        with self._get_conn() as conn:
            if codes:
                placeholders = ",".join(["?"] * len(codes))
                rows = conn.execute(
                    f"SELECT DISTINCT date FROM daily_kline WHERE code IN ({placeholders}) ORDER BY date ASC",
                    codes,
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT DISTINCT date FROM daily_kline ORDER BY date ASC"
                ).fetchall()
            return [r[0] for r in rows]

    def get_multi_kline(self, codes: list[str], start: str | None = None, end: str | None = None) -> dict[str, pd.DataFrame]:
        """批量获取多只股票的K线数据"""
        result = {}
        for code in codes:
            df = self.get_kline(code, start, end)
            if not df.empty:
                result[code] = df
        return result
