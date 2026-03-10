import pytest
from unittest.mock import patch, MagicMock
from app.services.currency_service import get_currency_quote, _quote_cache, _set_in_cache

@pytest.fixture(autouse=True)
def clear_cache():
    _quote_cache.clear()
    yield
    _quote_cache.clear()

@pytest.mark.asyncio
async def test_get_currency_quote_success():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "USDBRL": {
            "code": "USD",
            "codein": "BRL",
            "name": "Dólar Americano/Real Brasileiro",
            "bid": "5.5020",
        }
    }

    with patch("httpx.AsyncClient.get", return_value=mock_response):
        with patch("app.services.currency_service.add_currency_pair"):
            result = await get_currency_quote("USD", "BRL")
        
    assert result["price"] == 5.5020
    assert "updated_at" in result
    assert "USD-BRL" in _quote_cache

@pytest.mark.asyncio
async def test_get_currency_quote_from_cache():
    _set_in_cache("USD-BRL", 5.5020)
    
    with patch("httpx.AsyncClient.get") as mock_get:
        with patch("app.services.currency_service.add_currency_pair"):
            result = await get_currency_quote("USD", "BRL")
            mock_get.assert_not_called()
        
    assert result["price"] == 5.5020

@pytest.mark.asyncio
async def test_get_currency_quote_rate_limit_fallback():
    _set_in_cache("USD-BRL", 5.4000)
    
    # Simulate cache expiration
    _quote_cache["USD-BRL"]["expires_at"] = 0 
    
    mock_response = MagicMock()
    mock_response.status_code = 429
    
    with patch("httpx.AsyncClient.get", return_value=mock_response):
        with patch("app.services.currency_service.add_currency_pair"):
            result = await get_currency_quote("USD", "BRL")
            
    assert result["price"] == 5.4000 # Returned from fallback

@pytest.mark.asyncio
async def test_get_currency_quote_rate_limit_no_fallback():
    mock_response = MagicMock()
    mock_response.status_code = 429
    
    with patch("httpx.AsyncClient.get", return_value=mock_response):
        with patch("app.services.currency_service.add_currency_pair"):
            with pytest.raises(ValueError, match="Rate limit exceeded for USD-BRL on first fetch \\(no cache available\\). Try again later."):
                await get_currency_quote("USD", "BRL")
