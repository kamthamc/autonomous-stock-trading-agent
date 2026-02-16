from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel

class Signal(SQLModel, table=True):
    __tablename__ = "signals"
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=datetime.now)
    symbol: str
    decision: str  # BUY, SELL, HOLD
    confidence: float
    reasoning: str
    recommended_option: Optional[str] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None

class Trade(SQLModel, table=True):
    __tablename__ = "trades"
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=datetime.now)
    symbol: str
    action: str # BUY, SELL
    quantity: float
    price: float
    status: str # FILLED, REJECTED, PENDING
    order_id: Optional[str] = None
    strategy: str = "AI_Momentum"
    pnl: Optional[float] = 0.0

class MarketTrend(SQLModel, table=True):
    __tablename__ = "market_trends"
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=datetime.now)
    tickers: str # JSON string of tickers found
    source: str = "news_scan"
