import pytest
from unittest.mock import patch, MagicMock
from app.services.us_market_service import get_us_market_quote, _quote_cache, _set_in_cache

@pytest.fixture(autouse=True)
def clear_cache():
    _quote_cache.clear()
    yield
    _quote_cache.clear()

@pytest.fixture(autouse=True)
def mock_history_repository():
    with patch("app.services.us_market_service.history_repository") as mock_repo:
        mock_repo.get_latest_us_stock_quote.return_value = None
        mock_repo.insert_us_stock_quote.return_value = None
        yield mock_repo

@pytest.mark.asyncio
async def test_get_us_market_quote_success(mock_history_repository):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"price": "150.25"}

    with patch("httpx.AsyncClient.get", return_value=mock_response):
        with patch("app.services.us_market_service.add_ticker_us"):
            result = await get_us_market_quote("AAPL")
        
    assert result["price"] == 150.25
    assert "updated_at" in result
    assert "AAPL" in _quote_cache

@pytest.mark.asyncio
async def test_get_us_market_quote_from_cache():
    _set_in_cache("AAPL", 150.25)
    
    with patch("httpx.AsyncClient.get") as mock_get:
        with patch("app.services.us_market_service.add_ticker_us"):
            result = await get_us_market_quote("AAPL")
            mock_get.assert_not_called()
        
    assert result["price"] == 150.25

@pytest.mark.asyncio
async def test_get_us_market_quote_rate_limit_fallback():
    _set_in_cache("AAPL", 140.00)
    
    _quote_cache["AAPL"]["expires_at"] = 0 
    
    mock_response = MagicMock()
    mock_response.status_code = 429
    
    with patch("httpx.AsyncClient.get", return_value=mock_response):
        with patch("app.services.us_market_service.add_ticker_us"):
            result = await get_us_market_quote("AAPL")
            
    assert result["price"] == 140.00

@pytest.mark.asyncio
async def test_get_us_market_quote_rate_limit_no_fallback(mock_history_repository):
    mock_response = MagicMock()
    mock_response.status_code = 429
    
    with patch("httpx.AsyncClient.get", return_value=mock_response):
        with patch("app.services.us_market_service.add_ticker_us"):
            with pytest.raises(ValueError, match=r"Rate limit exceeded for AAPL on first fetch \(no cache available\)\. Try again later\."):
                await get_us_market_quote("AAPL")
