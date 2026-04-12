"""
Tests for LCI and LCA pricing and endpoints.
"""
from datetime import date, timedelta
from typing import ClassVar

import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from app.models.lci_lca import LCILCAIndexType, LCILCAInstrumentType, LCILCAValueRequest
from app.services.lci_lca_pricing_engine import calculate_lci_lca

@pytest.fixture(scope="module")
def client():
    from app.main import app
    with TestClient(app, raise_server_exceptions=True) as c:
        c.headers["X-API-Key"] = "wiawwuXSQm32jc4nRKgbYB"
        yield c

# ---------------------------------------------------------------------------
# Engine Tests
# ---------------------------------------------------------------------------

class TestLCILCAPricingEngine:

    def test_lci_cdi_pricing_with_grace_period(self):
        """Test pricing a CDI-indexed LCI inside and outside grace period."""
        purchase_date = date.today() - timedelta(days=60)
        maturity_date = purchase_date + timedelta(days=365*2)
        request = LCILCAValueRequest(
            instrument_type=LCILCAInstrumentType.LCI,
            principal=10000.0,
            rate=0.95,
            index_type=LCILCAIndexType.CDI,
            purchase_date=purchase_date,
            maturity_date=maturity_date,
            grace_period_days=90,
        )
        
        # Test inside grace period
        ref_inside = purchase_date + timedelta(days=50)
        result_inside = calculate_lci_lca(request, ref=ref_inside)
        assert result_inside.instrument_type == LCILCAInstrumentType.LCI
        assert result_inside.current_value >= 10000.0
        assert result_inside.redeemable is False
        
        # Test outside grace period
        ref_outside = purchase_date + timedelta(days=91)
        result_outside = calculate_lci_lca(request, ref=ref_outside)
        assert result_outside.redeemable is True

    def test_lca_prefixado_pricing(self):
        """Test pricing a PREFIXADO LCA."""
        purchase_date = date.today() - timedelta(days=365)
        maturity_date = purchase_date + timedelta(days=365*3)
        request = LCILCAValueRequest(
            instrument_type=LCILCAInstrumentType.LCA,
            principal=20000.0,
            rate=0.10,  # 10%
            index_type=LCILCAIndexType.PREFIXADO,
            purchase_date=purchase_date,
            maturity_date=maturity_date,
            grace_period_days=180,
        )
        
        ref = purchase_date + timedelta(days=365)
        result = calculate_lci_lca(request, ref=ref)
        
        assert result.instrument_type == LCILCAInstrumentType.LCA
        assert result.redeemable is True
        # exact after 1 year: 20000 * 1.10 = 22000
        assert result.current_value == pytest.approx(22000.0, abs=10.0)

    def test_lci_ipca_pricing(self):
        """Test pricing an IPCA LCI."""
        purchase_date = date.today() - timedelta(days=100)
        maturity_date = purchase_date + timedelta(days=800)
        request = LCILCAValueRequest(
            instrument_type=LCILCAInstrumentType.LCI,
            principal=15000.0,
            rate=0.05,
            index_type=LCILCAIndexType.IPCA,
            purchase_date=purchase_date,
            maturity_date=maturity_date,
            grace_period_days=0,
        )
        
        result = calculate_lci_lca(request)
        assert result.current_value >= 15000.0
        assert result.redeemable is True

# ---------------------------------------------------------------------------
# API Route Tests
# ---------------------------------------------------------------------------

def test_lci_lca_api_endpoint(client):
    """Test the POST /lci-lca/value route."""
    purchase_date_str = (date.today() - timedelta(days=120)).isoformat()
    maturity_date_str = (date.today() + timedelta(days=600)).isoformat()
    
    payload = {
        "instrument_type": "LCI",
        "principal": 15000.0,
        "rate": 0.95,
        "index_type": "CDI",
        "purchase_date": purchase_date_str,
        "maturity_date": maturity_date_str,
        "grace_period_days": 90
    }
    
    response = client.post("/lci-lca/value", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data["instrument_type"] == "LCI"
    assert "current_value" in data
    assert "yield_amount" in data
    assert "yield_percentage" in data
    assert data["redeemable"] is True
    assert "calculation_date" in data
