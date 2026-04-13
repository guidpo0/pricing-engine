from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class MarketQuoteResponse(BaseModel):
    ticker: str = Field(..., description="The asset ticker (e.g. PETR4, MXRF11)")
    unit_price: float = Field(..., description="Current unit price")
    currency: str = Field(default="BRL", description="Currency of the price")
    updated_at: datetime = Field(..., description="Timestamp of the quote data")
    quantity: Optional[float] = Field(default=None, description="Quantity if portfolio valuation was requested")
    position_value: Optional[float] = Field(default=None, description="Total position value (unit_price * quantity)")

class TrackedTickersResponse(BaseModel):
    br_tickers: list[str] = Field(default_factory=list, description="List of all BRAPI tickers currently tracked")
    us_tickers: list[str] = Field(default_factory=list, description="List of all US tickers currently tracked")
    crypto_slugs: list[str] = Field(default_factory=list, description="List of all Crypto slugs currently tracked")
    currencies: list[str] = Field(default_factory=list, description="List of all Currency pairs currently tracked")

class CurrencyHistoryItem(BaseModel):
    date: datetime = Field(..., description="Date of the quote")
    price: float = Field(..., description="Exchange rate on this date")
    change: Optional[float] = Field(default=None, description="Percentage change from previous day")

class CurrencyHistoryResponse(BaseModel):
    currency_pair: str = Field(..., description="Currency pair (e.g. USD-BRL)")
    history: list[CurrencyHistoryItem] = Field(default_factory=list, description="Historical quotes")
    variation_30_days: Optional[float] = Field(default=None, description="Total variation percentage over the period")

