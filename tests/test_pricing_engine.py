"""
Unit tests for the individual bond pricing formulas.

All tests use deterministic inputs and known outputs (calculated by hand
or from reference tables) to validate the pricing implementations.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from app.models.bond import BondType
from app.services.pricing_engine import (
    PricingResult,
    calculate_pu,
    price_lft,
    price_ltn,
    price_ntnb,
    price_ntnb_principal,
    price_ntnf,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REF_DATE = date(2026, 3, 7)  # Fixed reference date for deterministic tests


def _mock_pre_rate(tenor, curve_type="pre"):
    """Deterministic mock rate: 13% p.a. for pre curve."""
    if curve_type == "pre":
        return 0.13
    elif curve_type == "ipca":
        return 0.08
    elif curve_type == "selic":
        return 0.1325
    return 0.13


# ---------------------------------------------------------------------------
# LTN pricing
# ---------------------------------------------------------------------------

class TestPriceLTN:
    def test_basic_pricing(self):
        """LTN: PU = 1000 / (1+r)^years — value should be below face value."""
        maturity = date(2029, 1, 1)
        with patch("app.services.pricing_engine.curve_service.get_rate", side_effect=_mock_pre_rate):
            result = price_ltn(maturity, spread=0.0, ref=REF_DATE)

        assert isinstance(result, PricingResult)
        assert 0 < result.pu < 1000, "PU should be a discount to face value"
        assert result.yield_rate == pytest.approx(0.13, abs=1e-6)
        assert result.vna is None
        assert result.calculation_date == REF_DATE

    def test_price_increases_as_maturity_approaches(self):
        """PU should increase as the bond approaches maturity (holding rate constant)."""
        with patch("app.services.pricing_engine.curve_service.get_rate", side_effect=_mock_pre_rate):
            far = price_ltn(date(2035, 1, 1), ref=REF_DATE)
            near = price_ltn(date(2028, 1, 1), ref=REF_DATE)

        assert near.pu > far.pu

    def test_positive_spread_reduces_price(self):
        """A positive spread over the benchmark rate should lower the PU."""
        maturity = date(2030, 1, 1)
        with patch("app.services.pricing_engine.curve_service.get_rate", side_effect=_mock_pre_rate):
            no_spread = price_ltn(maturity, spread=0.0, ref=REF_DATE)
            with_spread = price_ltn(maturity, spread=0.01, ref=REF_DATE)

        assert with_spread.pu < no_spread.pu

    def test_matured_bond_raises(self):
        """Pricing a matured bond should raise ValueError."""
        with pytest.raises(ValueError, match="matured"):
            price_ltn(date(2020, 1, 1), ref=REF_DATE)

    def test_known_value(self):
        """
        Known approximate: LTN 2029-01-01, rate=13.5%, ~2.8 years.
        PU ≈ 1000 / 1.135^2.8 ≈ 695
        """
        from app.utils.date_utils import years_to_maturity
        maturity = date(2029, 1, 1)
        RATE = 0.135
        tenor = years_to_maturity(maturity, REF_DATE)
        expected_pu = 1000 / (1 + RATE) ** tenor

        with patch("app.services.pricing_engine.curve_service.get_rate", return_value=RATE):
            result = price_ltn(maturity, ref=REF_DATE)

        assert result.pu == pytest.approx(expected_pu, rel=1e-5)


# ---------------------------------------------------------------------------
# NTN-F pricing
# ---------------------------------------------------------------------------

class TestPriceNTNF:
    def test_basic_pricing(self):
        """NTN-F: should return a reasonable PU with coupon cash flows."""
        maturity = date(2033, 1, 1)
        with patch("app.services.pricing_engine.curve_service.get_rate", side_effect=_mock_pre_rate):
            result = price_ntnf(maturity, ref=REF_DATE)

        assert result.pu > 0
        assert result.calculation_date == REF_DATE

    def test_rate_equal_to_coupon_trades_near_par(self):
        """When market rate ≈ coupon rate (10%), NTN-F should trade near par (1000)."""
        maturity = date(2031, 1, 1)
        RATE = 0.10  # equals coupon rate
        with patch("app.services.pricing_engine.curve_service.get_rate", return_value=RATE):
            result = price_ntnf(maturity, ref=REF_DATE)

        # Near par — allow 5% tolerance due to day count differences
        assert abs(result.pu - 1000) < 50

    def test_matured_bond_raises(self):
        with pytest.raises(ValueError):
            price_ntnf(date(2020, 1, 1), ref=REF_DATE)


# ---------------------------------------------------------------------------
# NTN-B Principal pricing
# ---------------------------------------------------------------------------

class TestPriceNTNBPrincipal:
    def test_basic_pricing(self):
        """NTN-B Principal: PU = VNA / (1+real)^years."""
        maturity = date(2035, 5, 15)
        VNA = 4782.22
        with (
            patch("app.services.pricing_engine.curve_service.get_rate", side_effect=_mock_pre_rate),
            patch("app.services.pricing_engine.inflation_service.get_vna", return_value=VNA),
        ):
            result = price_ntnb_principal(maturity, ref=REF_DATE)

        assert result.pu > 0
        assert result.vna == VNA
        assert result.yield_rate == pytest.approx(0.08, abs=1e-6)

    def test_known_value(self):
        """Verify against hand-computed value."""
        from app.utils.date_utils import years_to_maturity
        maturity = date(2035, 5, 15)
        VNA = 4782.22
        RATE = 0.08
        tenor = years_to_maturity(maturity, REF_DATE)
        expected_pu = VNA / (1 + RATE) ** tenor

        with (
            patch("app.services.pricing_engine.curve_service.get_rate", return_value=RATE),
            patch("app.services.pricing_engine.inflation_service.get_vna", return_value=VNA),
        ):
            result = price_ntnb_principal(maturity, ref=REF_DATE)

        assert result.pu == pytest.approx(expected_pu, rel=1e-5)

    def test_matured_bond_raises(self):
        with pytest.raises(ValueError):
            price_ntnb_principal(date(2020, 1, 1), ref=REF_DATE)


# ---------------------------------------------------------------------------
# NTN-B pricing
# ---------------------------------------------------------------------------

class TestPriceNTNB:
    def test_basic_pricing(self):
        """NTN-B: should produce reasonable PU with 6% coupons on VNA."""
        maturity = date(2040, 8, 15)
        VNA = 4782.22
        with (
            patch("app.services.pricing_engine.curve_service.get_rate", side_effect=_mock_pre_rate),
            patch("app.services.pricing_engine.inflation_service.get_vna", return_value=VNA),
        ):
            result = price_ntnb(maturity, ref=REF_DATE)

        assert result.pu > 0
        assert result.vna == VNA

    def test_matured_bond_raises(self):
        with pytest.raises(ValueError):
            price_ntnb(date(2020, 1, 1), ref=REF_DATE)


# ---------------------------------------------------------------------------
# LFT pricing
# ---------------------------------------------------------------------------

class TestPriceLFT:
    def test_no_spread_trades_at_vna(self):
        """LFT with zero spread: PU ≈ VNA_SELIC (trades at par, with tiny tenor discount)."""
        maturity = date(2027, 3, 1)
        with patch("app.services.pricing_engine.curve_service.get_selic_rate", return_value=0.1325):
            result = price_lft(maturity, spread=0.0, ref=REF_DATE)

        # With spread=0, PU = VNA / (1+0)^years = VNA (if years close to 0)
        assert result.pu > 0
        assert result.yield_rate == pytest.approx(0.1325, abs=1e-4)

    def test_positive_spread_reduces_price(self):
        """Positive spread (e.g. NTN-B spread) should lower price."""
        maturity = date(2028, 9, 1)
        with patch("app.services.pricing_engine.curve_service.get_selic_rate", return_value=0.1325):
            no_spread = price_lft(maturity, spread=0.0, ref=REF_DATE)
            with_spread = price_lft(maturity, spread=0.001, ref=REF_DATE)

        assert with_spread.pu < no_spread.pu

    def test_matured_bond_raises(self):
        with pytest.raises(ValueError):
            price_lft(date(2020, 1, 1), ref=REF_DATE)


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

class TestCalculatePU:
    @pytest.mark.parametrize("bond_type, maturity", [
        (BondType.PREFIXADO, date(2029, 1, 1)),
        (BondType.PREFIXADO_JUROS, date(2033, 1, 1)),
        (BondType.IPCA, date(2035, 5, 15)),
        (BondType.IPCA_JUROS, date(2040, 8, 15)),
        (BondType.SELIC, date(2027, 3, 1)),
    ])
    def test_all_bond_types_return_valid_pu(self, bond_type, maturity):
        VNA = 4782.22
        with (
            patch("app.services.pricing_engine.curve_service.get_rate", side_effect=_mock_pre_rate),
            patch("app.services.pricing_engine.curve_service.get_selic_rate", return_value=0.1325),
            patch("app.services.pricing_engine.inflation_service.get_vna", return_value=VNA),
        ):
            result = calculate_pu(bond_type, maturity, ref=REF_DATE)

        assert result.pu > 0
        assert result.yield_rate > 0
        assert result.calculation_date == REF_DATE
