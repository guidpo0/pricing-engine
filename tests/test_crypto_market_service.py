import pytest
from unittest.mock import patch, MagicMock
from app.services.crypto_market_service import get_crypto_quote, _quote_cache, _set_in_cache

@pytest.fixture(autouse=True)
def clear_cache():
    _quote_cache.clear()
    yield
    _quote_cache.clear()

@pytest.fixture(autouse=True)
def mock_history_repository():
    with patch("app.services.crypto_market_service.history_repository") as mock_repo:
        mock_repo.get_latest_crypto_quote.return_value = None
        mock_repo.insert_crypto_quote.return_value = None
        yield mock_repo

@pytest.mark.asyncio
async def test_get_crypto_quote_success(mock_history_repository):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": {"error_code": 0, "error_message": None},
        "data": {
            "1": {
                "id": 1,
                "name": "Bitcoin",
                "symbol": "BTC",
                "slug": "bitcoin",
                "quote": {
                    "USD": {
                        "price": 65000.50
                    }
                }
            }
        }
    }

    with patch("httpx.AsyncClient.get", return_value=mock_response):
        with patch("app.services.crypto_market_service.add_crypto_slug"):
            result = await get_crypto_quote("bitcoin")
        
    assert result["price"] == 65000.50
    assert "updated_at" in result
    assert "bitcoin" in _quote_cache

@pytest.mark.asyncio
async def test_get_crypto_quote_from_cache():
    _set_in_cache("bitcoin", 65000.50)
    
    with patch("httpx.AsyncClient.get") as mock_get:
        with patch("app.services.crypto_market_service.add_crypto_slug"):
            result = await get_crypto_quote("bitcoin")
            mock_get.assert_not_called()
        
    assert result["price"] == 65000.50

@pytest.mark.asyncio
async def test_get_crypto_quote_rate_limit_fallback():
    _set_in_cache("bitcoin", 64000.00)
    
    _quote_cache["bitcoin"]["expires_at"] = 0 
    
    mock_response = MagicMock()
    mock_response.status_code = 429
    
    with patch("httpx.AsyncClient.get", return_value=mock_response):
        with patch("app.services.crypto_market_service.add_crypto_slug"):
            result = await get_crypto_quote("bitcoin")
            
    assert result["price"] == 64000.00

@pytest.mark.asyncio
async def test_get_crypto_quote_rate_limit_no_fallback(mock_history_repository):
    mock_response = MagicMock()
    mock_response.status_code = 429
    
    with patch("httpx.AsyncClient.get", return_value=mock_response):
        with patch("app.services.crypto_market_service.add_crypto_slug"):
            with pytest.raises(ValueError, match=r"Rate limit exceeded for bitcoin on first fetch \(no cache available\)\. Try again later\."):
                await get_crypto_quote("bitcoin")
