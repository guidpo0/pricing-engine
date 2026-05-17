"""
Database utilities for Pricing Engine using PostgreSQL.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, date as date_type
from contextlib import contextmanager

import psycopg2
from psycopg2 import pool

from app.config import settings

logger = logging.getLogger(__name__)

_connection_pool = None


def _get_connection_pool():
    """Get or create the PostgreSQL connection pool."""
    global _connection_pool
    if _connection_pool is None:
        database_url = settings.database_url
        if not database_url:
            logger.warning("DATABASE_URL not set, database features disabled")
            return None
        
        # Add sslmode if not present
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
            logger.info("Database connection pool created successfully")
        except Exception as e:
            logger.error("Failed to create database connection pool: %s", e)
            return None
    return _connection_pool


@contextmanager
def get_connection():
    """Get a connection from the pool."""
    pool_obj = _get_connection_pool()
    if pool_obj is None:
        raise Exception("Database connection not available - DATABASE_URL not configured")
    conn = pool_obj.getconn()
    try:
        yield conn
    finally:
        pool_obj.putconn(conn)


def init_db() -> None:
    """Initialize the database with the required tables."""
    try:
        pool_obj = _get_connection_pool()
        if pool_obj is None:
            logger.warning("Database not available, skipping initialization")
            return
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS tracked_tickers (
                        ticker VARCHAR(20) PRIMARY KEY,
                        added_at TIMESTAMP DEFAULT NOW()
                    )
                ''')
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS tracked_tickers_us (
                        ticker VARCHAR(20) PRIMARY KEY,
                        added_at TIMESTAMP DEFAULT NOW()
                    )
                ''')
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS tracked_crypto_slugs (
                        slug VARCHAR(50) PRIMARY KEY,
                        added_at TIMESTAMP DEFAULT NOW()
                    )
                ''')
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS tracked_currencies (
                        currency_pair VARCHAR(20) PRIMARY KEY,
                        added_at TIMESTAMP DEFAULT NOW()
                    )
                ''')
                conn.commit()
                logger.info("Database initialized successfully")
    except Exception as e:
        logger.error("Failed to initialize database: %s", e)
        raise


def add_ticker(ticker: str) -> None:
    """Add a new ticker to be tracked by the background job."""
    ticker = ticker.upper()
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    'INSERT INTO tracked_tickers (ticker, added_at) VALUES (%s, %s) ON CONFLICT (ticker) DO NOTHING',
                    (ticker, datetime.now(timezone.utc))
                )
                conn.commit()
    except Exception as e:
        logger.error("Failed to add ticker %s to database: %s", ticker, e)


def get_all_tickers() -> list[str]:
    """Retrieve all tracked tickers from the database."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT ticker FROM tracked_tickers ORDER BY ticker ASC')
                return [row[0] for row in cur.fetchall()]
    except Exception as e:
        logger.error("Failed to retrieve tickers from database: %s", e)
        return []


def get_all_tickers_with_dates() -> list[tuple[str, date_type]]:
    """Retrieve all tracked tickers with their added_at dates."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT ticker, added_at FROM tracked_tickers ORDER BY ticker ASC')
                return [(row[0], row[1].date()) for row in cur.fetchall()]
    except Exception as e:
        logger.error("Failed to retrieve tickers with dates from database: %s", e)
        return []


def add_ticker_us(ticker: str) -> None:
    """Add a new US ticker to be tracked by the background job."""
    ticker = ticker.upper()
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    'INSERT INTO tracked_tickers_us (ticker, added_at) VALUES (%s, %s) ON CONFLICT (ticker) DO NOTHING',
                    (ticker, datetime.now(timezone.utc))
                )
                conn.commit()
    except Exception as e:
        logger.error("Failed to add US ticker %s to database: %s", ticker, e)


def get_all_tickers_us() -> list[str]:
    """Retrieve all tracked US tickers from the database."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT ticker FROM tracked_tickers_us ORDER BY ticker ASC')
                return [row[0] for row in cur.fetchall()]
    except Exception as e:
        logger.error("Failed to retrieve US tickers from database: %s", e)
        return []


def get_all_tickers_us_with_dates() -> list[tuple[str, date_type]]:
    """Retrieve all tracked US tickers with their added_at dates."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT ticker, added_at FROM tracked_tickers_us ORDER BY ticker ASC')
                return [(row[0], row[1].date()) for row in cur.fetchall()]
    except Exception as e:
        logger.error("Failed to retrieve US tickers with dates from database: %s", e)
        return []


def add_crypto_slug(slug: str) -> None:
    """Add a new crypto slug to be tracked by the background job."""
    slug = slug.lower()
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    'INSERT INTO tracked_crypto_slugs (slug, added_at) VALUES (%s, %s) ON CONFLICT (slug) DO NOTHING',
                    (slug, datetime.now(timezone.utc))
                )
                conn.commit()
    except Exception as e:
        logger.error("Failed to add crypto slug %s to database: %s", slug, e)


def get_all_crypto_slugs() -> list[str]:
    """Retrieve all tracked crypto slugs from the database."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT slug FROM tracked_crypto_slugs ORDER BY slug ASC')
                return [row[0] for row in cur.fetchall()]
    except Exception as e:
        logger.error("Failed to retrieve crypto slugs from database: %s", e)
        return []


def add_currency_pair(pair: str) -> None:
    """Add a new currency pair to be tracked by the background job. (e.g. USD-BRL)"""
    pair = pair.upper()
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    'INSERT INTO tracked_currencies (currency_pair, added_at) VALUES (%s, %s) ON CONFLICT (currency_pair) DO NOTHING',
                    (pair, datetime.now(timezone.utc))
                )
                conn.commit()
    except Exception as e:
        logger.error("Failed to add currency pair %s to database: %s", pair, e)


def get_all_currency_pairs() -> list[str]:
    """Retrieve all tracked currency pairs from the database."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT currency_pair FROM tracked_currencies ORDER BY currency_pair ASC')
                return [row[0] for row in cur.fetchall()]
    except Exception as e:
        logger.error("Failed to retrieve currency pairs from database: %s", e)
        return []


def get_all_currency_pairs_with_dates() -> list[tuple[str, date_type]]:
    """Retrieve all tracked currency pairs with their added_at dates."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT currency_pair, added_at FROM tracked_currencies ORDER BY currency_pair ASC')
                return [(row[0], row[1].date()) for row in cur.fetchall()]
    except Exception as e:
        logger.error("Failed to retrieve currency pairs with dates from database: %s", e)
        return []


init_db()