"""
Pydantic models for CDB (Certificado de Depósito Bancário) pricing.
"""
from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, Field, model_validator


class CDBIndexType(str, Enum):
    """Supported CDB index types."""
    CDI = "CDI"          # CDI indexed, rate = % of CDI (e.g. 1.10 = 110% CDI)
    PREFIXADO = "PREFIXADO"  # Fixed rate, rate = annual rate (e.g. 0.12 = 12% p.a.)
    IPCA = "IPCA"        # IPCA indexed, rate = real rate spread (e.g. 0.05 = IPCA + 5%)


class CDBValueRequest(BaseModel):
    """Request body for POST /cdb/value."""

    principal: float = Field(
        ...,
        gt=0,
        description="Initial invested amount in BRL",
        examples=[10000.0],
    )
    rate: float = Field(
        ...,
        gt=0,
        description=(
            "Yield rate: for CDI, the multiplier (e.g. 1.10 = 110% CDI); "
            "for PREFIXADO, the annual rate (e.g. 0.12 = 12% p.a.); "
            "for IPCA, the real spread rate (e.g. 0.05 = IPCA + 5%)"
        ),
        examples=[1.10],
    )
    index_type: CDBIndexType = Field(
        ...,
        description="Index type: CDI, PREFIXADO or IPCA",
    )
    purchase_date: date = Field(
        ...,
        description="Date the CDB was purchased (YYYY-MM-DD)",
        examples=["2024-06-01"],
    )
    maturity_date: date = Field(
        ...,
        description="CDB maturity date (YYYY-MM-DD)",
        examples=["2027-06-01"],
    )

    @model_validator(mode="after")
    def validate_dates(self) -> "CDBValueRequest":
        if self.purchase_date >= self.maturity_date:
            raise ValueError("maturity_date must be after purchase_date")
        if self.purchase_date > date.today():
            raise ValueError("purchase_date cannot be in the future")
        return self


class CDBValueResponse(BaseModel):
    """Response for POST /cdb/value."""

    index_type: CDBIndexType
    principal: float = Field(..., description="Original invested amount")
    rate: float = Field(..., description="Rate used in pricing")
    purchase_date: date
    maturity_date: date
    current_value: float = Field(..., description="Current mark-to-model value in BRL")
    yield_amount: float = Field(..., description="Gross earnings so far in BRL")
    yield_percentage: float = Field(..., description="Gross return as a percentage")
    is_matured: bool = Field(..., description="True if the CDB has already reached maturity")
    calculation_date: date
