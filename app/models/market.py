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

class BatchQuoteItem(BaseModel):
    ticker: str = Field(..., description="Asset ticker or crypto slug")
    market: str = Field(default="br", description="Market: 'br', 'us', or 'crypto'")

class BatchQuoteRequest(BaseModel):
    tickers: list[BatchQuoteItem] = Field(..., min_items=1, max_items=50)
    date: Optional[str] = Field(default=None, description="Optional date (YYYY-MM-DD) for historical quotes")

class BatchQuoteResult(BaseModel):
    ticker: str = Field(..., description="Asset ticker or crypto slug")
    unit_price: Optional[float] = Field(default=None, description="Current unit price, null if failed")
    market: str = Field(..., description="Market: 'br', 'us', or 'crypto'")
    updated_at: Optional[datetime] = Field(default=None, description="Timestamp of the quote data")
    error: Optional[str] = Field(default=None, description="Error message if quote failed")

class BatchQuoteResponse(BaseModel):
    quotes: list[BatchQuoteResult] = Field(default_factory=list)

