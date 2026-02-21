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
    option_strike: Optional[float] = None
    option_expiry: Optional[str] = None
    target_buy_price: Optional[float] = None
    target_sell_price: Optional[float] = None
    stop_loss: Optional[float] = None

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
    estimated_fees: Optional[float] = 0.0    # Broker + exchange fees
    net_pnl: Optional[float] = 0.0           # pnl minus fees
    fee_currency: str = "USD"                # USD or INR
    
    # Advanced Order & Option Support
    is_manual: bool = False
    order_type: str = "MARKET"               # MARKET, LIMIT, STOP
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    asset_type: str = "STOCK"                # STOCK, CALL, PUT
    option_strike: Optional[float] = None
    option_expiry: Optional[str] = None

class MarketTrend(SQLModel, table=True):
    __tablename__ = "market_trends"
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=datetime.now)
    tickers: str  # JSON string of tickers found
    source: str = "news_scan"

class AccountEquitySnapshot(SQLModel, table=True):
    """Tracks true account equity (cash + holdings) over time."""
    __tablename__ = "account_equity_snapshots"
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=datetime.now)
    region: str           # US or IN
    cash: float
    holdings_value: float
    total_equity: float

class WatchedTicker(SQLModel, table=True):
    """Tickers discovered by the scanner that the user wants to watch."""
    __tablename__ = "watched_tickers"
    id: Optional[int] = Field(default=None, primary_key=True)
    added_at: datetime = Field(default_factory=datetime.now)
    symbol: str
    region: str
    source_trend: Optional[str] = None
    notes: Optional[str] = None


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


class AppConfig(SQLModel, table=True):
    """
    Stores dynamic application settings that can be changed via Dashboard.
    Key-Value pair storage.
    """
    __tablename__ = "app_config"
    key: str = Field(primary_key=True)
    value: str
    description: Optional[str] = None
    updated_at: datetime = Field(default_factory=datetime.now)


class AIDecisionLog(SQLModel, table=True):
    """
    Captures every AI analysis decision with full context.
    Makes it easy to trace WHY the AI made a specific call.
    """
    __tablename__ = "ai_decision_logs"
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=datetime.now)
    symbol: str
    region: str = "US"

    # What the AI decided
    decision: str            # BUY_STOCK, BUY_AGGRESSIVE, SELL, PARTIAL_SELL, HOLD, etc.
    confidence: float
    reasoning: str           # Full AI reasoning text

    # Context that was fed to the AI
    current_price: Optional[float] = None
    technical_summary: Optional[str] = None   # JSON: RSI, MACD, Bollinger, etc.
    news_headlines: Optional[str] = None      # JSON: list of headlines used
    macro_factors: Optional[str] = None       # JSON: geopolitics, earnings, sector moves
    cross_impact: Optional[str] = None        # JSON: peer moves, correlations

    # Stop/target suggestions
    stop_loss_suggestion: Optional[float] = None
    target_sell_price: Optional[float] = None
    target_buy_price: Optional[float] = None
    min_upside_target_pct: Optional[float] = None
    option_strike: Optional[float] = None
    option_expiry: Optional[str] = None

    # What happened after
    was_executed: bool = False
    was_cache_hit: bool = False              # True if AI response came from cache
    risk_review_result: Optional[str] = None  # APPROVE / REJECT
    execution_price: Optional[float] = None


class NewsFingerprint(SQLModel, table=True):
    """
    Tracks news headlines already processed to avoid re-acting on stale news.
    The fingerprint is a hash of (symbol + headline_text).
    """
    __tablename__ = "news_fingerprints"
    id: Optional[int] = Field(default=None, primary_key=True)
    fingerprint: str = Field(index=True)   # SHA-256 of symbol+headline
    symbol: str
    headline: str
    source: Optional[str] = None
    first_seen: datetime = Field(default_factory=datetime.now)
    acted_on: bool = False         # True if a trade was triggered by this news


