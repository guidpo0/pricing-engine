"""
Integration tests for the API routes using FastAPI's TestClient.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    """
    TestClient with the lifespan events.
    """
    from app.main import app

    with TestClient(app, raise_server_exceptions=True) as c:
        c.headers["X-API-Key"] = "wiawwuXSQm32jc4nRKgbYB"
        yield c


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    def test_health_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "curves_last_updated" in data
        assert "vna_last_updated" in data


# ---------------------------------------------------------------------------
# POST /bonds/price
# ---------------------------------------------------------------------------

class TestBondPriceEndpoint:
    def _mock_curve(self, tenor, curve_type="pre"):
        if curve_type == "pre":
            return 0.13
        if curve_type == "ipca":
            return 0.08
        return 0.1325

    def test_prefixado_pricing(self, client):
        with (
            patch("app.api.routes.calculate_pu") as mock_pu,
        ):
            from app.services.pricing_engine import PricingResult
            from datetime import date

            mock_pu.return_value = PricingResult(
                pu=711.32, yield_rate=0.12, vna=None, calculation_date=date(2026, 3, 7)
            )
            response = client.post("/bonds/price", json={
                "type": "PREFIXADO",
                "maturity_date": "2029-01-01",
            })

        assert response.status_code == 200
        data = response.json()
        assert data["bond_type"] == "PREFIXADO"
        assert data["pu"] == 711.32
        assert data["yield_rate"] == 0.12
        assert data["maturity_date"] == "2029-01-01"
        assert data["calculation_date"] == "2026-03-07"

    def test_all_bond_types_accepted(self, client):
        from app.services.pricing_engine import PricingResult
        from datetime import date

        bond_configs = [
            ("PREFIXADO", "2029-01-01"),
            ("PREFIXADO_JUROS", "2033-01-01"),
            ("IPCA", "2035-05-15"),
            ("IPCA_JUROS", "2040-08-15"),
            ("SELIC", "2027-03-01"),
        ]
        for bond_type, maturity in bond_configs:
            with patch("app.api.routes.calculate_pu") as mock_pu:
                mock_pu.return_value = PricingResult(
                    pu=1000.0, yield_rate=0.13, vna=None, calculation_date=date(2026, 3, 7)
                )
                response = client.post("/bonds/price", json={
                    "type": bond_type,
                    "maturity_date": maturity,
                })
            assert response.status_code == 200, f"Failed for {bond_type}: {response.text}"

    def test_invalid_bond_type_returns_422(self, client):
        response = client.post("/bonds/price", json={
            "type": "INVALID_TYPE",
            "maturity_date": "2029-01-01",
        })
        assert response.status_code == 422

    def test_past_maturity_returns_422(self, client):
        response = client.post("/bonds/price", json={
            "type": "PREFIXADO",
            "maturity_date": "2020-01-01",
        })
        assert response.status_code == 422

    def test_missing_params_returns_422(self, client):
        response = client.post("/bonds/price", json={"type": "PREFIXADO"})
        assert response.status_code == 422

    def test_spread_accepted(self, client):
        from app.services.pricing_engine import PricingResult
        from datetime import date

        with patch("app.api.routes.calculate_pu") as mock_pu:
            mock_pu.return_value = PricingResult(
                pu=700.0, yield_rate=0.135, vna=None, calculation_date=date(2026, 3, 7)
            )
            response = client.post("/bonds/price", json={
                "type": "PREFIXADO",
                "maturity_date": "2030-01-01",
                "spread": 0.005,
            })

        assert response.status_code == 200


# ---------------------------------------------------------------------------
# POST /portfolio/value
# ---------------------------------------------------------------------------

class TestPortfolioValueEndpoint:
    def test_portfolio_value_basic(self, client):
        from app.services.pricing_engine import PricingResult
        from datetime import date

        with patch("app.api.routes.calculate_pu") as mock_pu:
            mock_pu.return_value = PricingResult(
                pu=1520.34, yield_rate=0.08, vna=4782.22, calculation_date=date(2026, 3, 7)
            )
            response = client.post("/portfolio/value", json={
                "bond_type": "IPCA",
                "maturity_date": "2035-05-15",
                "quantity": 0.73,
            })

        assert response.status_code == 200
        data = response.json()
        assert data["pu"] == 1520.34
        assert data["position_value"] == pytest.approx(1520.34 * 0.73, rel=1e-5)
        assert data["quantity"] == 0.73
        assert data["vna"] == 4782.22

    def test_past_maturity_returns_422(self, client):
        response = client.post("/portfolio/value", json={
            "bond_type": "IPCA",
            "maturity_date": "2020-05-15",
            "quantity": 1.0,
        })
        assert response.status_code == 422

    def test_zero_quantity_rejected(self, client):
        response = client.post("/portfolio/value", json={
            "bond_type": "PREFIXADO",
            "maturity_date": "2030-01-01",
            "quantity": 0,
        })
        assert response.status_code == 422

    def test_invalid_bond_type_rejected(self, client):
        response = client.post("/portfolio/value", json={
            "bond_type": "BITCOINTESOURO",
            "maturity_date": "2030-01-01",
            "quantity": 1.0,
        })
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Market data debug endpoints
# ---------------------------------------------------------------------------

class TestMarketEndpoints:
    def test_market_curves_endpoint(self, client):
        response = client.get("/market/curves")
        assert response.status_code == 200
        data = response.json()
        assert "pre_curve" in data
        assert "ipca_curve" in data
        assert "selic_rate" in data

    def test_market_vna_endpoint(self, client):
        response = client.get("/market/vna")
        assert response.status_code == 200
        data = response.json()
        assert "vna" in data
        assert data["vna"] > 0

    def test_market_tickers_endpoint(self, client):
        with patch("app.api.routes.get_all_tickers", return_value=["PETR4"]), \
             patch("app.api.routes.get_all_tickers_us", return_value=["AAPL"]), \
             patch("app.api.routes.get_all_crypto_slugs", return_value=["bitcoin"]), \
             patch("app.api.routes.get_all_currency_pairs", return_value=["USD-BRL"]):
            
            response = client.get("/market/tickers")
            
        assert response.status_code == 200
        data = response.json()
        assert data["br_tickers"] == ["PETR4"]
        assert data["us_tickers"] == ["AAPL"]
        assert data["crypto_slugs"] == ["bitcoin"]
        assert data["currencies"] == ["USD-BRL"]

    def test_market_quote_success(self, client):
        with patch("app.api.routes.history_repository") as mock_repo:
            mock_repo.get_latest_stock_quote.return_value = None
            mock_repo.insert_stock_quote.return_value = None
            with patch("app.api.routes.market_service.get_market_quote", new_callable=AsyncMock) as mock_get:
                from datetime import datetime, timezone
                mock_get.return_value = {
                    "price": 38.50,
                    "updated_at": datetime.now(timezone.utc)
                }
                response = client.get("/market/quote/PETR4")
                
        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "PETR4"
        assert data["unit_price"] == 38.50
        assert "quantity" not in data or data["quantity"] is None

    def test_market_quote_with_quantity(self, client):
        with patch("app.api.routes.history_repository") as mock_repo:
            mock_repo.get_latest_stock_quote.return_value = None
            mock_repo.insert_stock_quote.return_value = None
            with patch("app.api.routes.market_service.get_market_quote", new_callable=AsyncMock) as mock_get:
                from datetime import datetime, timezone
                mock_get.return_value = {
                    "price": 38.50,
                    "updated_at": datetime.now(timezone.utc)
                }
                response = client.get("/market/quote/PETR4?quantity=100")
                
        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "PETR4"
        assert data["unit_price"] == 38.50
        assert data["quantity"] == 100
        assert data["position_value"] == 3850.0

    def test_market_quote_not_found(self, client):
        with patch("app.api.routes.history_repository") as mock_repo:
            mock_repo.get_latest_stock_quote.return_value = None
            mock_repo.insert_stock_quote.return_value = None
            with patch("app.api.routes.market_service.get_market_quote", new_callable=AsyncMock) as mock_get:
                mock_get.side_effect = ValueError("Ticker INVALID not found")
                response = client.get("/market/quote/INVALID")
                
        assert response.status_code == 404
