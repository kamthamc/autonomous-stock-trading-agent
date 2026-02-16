from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel


# ──────────────────────────────────────────────
# Trading DB Models  (trading_agent.db)
# Core business data: signals, trades, market trends
# ──────────────────────────────────────────────

class Signal(SQLModel, table=True):
    __tablename__ = "signals"
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=datetime.now)
    symbol: str
    decision: str  # BUY_STOCK, BUY_CALL, BUY_PUT, SELL, HOLD
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
    action: str  # BUY, SELL
    quantity: float
    price: float
    status: str  # FILLED, REJECTED, PENDING, FAILED
    order_id: Optional[str] = None
    region: str = "US"
    strategy: str = "AI_Momentum"
    pnl: Optional[float] = 0.0

class MarketTrend(SQLModel, table=True):
    __tablename__ = "market_trends"
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=datetime.now)
    tickers: str  # JSON string of tickers found
    source: str = "news_scan"


# ──────────────────────────────────────────────
# Activity DB Models  (activity.db)
# High-volume operational data: risk reviews, agent events, API stats
# ──────────────────────────────────────────────

class RiskReview(SQLModel, table=True):
    """Stores devil's advocate (AI risk reviewer) decisions."""
    __tablename__ = "risk_reviews"
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=datetime.now)
    symbol: str
    original_decision: str   # The AI signal's decision (e.g. BUY_CALL)
    original_confidence: float
    review_decision: str     # APPROVE or REJECT
    review_reasoning: str    # The risk reviewer's explanation
    was_overridden: bool = False  # True if rejected but trade proceeded anyway (paper mode)

class AgentEvent(SQLModel, table=True):
    """Stores notable agent lifecycle events (cycle starts, errors, circuit breakers)."""
    __tablename__ = "agent_events"
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=datetime.now)
    event_type: str    # cycle_start, error, circuit_breaker, broker_auth, etc.
    symbol: Optional[str] = None
    region: Optional[str] = None
    details: Optional[str] = None  # JSON or free text

class APICallLog(SQLModel, table=True):
    """Tracks every external API call for cost, latency, and usage analysis."""
    __tablename__ = "api_call_logs"
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=datetime.now)
    
    # What was called
    source: str            # "ai_analyze", "ai_review", "news", "market_data", "broker_quote", "broker_order"
    provider: str          # "azure_openai", "gemini", "yfinance", "robinhood", "zerodha", etc.
    endpoint: Optional[str] = None  # Specific API endpoint or model name
    
    # Context
    symbol: Optional[str] = None
    region: Optional[str] = None
    
    # Performance
    latency_ms: int = 0             # Call duration in milliseconds
    http_status: Optional[int] = None
    success: bool = True
    error_message: Optional[str] = None
    
    # Token usage (AI calls only)
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    
    # Cost estimate (optional, AI calls)
    estimated_cost_usd: Optional[float] = None

