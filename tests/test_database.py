import pytest
import sqlite3
import os
from unittest.mock import patch, MagicMock
from app.utils.database import (
    add_ticker, get_all_tickers, _get_connection, DB_PATH,
    add_ticker_us, get_all_tickers_us,
    add_crypto_slug, get_all_crypto_slugs,
    add_currency_pair, get_all_currency_pairs
)

@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch):
    test_db = "test_tickers.db"
    monkeypatch.setattr("app.utils.database.DB_PATH", test_db)
    
    # Init DB schema
    import app.utils.database as app_db
    app_db.init_db()
    
    yield
    
    if os.path.exists(test_db):
        os.remove(test_db)

def test_add_ticker_success():
    add_ticker("PETR4")
    tickers = get_all_tickers()
    assert "PETR4" in tickers
    assert len(tickers) == 1

def test_add_ticker_uppercase():
    add_ticker("mglu3")
    tickers = get_all_tickers()
    assert "MGLU3" in tickers

def test_add_ticker_duplicate_ignored():
    add_ticker("VALE3")
    add_ticker("VALE3")
    add_ticker("VALE3")
    tickers = get_all_tickers()
    assert len(tickers) == 1
    assert "VALE3" in tickers

def test_get_all_tickers_ordered():
    add_ticker("ZBRA3")
    add_ticker("AMZN34")
    add_ticker("PETR4")
    
    tickers = get_all_tickers()
    assert tickers == ["AMZN34", "PETR4", "ZBRA3"]

def test_us_tickers():
    add_ticker_us("aapl")
    add_ticker_us("TSLA")
    add_ticker_us("aapl")
    tickers = get_all_tickers_us()
    assert tickers == ["AAPL", "TSLA"]

def test_crypto_slugs():
    add_crypto_slug("BITCOIN")
    add_crypto_slug("ethereum")
    add_crypto_slug("bitcoin")
    slugs = get_all_crypto_slugs()
    assert slugs == ["bitcoin", "ethereum"]

def test_currency_pairs():
    add_currency_pair("usd-brl")
    add_currency_pair("EUR-BRL")
    add_currency_pair("usd-brl")
    pairs = get_all_currency_pairs()
    assert pairs == ["EUR-BRL", "USD-BRL"]
