"""
History repository for Pricing Engine using PostgreSQL.
Stores historical data in separate tables.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, date as date_type
from typing import Any, Optional

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

from app.config import settings

logger = logging.getLogger(__name__)

_connection_pool = None

HISTORY_KEYS = {
    "curves": "curves",
    "inflation": "inflation",
    "br_stocks": "br_stocks",
    "us_stocks": "us_stocks",
    "crypto": "crypto",
    "currencies": "currencies",
}

DEFAULT_TTL_HOURS = 24


def _get_connection_pool():
    """Get or create the PostgreSQL connection pool."""
    global _connection_pool
    if _connection_pool is None:
        database_url = settings.database_url
        if not database_url:
            logger.warning("DATABASE_URL not set, cache features disabled")
            return None
        
        if 'sslmode' not in database_url:
            if '?' in database_url:
                database_url = f"{database_url}&sslmode=require"
            else:
                database_url = f"{database_url}?sslmode=require"
        
        try:
            _connection_pool = pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=10,
                dsn=database_url,
            )
        except Exception as e:
            logger.error("Failed to create connection pool: %s", e)
            return None
    return _connection_pool


def _get_connection():
    """Get a connection from the pool."""
    pool_obj = _get_connection_pool()
    if pool_obj is None:
        raise Exception("Database connection not available")
    return pool_obj.getconn()


def _return_connection(conn):
    """Return connection to the pool."""
    pool_obj = _get_connection_pool()
    if pool_obj is not None:
        pool_obj.putconn(conn)


class HistoryRepository:
    def __init__(self):
        pass

    def _execute(self, query: str, params: tuple = None, fetch: bool = False):
        """Execute a query and optionally fetch results."""
        conn = _get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params or ())
                if fetch:
                    result = cur.fetchall()
                    conn.commit()
                    return result
                conn.commit()
        except Exception as e:
            logger.error("Database error: %s", e)
            conn.rollback()
            raise
        finally:
            _return_connection(conn)

    def _execute_one(self, query: str, params: tuple = None):
        """Execute a query and fetch one result."""
        conn = _get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params or ())
                return cur.fetchone()
        except Exception as e:
            logger.error("Database error: %s", e)
            raise
        finally:
            _return_connection(conn)

    def insert_stock_quote(self, ticker: str, unit_price: float, currency: str = "BRL", recorded_at: datetime | None = None) -> None:
        """Insert a new stock quote into history."""
        now = recorded_at or datetime.now(timezone.utc)
        self._execute(
            '''INSERT INTO stock_quotes_history (ticker, unit_price, currency, recorded_at) 
               VALUES (%s, %s, %s, %s)''',
            (ticker, unit_price, currency, now)
        )

    def insert_us_stock_quote(self, ticker: str, unit_price: float, currency: str = "USD", recorded_at: datetime | None = None) -> None:
        """Insert a new US stock quote into history."""
        now = recorded_at or datetime.now(timezone.utc)
        self._execute(
            '''INSERT INTO stock_quotes_us_history (ticker, unit_price, currency, recorded_at) 
               VALUES (%s, %s, %s, %s)''',
            (ticker, unit_price, currency, now)
        )

    def insert_crypto_quote(self, slug: str, unit_price: float, currency: str = "USD", recorded_at: datetime | None = None) -> None:
        """Insert a new crypto quote into history."""
        now = recorded_at or datetime.now(timezone.utc)
        self._execute(
            '''INSERT INTO crypto_quotes_history (slug, unit_price, currency, recorded_at) 
               VALUES (%s, %s, %s, %s)''',
            (slug, unit_price, currency, now)
        )

    def insert_currency_quote(self, currency_pair: str, unit_price: float, recorded_at: datetime | None = None) -> None:
        """Insert a new currency quote into history."""
        now = recorded_at or datetime.now(timezone.utc)
        self._execute(
            '''INSERT INTO currency_quotes_history (currency_pair, unit_price, recorded_at) 
               VALUES (%s, %s, %s)''',
            (currency_pair, unit_price, now)
        )

    def insert_curves(self, pre_curve: dict, ipca_curve: dict, selic_rate: float, lft_vna: float) -> None:
        """Insert curves data into history."""
        now = datetime.now(timezone.utc)
        self._execute(
            '''INSERT INTO curves_history (pre_curve, ipca_curve, selic_rate, lft_vna, recorded_at) 
               VALUES (%s, %s, %s, %s, %s)''',
            (json.dumps(pre_curve), json.dumps(ipca_curve), selic_rate, lft_vna, now)
        )

    def insert_inflation(self, vna: float, ipca_monthly: list) -> None:
        """Insert inflation data into history."""
        now = datetime.now(timezone.utc)
        self._execute(
            '''INSERT INTO inflation_history (vna, ipca_monthly, recorded_at) 
               VALUES (%s, %s, %s)''',
            (vna, json.dumps(ipca_monthly), now)
        )

    def get_latest_stock_quote(self, ticker: str) -> Optional[dict]:
        """Get the latest stock quote."""
        return self._execute_one(
            '''SELECT ticker, unit_price, currency, recorded_at 
               FROM stock_quotes_history 
               WHERE ticker = %s 
               ORDER BY recorded_at DESC 
               LIMIT 1''',
            (ticker,)
        )

    def get_latest_us_stock_quote(self, ticker: str) -> Optional[dict]:
        """Get the latest US stock quote."""
        return self._execute_one(
            '''SELECT ticker, unit_price, currency, recorded_at 
               FROM stock_quotes_us_history 
               WHERE ticker = %s 
               ORDER BY recorded_at DESC 
               LIMIT 1''',
            (ticker,)
        )

    def get_latest_crypto_quote(self, slug: str) -> Optional[dict]:
        """Get the latest crypto quote."""
        return self._execute_one(
            '''SELECT slug, unit_price, currency, recorded_at 
               FROM crypto_quotes_history 
               WHERE slug = %s 
               ORDER BY recorded_at DESC 
               LIMIT 1''',
            (slug,)
        )

    def get_stock_quote_by_date(self, ticker: str, date: str) -> Optional[dict]:
        """Get stock quote for a specific date or the latest before that date."""
        date_obj = datetime.strptime(date, "%Y-%m-%d").date()
        return self._execute_one(
            '''SELECT ticker, unit_price, currency, recorded_at 
               FROM stock_quotes_history 
               WHERE ticker = %s 
                 AND DATE(recorded_at) <= %s 
               ORDER BY recorded_at DESC 
               LIMIT 1''',
            (ticker, date_obj)
        )

    def get_us_stock_quote_by_date(self, ticker: str, date: str) -> Optional[dict]:
        """Get US stock quote for a specific date or the latest before that date."""
        date_obj = datetime.strptime(date, "%Y-%m-%d").date()
        return self._execute_one(
            '''SELECT ticker, unit_price, currency, recorded_at 
               FROM stock_quotes_us_history 
               WHERE ticker = %s 
                 AND DATE(recorded_at) <= %s 
               ORDER BY recorded_at DESC 
               LIMIT 1''',
            (ticker, date_obj)
        )

    def get_crypto_quote_by_date(self, slug: str, date: str) -> Optional[dict]:
        """Get crypto quote for a specific date or the latest before that date."""
        date_obj = datetime.strptime(date, "%Y-%m-%d").date()
        return self._execute_one(
            '''SELECT slug, unit_price, currency, recorded_at 
               FROM crypto_quotes_history 
               WHERE slug = %s 
                 AND DATE(recorded_at) <= %s 
               ORDER BY recorded_at DESC 
               LIMIT 1''',
            (slug, date_obj)
        )

    def get_latest_currency_quote(self, currency_pair: str) -> Optional[dict]:
        """Get the latest currency quote."""
        return self._execute_one(
            '''SELECT currency_pair, unit_price, recorded_at 
               FROM currency_quotes_history 
               WHERE currency_pair = %s 
               ORDER BY recorded_at DESC 
               LIMIT 1''',
            (currency_pair,)
        )

    def get_currency_quote_by_date(self, currency_pair: str, date: str) -> Optional[dict]:
        """Get currency quote for a specific date."""
        date_obj = datetime.strptime(date, "%Y-%m-%d").date()
        return self._execute_one(
            '''SELECT currency_pair, unit_price, recorded_at 
               FROM currency_quotes_history 
               WHERE currency_pair = %s 
                 AND DATE(recorded_at) = %s 
               ORDER BY recorded_at DESC 
               LIMIT 1''',
            (currency_pair, date_obj)
        )

    def get_latest_curve(self) -> Optional[dict]:
        """Get the latest curves data."""
        return self._execute_one(
            '''SELECT pre_curve, ipca_curve, selic_rate, lft_vna, recorded_at 
               FROM curves_history 
               ORDER BY recorded_at DESC 
               LIMIT 1'''
        )

    def get_latest_inflation(self) -> Optional[dict]:
        """Get the latest inflation data."""
        return self._execute_one(
            '''SELECT vna, ipca_monthly, recorded_at 
               FROM inflation_history 
               ORDER BY recorded_at DESC 
               LIMIT 1'''
        )

    def get_currency_history(self, currency_pair: str, days: int = 30) -> list[dict]:
        """Get currency quote history for the last N days."""
        result = self._execute(
            '''SELECT currency_pair, unit_price, recorded_at 
               FROM currency_quotes_history 
               WHERE currency_pair = %s 
               ORDER BY recorded_at DESC 
               LIMIT %s''',
            (currency_pair, days),
            fetch=True
        )
        return result if result else []

    def get(self, key: str) -> Optional[dict]:
        """Get latest data for a specific key."""
        if key == HISTORY_KEYS["curves"]:
            return self.get_latest_curve()
        elif key == HISTORY_KEYS["inflation"]:
            return self.get_latest_inflation()
        return None

    def get_updated_at(self) -> Optional[str]:
        """Get the updated_at timestamp (from latest curves)."""
        curves = self.get_latest_curve()
        if curves and curves.get("recorded_at"):
            return curves["recorded_at"].isoformat()
        return None

    def is_cache_fresh(self, key: str, max_age_hours: int = DEFAULT_TTL_HOURS) -> bool:
        """Check if cache is fresh based on recorded_at."""
        data = self.get(key)
        if not data or not data.get("recorded_at"):
            return False
        try:
            recorded = data["recorded_at"]
            if isinstance(recorded, str):
                recorded = datetime.fromisoformat(recorded.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            age_hours = (now - recorded).total_seconds() / 3600
            return age_hours < max_age_hours
        except Exception:
            return False

    def clear(self) -> None:
        """Clear all historical data (use with caution!)."""
        logger.warning("Clearing all historical data from database")
        self._execute('DELETE FROM stock_quotes_history')
        self._execute('DELETE FROM stock_quotes_us_history')
        self._execute('DELETE FROM crypto_quotes_history')
        self._execute('DELETE FROM currency_quotes_history')
        self._execute('DELETE FROM curves_history')
        self._execute('DELETE FROM inflation_history')
        self._execute('DELETE FROM selic_daily_factors')

    def clear_stock_quotes(self) -> int:
        """Clear only the stock_quotes_history table. Returns count of deleted rows."""
        logger.warning("Clearing stock_quotes_history table")
        result = self._execute('DELETE FROM stock_quotes_history RETURNING id', fetch=True)
        return len(result)

    def clear_us_stock_quotes(self) -> int:
        """Clear only the stock_quotes_us_history table. Returns count of deleted rows."""
        logger.warning("Clearing stock_quotes_us_history table")
        result = self._execute('DELETE FROM stock_quotes_us_history RETURNING id', fetch=True)
        return len(result)

    def clear_currency_quotes(self) -> int:
        """Clear only the currency_quotes_history table. Returns count of deleted rows."""
        logger.warning("Clearing currency_quotes_history table")
        result = self._execute('DELETE FROM currency_quotes_history RETURNING id', fetch=True)
        return len(result)

    def clear_quotes_tables(self) -> dict[str, int]:
        """Clear stock_quotes_history, stock_quotes_us_history, and currency_quotes_history."""
        return {
            "stock_quotes_history": self.clear_stock_quotes(),
            "stock_quotes_us_history": self.clear_us_stock_quotes(),
            "currency_quotes_history": self.clear_currency_quotes(),
        }

    def get_latest_stock_quote_date(self, ticker: str) -> date_type | None:
        """Get the latest recorded_at date for a stock ticker."""
        result = self._execute_one(
            '''SELECT MAX(DATE(recorded_at)) as max_date
               FROM stock_quotes_history
               WHERE ticker = %s''',
            (ticker,)
        )
        return result["max_date"] if result and result["max_date"] else None

    def get_latest_us_stock_quote_date(self, ticker: str) -> date_type | None:
        """Get the latest recorded_at date for a US stock ticker."""
        result = self._execute_one(
            '''SELECT MAX(DATE(recorded_at)) as max_date
               FROM stock_quotes_us_history
               WHERE ticker = %s''',
            (ticker,)
        )
        return result["max_date"] if result and result["max_date"] else None

    def get_latest_currency_quote_date(self, currency_pair: str) -> date_type | None:
        """Get the latest recorded_at date for a currency pair."""
        result = self._execute_one(
            '''SELECT MAX(DATE(recorded_at)) as max_date
               FROM currency_quotes_history
               WHERE currency_pair = %s''',
            (currency_pair,)
        )
        return result["max_date"] if result and result["max_date"] else None

    def deduplicate_all_tables(self) -> dict[str, int]:
        """
        Remove registros duplicados de todas as tabelas de histórico.

        Regras:
        - Tabelas com (ativo, data): mantém o registro com recorded_at mais recente de cada dia
          (stock_quotes_history, stock_quotes_us_history, crypto_quotes_history, currency_quotes_history)
        - Tabelas sem ativo: mantém o último registro de cada dia
          (curves_history, inflation_history)
        - selic_daily_factors: não precisa (PK em factor_date)
        """
        results: dict[str, int] = {}

        tables_with_asset = [
            ("stock_quotes_history", "ticker"),
            ("stock_quotes_us_history", "ticker"),
            ("crypto_quotes_history", "slug"),
            ("currency_quotes_history", "currency_pair"),
        ]
        for table, asset_col in tables_with_asset:
            sql = f"""DELETE FROM {table} WHERE id NOT IN (
                SELECT DISTINCT ON ({asset_col}, DATE(recorded_at)) id
                FROM {table}
                ORDER BY {asset_col}, DATE(recorded_at), recorded_at DESC
            )"""
            self._execute(sql)
            results[table] = self._execute_one(
                f"SELECT COUNT(*) as cnt FROM {table}"
            )["cnt"]

        tables_by_day = ["curves_history", "inflation_history"]
        for table in tables_by_day:
            sql = f"""DELETE FROM {table} WHERE id NOT IN (
                SELECT DISTINCT ON (DATE(recorded_at)) id
                FROM {table}
                ORDER BY DATE(recorded_at), recorded_at DESC
            )"""
            self._execute(sql)
            results[table] = self._execute_one(
                f"SELECT COUNT(*) as cnt FROM {table}"
            )["cnt"]

        logger.info("Deduplication complete: %s", results)
        return results


history_repository = HistoryRepository()