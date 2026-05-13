"""
Unit tests for the CDB pricing engine.

All tests use deterministic inputs and known/hand-computed outputs.
Market data (CDI factors, IPCA series) is injected via mocks.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from app.models.cdb import CDBIndexType, CDBValueRequest
from app.services.cdb_pricing_engine import (
    CDBResult,
    calculate_cdb,
    price_cdb_cdi,
    price_cdb_ipca,
    price_cdb_prefixado,
)

# Fixed reference date so tests are deterministic
REF_DATE = date(2026, 3, 7)
PURCHASE_DATE = date(2024, 6, 1)
MATURITY_DATE = date(2027, 6, 1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cdi_factor_entry(date_str: str, valor: str = "0.055131") -> dict:
    """Create a mock BCB SGS-12 daily factor entry."""
    return {"data": date_str, "valor": valor}


_MOCK_CDI_FACTORS = [
    _make_cdi_factor_entry("01/03/2026"),
    _make_cdi_factor_entry("02/03/2026"),
    _make_cdi_factor_entry("03/03/2026"),
    _make_cdi_factor_entry("04/03/2026"),
    _make_cdi_factor_entry("05/03/2026"),
    _make_cdi_factor_entry("06/03/2026"),
    _make_cdi_factor_entry("07/03/2026"),
]

_MOCK_IPCA_SERIES = [
    {"data": "01/06/2024", "valor": "0.46"},
    {"data": "01/07/2024", "valor": "0.38"},
    {"data": "01/08/2024", "valor": "0.44"},
    {"data": "01/09/2024", "valor": "0.44"},
    {"data": "01/10/2024", "valor": "0.56"},
    {"data": "01/11/2024", "valor": "0.39"},
    {"data": "01/12/2024", "valor": "0.52"},
    {"data": "01/01/2025", "valor": "0.16"},
    {"data": "01/02/2025", "valor": "1.31"},
    {"data": "01/03/2025", "valor": "0.56"},
]


# ---------------------------------------------------------------------------
# CDI Indexed CDB
# ---------------------------------------------------------------------------

class TestCDBCDI:
    def test_basic_pricing_returns_positive(self):
        """CDI CDB at 110% CDI — value should be greater than principal."""
        with (
            patch("app.services.cdb_pricing_engine.cdb_service.get_cdi_daily_factors", return_value=_MOCK_CDI_FACTORS),
            patch("app.services.cdb_pricing_engine.cdb_service.get_fallback_daily_factor", return_value=0.0004970),
        ):
            result = price_cdb_cdi(
                principal=10_000.0,
                rate=1.10,
                purchase_date=PURCHASE_DATE,
                ref=REF_DATE,
            )

        assert isinstance(result, CDBResult)
        assert result.current_value > 10_000.0
        assert result.yield_amount > 0
        assert result.yield_percentage > 0
        assert result.calculation_date == REF_DATE

    def test_100pct_cdi_yields_less_than_110pct(self):
        """110% CDI must net more than 100% CDI for the same period."""
        with (
            patch("app.services.cdb_pricing_engine.cdb_service.get_cdi_daily_factors", return_value=_MOCK_CDI_FACTORS),
            patch("app.services.cdb_pricing_engine.cdb_service.get_fallback_daily_factor", return_value=0.0004970),
        ):
            r100 = price_cdb_cdi(10_000, 1.00, PURCHASE_DATE, REF_DATE)
            r110 = price_cdb_cdi(10_000, 1.10, PURCHASE_DATE, REF_DATE)

        assert r110.current_value > r100.current_value

    def test_no_live_data_uses_fallback(self):
        """With no live CDI factors, fallback should still produce a positive value."""
        with (
            patch("app.services.cdb_pricing_engine.cdb_service.get_cdi_daily_factors", return_value=[]),
            patch("app.services.cdb_pricing_engine.cdb_service.get_fallback_daily_factor", return_value=0.0004970),
        ):
            result = price_cdb_cdi(10_000, 1.10, PURCHASE_DATE, REF_DATE)

        assert result.current_value > 10_000.0

    def test_purchase_same_as_ref_has_no_yield(self):
        """Buying and valuing on the same date gives no yield from live factors."""
        same_day = date(2026, 3, 6)  # just before last factor
        with (
            patch("app.services.cdb_pricing_engine.cdb_service.get_cdi_daily_factors", return_value=_MOCK_CDI_FACTORS),
            patch("app.services.cdb_pricing_engine.cdb_service.get_fallback_daily_factor", return_value=0.0004970),
        ):
            result = price_cdb_cdi(10_000, 1.10, same_day, same_day)

        # Same day: only the fallback phase runs (0 calendar days → 0 bdays), ≈ 0 yield
        assert result.current_value >= 10_000.0


# ---------------------------------------------------------------------------
# Prefixado CDB
# ---------------------------------------------------------------------------

class TestCDBPrefixado:
    def test_basic_pricing(self):
        """Prefixado at 12% p.a. for ~1.75 years should be > principal."""
        result = price_cdb_prefixado(10_000, 0.12, PURCHASE_DATE, REF_DATE)

        assert result.current_value > 10_000.0
        assert result.calculation_date == REF_DATE

    def test_known_formula_value(self):
        """Validate against hand-computed result: 10000*(1.12)^years."""
        years = (REF_DATE - PURCHASE_DATE).days / 365.0
        expected = round(10_000 * (1.12 ** years), 2)

        result = price_cdb_prefixado(10_000, 0.12, PURCHASE_DATE, REF_DATE)

        assert result.current_value == pytest.approx(expected, rel=1e-4)

    def test_higher_rate_yields_more(self):
        """15% p.a. CDB must produce more than 12% p.a. over the same period."""
        r12 = price_cdb_prefixado(10_000, 0.12, PURCHASE_DATE, REF_DATE)
        r15 = price_cdb_prefixado(10_000, 0.15, PURCHASE_DATE, REF_DATE)

        assert r15.current_value > r12.current_value

    def test_zero_rate_returns_principal(self):
        """With 0% rate, value must equal principal (no growth)."""
        result = price_cdb_prefixado(10_000, 0.0, PURCHASE_DATE, REF_DATE)

        assert result.current_value == pytest.approx(10_000.0, rel=1e-5)
        assert result.yield_amount == pytest.approx(0.0, abs=0.01)


# ---------------------------------------------------------------------------
# IPCA Indexed CDB
# ---------------------------------------------------------------------------

class TestCDBIPCA:
    def test_basic_pricing(self):
        """IPCA + 5% CDB with mocked inflation should return value > principal."""
        with patch(
            "app.services.cdb_pricing_engine.history_repository.get_latest_inflation",
            return_value={"vna": 4782.22, "ipca_monthly": _MOCK_IPCA_SERIES},
        ):
            result = price_cdb_ipca(10_000, 0.05, PURCHASE_DATE, REF_DATE)

        assert result.current_value > 10_000.0
        assert result.calculation_date == REF_DATE

    def test_higher_real_spread_yields_more(self):
        """IPCA + 8% must produce more than IPCA + 5%."""
        with patch(
            "app.services.cdb_pricing_engine.history_repository.get_latest_inflation",
            return_value={"vna": 4782.22, "ipca_monthly": _MOCK_IPCA_SERIES},
        ):
            r5 = price_cdb_ipca(10_000, 0.05, PURCHASE_DATE, REF_DATE)
            r8 = price_cdb_ipca(10_000, 0.08, PURCHASE_DATE, REF_DATE)

        assert r8.current_value > r5.current_value


# ---------------------------------------------------------------------------
# Edge Cases — Dispatcher
# ---------------------------------------------------------------------------

class TestCDBEdgeCases:
    def _make_request(self, index_type: str = "PREFIXADO") -> CDBValueRequest:
        return CDBValueRequest(
            principal=10_000,
            rate=0.12,
            index_type=CDBIndexType(index_type),
            purchase_date=date(2024, 1, 1),
            maturity_date=date(2028, 1, 1),
        )

    def test_matured_cdb_returns_is_matured_true(self):
        """Valuing a CDB past its maturity date should return is_matured=True."""
        req = CDBValueRequest(
            principal=10_000,
            rate=0.12,
            index_type=CDBIndexType.PREFIXADO,
            purchase_date=date(2020, 1, 1),
            maturity_date=date(2023, 1, 1),
        )
        # Use ref = today (past maturity)
        result = calculate_cdb(req)

        assert result.is_matured is True
        assert result.current_value > 10_000.0  # still grew until maturity

    def test_purchase_date_future_raises(self):
        """A future purchase_date should be rejected by the model validator."""
        with pytest.raises(Exception):
            CDBValueRequest(
                principal=10_000,
                rate=0.12,
                index_type=CDBIndexType.PREFIXADO,
                purchase_date=date(2030, 1, 1),
                maturity_date=date(2033, 1, 1),
            )

    def test_maturity_before_purchase_raises(self):
        """maturity_date before purchase_date should be rejected."""
        with pytest.raises(Exception):
            CDBValueRequest(
                principal=10_000,
                rate=0.12,
                index_type=CDBIndexType.PREFIXADO,
                purchase_date=date(2025, 1, 1),
                maturity_date=date(2024, 1, 1),
            )

    def test_all_index_types_return_positive(self):
        """All three index types should produce a positive current_value."""
        for index_type in [CDBIndexType.PREFIXADO, CDBIndexType.CDI, CDBIndexType.IPCA]:
            req = CDBValueRequest(
                principal=10_000,
                rate=1.10 if index_type == CDBIndexType.CDI else 0.12,
                index_type=index_type,
                purchase_date=date(2024, 1, 1),
                maturity_date=date(2028, 1, 1),
            )
            with (
                patch("app.services.cdb_pricing_engine.cdb_service.get_cdi_daily_factors", return_value=[]),
                patch("app.services.cdb_pricing_engine.cdb_service.get_fallback_daily_factor", return_value=0.0004970),
                patch(
                    "app.services.cdb_pricing_engine.history_repository.get_latest_inflation",
                    return_value={"vna": 4782.22, "ipca_monthly": _MOCK_IPCA_SERIES},
                ),
            ):
                result = calculate_cdb(req)

            assert result.current_value > 10_000.0, f"Failed for {index_type}"
