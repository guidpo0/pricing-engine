"""
Cache repository for Pricing Engine using PostgreSQL.
Stores historical data in separate tables instead of JSON.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import psycopg2
from psycopg2 import pool

from app.config import settings

logger = logging.getLogger(__name__)

_connection_pool = None

CACHE_KEYS = {
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


class CacheRepository:
    def __init__(self):
        pass

    def _execute(self, query: str, params: tuple = None, fetch: bool = False):
        """Execute a query and optionally fetch results."""
        conn = _get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params or ())
                if fetch:
                    return cur.fetchall()
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

    def insert_stock_quote(self, ticker: str, unit_price: float, currency: str = "BRL") -> None:
        """Insert a new stock quote into history."""
        now = datetime.now(timezone.utc)
        self._execute(
            '''INSERT INTO stock_quotes_history (ticker, unit_price, currency, recorded_at) 
               VALUES (%s, %s, %s, %s)''',
            (ticker, unit_price, currency, now)
        )

    def insert_stock_quote_us(self, ticker: str, unit_price: float, currency: str = "USD") -> None:
        """Insert a new US stock quote into history."""
        now = datetime.now(timezone.utc)
        self._execute(
            '''INSERT INTO stock_quotes_us_history (ticker, unit_price, currency, recorded_at) 
               VALUES (%s, %s, %s, %s)''',
            (ticker, unit_price, currency, now)
        )

    def insert_crypto_quote(self, slug: str, unit_price: float, currency: str = "USD") -> None:
        """Insert a new crypto quote into history."""
        now = datetime.now(timezone.utc)
        self._execute(
            '''INSERT INTO crypto_quotes_history (slug, unit_price, currency, recorded_at) 
               VALUES (%s, %s, %s, %s)''',
            (slug, unit_price, currency, now)
        )

    def insert_currency_quote(self, currency_pair: str, unit_price: float) -> None:
        """Insert a new currency quote into history."""
        now = datetime.now(timezone.utc)
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

    def get_latest_stock_quote_us(self, ticker: str) -> Optional[dict]:
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

    def get_latest_curves(self) -> Optional[dict]:
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

    def get(self, key: str) -> Optional[dict]:
        """Get latest data for a specific key (legacy compatibility)."""
        if key == "curves":
            return self.get_latest_curves()
        elif key == "inflation":
            return self.get_latest_inflation()
        return None

    def set(self, key: str, value: Any) -> None:
        """Set data for a specific key (legacy compatibility - not used in historical mode)."""
        pass

    def get_all(self) -> dict:
        """Get all latest data (legacy compatibility)."""
        return {
            "curves": self.get_latest_curves(),
            "inflation": self.get_latest_inflation(),
        }

    def get_updated_at(self) -> Optional[str]:
        """Get the updated_at timestamp (from latest curves)."""
        curves = self.get_latest_curves()
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


cache_repository = CacheRepository()