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
    tickers: list[str] = Field(..., description="List of all tickers currently tracked in the background database")

