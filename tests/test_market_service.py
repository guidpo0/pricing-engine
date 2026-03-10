import pytest
from unittest.mock import patch, MagicMock
from app.services.market_service import get_market_quote, _quote_cache, _set_in_cache

@pytest.fixture(autouse=True)
def clear_cache():
    _quote_cache.clear()
    yield
    _quote_cache.clear()

@pytest.mark.asyncio
async def test_get_market_quote_success():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": [{"regularMarketPrice": 38.50}]
    }

    with patch("httpx.AsyncClient.get", return_value=mock_response):
        result = await get_market_quote("PETR4")
        
    assert result["price"] == 38.50
    assert "updated_at" in result
    assert "PETR4" in _quote_cache

@pytest.mark.asyncio
async def test_get_market_quote_from_cache():
    _set_in_cache("PETR4", 38.50)
    
    with patch("httpx.AsyncClient.get") as mock_get:
        result = await get_market_quote("PETR4")
        mock_get.assert_not_called()
        
    assert result["price"] == 38.50

@pytest.mark.asyncio
async def test_get_market_quote_not_found():
    mock_response = MagicMock()
    mock_response.status_code = 404
    
    with patch("httpx.AsyncClient.get", return_value=mock_response):
        with pytest.raises(ValueError, match="not found"):
            await get_market_quote("INVALID")

@pytest.mark.asyncio
async def test_get_market_quote_retry_success(monkeypatch):
    # Shorten sleep for testing
    import app.services.market_service as ms
    async def mock_sleep(x):
        pass
    monkeypatch.setattr("asyncio.sleep", mock_sleep)
    
    responses = [
        MagicMock(status_code=429),
        MagicMock(status_code=200)
    ]
    responses[1].json.return_value = {"results": [{"regularMarketPrice": 38.50}]}
    
    with patch("httpx.AsyncClient.get", side_effect=responses):
        result = await get_market_quote("PETR4")
        
    assert result["price"] == 38.50
