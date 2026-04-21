"""
Pydantic models for LCI (Letra de Crédito Imobiliário) and
LCA (Letra de Crédito do Agronegócio) pricing.
"""
from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, Field, model_validator


class LCILCAInstrumentType(str, Enum):
    LCI = "LCI"
    LCA = "LCA"


class LCILCAIndexType(str, Enum):
    """Supported LCI/LCA index types."""
    CDI = "CDI"
    PREFIXADO = "PREFIXADO"
    IPCA = "IPCA"


class LCILCAValueRequest(BaseModel):
    """Request body for POST /lci-lca/value."""

    instrument_type: LCILCAInstrumentType = Field(
        ...,
        description="Instrument type: LCI or LCA",
    )
    principal: float = Field(
        ...,
        gt=0,
        description="Initial invested amount in BRL",
        examples=[15000.0],
    )
    rate: float = Field(
        ...,
        gt=0,
        description=(
            "Yield rate: for CDI, the multiplier (e.g. 0.95 = 95% CDI); "
            "for PREFIXADO, the annual rate (e.g. 0.12 = 12% p.a.); "
            "for IPCA, the real spread rate (e.g. 0.05 = IPCA + 5%)"
        ),
        examples=[0.95],
    )
    index_type: LCILCAIndexType = Field(
        ...,
        description="Index type: CDI, PREFIXADO or IPCA",
    )
    purchase_date: date = Field(
        ...,
        description="Date the instrument was purchased (YYYY-MM-DD)",
        examples=["2025-01-10"],
    )
    maturity_date: date = Field(
        ...,
        description="Maturity date (YYYY-MM-DD)",
        examples=["2027-01-10"],
    )
    grace_period_days: int = Field(
        ...,
        ge=0,
        description="Grace period (carência) in days",
        examples=[90],
    )
    calculation_date: date | None = Field(
        None,
        description="Optional calculation date (defaults to today). Use for historical valuations.",
    )

    @model_validator(mode="after")
    def validate_dates(self) -> "LCILCAValueRequest":
        effective_date = self.calculation_date or date.today()
        if self.purchase_date >= self.maturity_date:
            raise ValueError("maturity_date must be after purchase_date")
        if self.purchase_date > effective_date:
            raise ValueError("purchase_date cannot be in the future")
        return self


class LCILCAValueResponse(BaseModel):
    """Response for POST /lci-lca/value."""

    instrument_type: LCILCAInstrumentType
    current_value: float = Field(..., description="Current mark-to-model value in BRL (tax exempt)")
    yield_amount: float = Field(..., description="Earnings so far in BRL (tax exempt)")
    yield_percentage: float = Field(..., description="Return as a percentage")
    redeemable: bool = Field(..., description="True if the grace period has passed")
    calculation_date: date
