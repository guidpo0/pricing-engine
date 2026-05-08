"""
Pydantic models for bond types, requests and responses.
"""
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class BondType(str, Enum):
    """Supported Tesouro Direto bond types."""
    PREFIXADO = "PREFIXADO"            # LTN — Tesouro Prefixado
    PREFIXADO_JUROS = "PREFIXADO_JUROS"  # NTN-F — Tesouro Prefixado com juros semestrais
    IPCA = "IPCA"                      # NTN-B Principal — Tesouro IPCA+
    IPCA_JUROS = "IPCA_JUROS"          # NTN-B — Tesouro IPCA+ com juros semestrais
    SELIC = "SELIC"                    # LFT — Tesouro Selic


class BondPriceRequest(BaseModel):
    """Query parameters for GET /bonds/price."""
    type: BondType = Field(..., description="Bond type identifier")
    maturity_date: date = Field(..., description="Bond maturity date (YYYY-MM-DD)")
    spread: float = Field(
        default=0.0,
        ge=-0.05,
        le=0.05,
        description="Optional spread over benchmark rate (decimal, e.g. 0.001 = 10bps)",
    )

    @model_validator(mode="after")
    def maturity_must_be_future(self) -> "BondPriceRequest":
        if self.maturity_date <= date.today():
            raise ValueError("maturity_date must be in the future")
        return self


class BondPriceResponse(BaseModel):
    """Response for GET /bonds/price."""
    bond_type: BondType
    maturity_date: date
    pu: float = Field(..., description="Preço Unitário (mark-to-market price)")
    yield_rate: float = Field(..., description="Benchmark rate used in calculation")
    vna: Optional[float] = Field(None, description="VNA used (IPCA/SELIC bonds only)")
    calculation_date: date


class PortfolioValueRequest(BaseModel):
    """Request body for POST /portfolio/value."""
    bond_type: BondType
    maturity_date: date
    quantity: float = Field(..., gt=0, description="Number of bond units held")
    spread: float = Field(
        default=0.0,
        ge=-0.05,
        le=0.05,
        description="Optional spread over benchmark rate",
    )
    calculation_date: date | None = Field(
        None,
        description="Optional calculation date (defaults to today). Use for historical valuations.",
    )

    @model_validator(mode="after")
    def maturity_must_be_future(self) -> "PortfolioValueRequest":
        ref = self.calculation_date or date.today()
        if self.maturity_date <= ref:
            raise ValueError("maturity_date must be in the future")
        return self


class PortfolioValueResponse(BaseModel):
    """Response for POST /portfolio/value."""
    bond_type: BondType
    maturity_date: date
    pu: float
    quantity: float
    position_value: float
    yield_rate: float
    vna: Optional[float] = None
    calculation_date: date


class ErrorResponse(BaseModel):
    """Structured error response."""
    error: str
    detail: str
    code: str
