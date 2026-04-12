import pytest
import os
from unittest.mock import patch, MagicMock
from app.utils.database import (
    add_ticker, get_all_tickers,
    add_ticker_us, get_all_tickers_us,
    add_crypto_slug, get_all_crypto_slugs,
    add_currency_pair, get_all_currency_pairs
)


@pytest.fixture(autouse=True)
def mock_database(monkeypatch):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=None)
    
    mock_pool = MagicMock()
    mock_pool.getconn.return_value = mock_conn
    
    monkeypatch.setattr("app.utils.database._get_connection_pool", lambda: mock_pool)
    
    yield mock_cursor, mock_conn


def test_add_ticker(mock_database):
    mock_cursor, mock_conn = mock_database
    add_ticker("PETR4")
    mock_cursor.execute.assert_called()
    mock_conn.commit.assert_called()


def test_add_ticker_uppercase(mock_database):
    mock_cursor, mock_conn = mock_database
    add_ticker("mglu3")
    call_args = mock_cursor.execute.call_args
    assert "MGLU3" in str(call_args)


def test_get_all_tickers(mock_database):
    mock_cursor, mock_conn = mock_database
    mock_cursor.fetchall.return_value = [("PETR4",), ("VALE3",)]
    
    tickers = get_all_tickers()
    assert "PETR4" in tickers
    assert "VALE3" in tickers


def test_us_tickers(mock_database):
    mock_cursor, mock_conn = mock_database
    mock_cursor.fetchall.return_value = [("AAPL",), ("TSLA",)]
    
    tickers = get_all_tickers_us()
    assert "AAPL" in tickers
    assert "TSLA" in tickers


def test_crypto_slugs(mock_database):
    mock_cursor, mock_conn = mock_database
    mock_cursor.fetchall.return_value = [("bitcoin",), ("ethereum",)]
    
    slugs = get_all_crypto_slugs()
    assert "bitcoin" in slugs
    assert "ethereum" in slugs


def test_currency_pairs(mock_database):
    mock_cursor, mock_conn = mock_database
    mock_cursor.fetchall.return_value = [("EUR-BRL",), ("USD-BRL",)]
    
    pairs = get_all_currency_pairs()
    assert "EUR-BRL" in pairs
    assert "USD-BRL" in pairs
