import sqlite3
from pathlib import Path
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

DB_PATH = Path("tickers.db")

def _get_connection() -> sqlite3.Connection:
    """Helper to get a database connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> None:
    """Initialize the SQLite database with the required tables."""
    try:
        with _get_connection() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS tracked_tickers (
                    ticker TEXT PRIMARY KEY,
                    added_at TEXT NOT NULL
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS tracked_tickers_us (
                    ticker TEXT PRIMARY KEY,
                    added_at TEXT NOT NULL
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS tracked_crypto_slugs (
                    slug TEXT PRIMARY KEY,
                    added_at TEXT NOT NULL
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS tracked_currencies (
                    currency_pair TEXT PRIMARY KEY,
                    added_at TEXT NOT NULL
                )
            ''')
            conn.commit()
    except sqlite3.Error as e:
        logger.error("Failed to initialize database: %s", e)

def add_ticker(ticker: str) -> None:
    """Add a new ticker to be tracked by the background job."""
    ticker = ticker.upper()
    now = datetime.now(timezone.utc).isoformat()
    try:
        with _get_connection() as conn:
            conn.execute(
                'INSERT OR IGNORE INTO tracked_tickers (ticker, added_at) VALUES (?, ?)',
                (ticker, now)
            )
            conn.commit()
    except sqlite3.Error as e:
        logger.error("Failed to add ticker %s to database: %s", ticker, e)

def get_all_tickers() -> list[str]:
    """Retrieve all tracked tickers from the database."""
    try:
        with _get_connection() as conn:
            cursor = conn.execute('SELECT ticker FROM tracked_tickers ORDER BY ticker ASC')
            return [row["ticker"] for row in cursor.fetchall()]
    except sqlite3.Error as e:
        logger.error("Failed to retrieve tickers from database: %s", e)
        return []

def add_ticker_us(ticker: str) -> None:
    """Add a new US ticker to be tracked by the background job."""
    ticker = ticker.upper()
    now = datetime.now(timezone.utc).isoformat()
    try:
        with _get_connection() as conn:
            conn.execute(
                'INSERT OR IGNORE INTO tracked_tickers_us (ticker, added_at) VALUES (?, ?)',
                (ticker, now)
            )
            conn.commit()
    except sqlite3.Error as e:
        logger.error("Failed to add US ticker %s to database: %s", ticker, e)

def get_all_tickers_us() -> list[str]:
    """Retrieve all tracked US tickers from the database."""
    try:
        with _get_connection() as conn:
            cursor = conn.execute('SELECT ticker FROM tracked_tickers_us ORDER BY ticker ASC')
            return [row["ticker"] for row in cursor.fetchall()]
    except sqlite3.Error as e:
        logger.error("Failed to retrieve US tickers from database: %s", e)
        return []

def add_crypto_slug(slug: str) -> None:
    """Add a new crypto slug to be tracked by the background job."""
    slug = slug.lower()
    now = datetime.now(timezone.utc).isoformat()
    try:
        with _get_connection() as conn:
            conn.execute(
                'INSERT OR IGNORE INTO tracked_crypto_slugs (slug, added_at) VALUES (?, ?)',
                (slug, now)
            )
            conn.commit()
    except sqlite3.Error as e:
        logger.error("Failed to add crypto slug %s to database: %s", slug, e)

def get_all_crypto_slugs() -> list[str]:
    """Retrieve all tracked crypto slugs from the database."""
    try:
        with _get_connection() as conn:
            cursor = conn.execute('SELECT slug FROM tracked_crypto_slugs ORDER BY slug ASC')
            return [row["slug"] for row in cursor.fetchall()]
    except sqlite3.Error as e:
        logger.error("Failed to retrieve crypto slugs from database: %s", e)
        return []

def add_currency_pair(pair: str) -> None:
    """Add a new currency pair to be tracked by the background job. (e.g. USD-BRL)"""
    pair = pair.upper()
    now = datetime.now(timezone.utc).isoformat()
    try:
        with _get_connection() as conn:
            conn.execute(
                'INSERT OR IGNORE INTO tracked_currencies (currency_pair, added_at) VALUES (?, ?)',
                (pair, now)
            )
            conn.commit()
    except sqlite3.Error as e:
        logger.error("Failed to add currency pair %s to database: %s", pair, e)

def get_all_currency_pairs() -> list[str]:
    """Retrieve all tracked currency pairs from the database."""
    try:
        with _get_connection() as conn:
            cursor = conn.execute('SELECT currency_pair FROM tracked_currencies ORDER BY currency_pair ASC')
            return [row["currency_pair"] for row in cursor.fetchall()]
    except sqlite3.Error as e:
        logger.error("Failed to retrieve currency pairs from database: %s", e)
        return []

# Ensure tables are created when this module is imported
init_db()
