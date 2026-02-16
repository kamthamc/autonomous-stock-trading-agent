# 📚 API Reference

Key data models, functions, and interfaces used throughout the agent.

---

## Database Models (`database/models.py`)

All models use [SQLModel](https://sqlmodel.tiangolo.com/) (Pydantic + SQLAlchemy).

### Signal

Stored in `trading_agent.db → signals`.

```python
class Signal(SQLModel, table=True):
    id: int                          # Auto-incrementing primary key
    timestamp: datetime              # When the signal was generated
    symbol: str                      # Ticker symbol (e.g., "AAPL")
    decision: str                    # "BUY_CALL" | "BUY_PUT" | "BUY_STOCK" | "SELL" | "HOLD"
    confidence: float                # 0.0 to 1.0
    reasoning: str                   # AI's explanation
    recommended_option: str | None   # e.g., "AAPL 190 CALL EXP 2026-03-20"
    stop_loss: float | None          # Suggested stop loss price
    take_profit: float | None        # Suggested take profit price
```

### Trade

Stored in `trading_agent.db → trades`.

```python
class Trade(SQLModel, table=True):
    id: int
    timestamp: datetime
    symbol: str
    action: str                      # "BUY", "SELL", etc.
    quantity: float
    price: float
    order_type: str | None           # "market", "limit"
    broker: str | None               # "robinhood", "zerodha", "icici"
    region: str | None               # "us" or "india"
    pnl: float | None                # Realized P&L (if closed)
```

### RiskReview

Stored in `activity_YYYY_MM.db → risk_reviews`.

```python
class RiskReview(SQLModel, table=True):
    id: int
    timestamp: datetime
    symbol: str
    original_decision: str           # The AI's proposed trade
    original_confidence: float
    review_decision: str             # "APPROVE" or "REJECT"
    review_reasoning: str            # Risk manager's explanation
    was_overridden: bool             # True if review changed the outcome
```

### APICallLog

Stored in `activity_YYYY_MM.db → api_call_logs`.

```python
class APICallLog(SQLModel, table=True):
    id: int
    timestamp: datetime
    
    # What was called
    source: str                      # "ai_analyze", "ai_review", "ai_analyze_cached", etc.
    provider: str                    # "azure_openai", "gemini", "cache"
    endpoint: str | None             # Model name or "cache"
    
    # Context
    symbol: str | None
    region: str | None               # "us" or "india"
    
    # Performance
    latency_ms: int                  # Call duration in milliseconds (0 for cached)
    http_status: int | None
    success: bool
    error_message: str | None
    
    # Token usage (AI calls only)
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    
    # Cost estimate
    estimated_cost_usd: float | None
```

### AgentEvent

Stored in `activity_YYYY_MM.db → agent_events`.

```python
class AgentEvent(SQLModel, table=True):
    id: int
    timestamp: datetime
    event_type: str                  # "cycle_start", "signal_generated", etc.
    details: str | None              # JSON-encoded additional data
```

---

## Key Functions

### Database Operations (`database/db.py`)

| Function | Description | Returns |
|----------|-------------|---------|
| `save_signal(signal)` | Persists a trading signal | `Signal` |
| `save_trade(trade)` | Persists an executed trade | `Trade` |
| `save_risk_review(review)` | Saves a risk review to activity DB | `RiskReview` |
| `save_api_call_log(log)` | Saves an API call log entry | `APICallLog` |
| `get_api_call_stats(limit, source, provider, since, until)` | Queries API logs with filters | `List[APICallLog]` |

All functions are `async` and use SQLModel async sessions.

### Strategy Functions

#### `ai.py`

| Function | Description |
|----------|-------------|
| `AIAnalyzer.analyze(symbol, price, tech, news, options, earnings)` | Generates an `AISignal` using LLM (cached) |
| `AIAnalyzer.review_trade(symbol, signal, price, tech, news)` | Returns `RiskReviewResult` (cached) |

#### `market_hours.py`

| Function | Description | Returns |
|----------|-------------|---------|
| `is_market_open(symbol)` | Checks if the market for this symbol is currently open | `bool` |
| `is_in_analysis_window(symbol)` | Checks if we're in the pre-market analysis window | `bool` |
| `filter_tickers_by_market_hours(tickers)` | Returns only tickers whose markets are open/in analysis window | `List[str]` |
| `get_session_info(symbol, date)` | Detailed session info (open/close times, holidays, early close) | `dict` |
| `get_market_status()` | Full status dict for US and India (used by dashboard) | `dict` |

#### `earnings.py`

| Function | Description | Returns |
|----------|-------------|---------|
| `get_earnings_info(symbol)` | Fetches next earnings date (cached 6h) | `EarningsInfo` |
| `get_bulk_earnings(symbols)` | Batch earnings lookup | `List[EarningsInfo]` |
| `get_earnings_warnings(symbols)` | Only symbols with earnings within 7 days | `List[EarningsInfo]` |

### Trader Functions

#### `router.py`

| Function | Description | Returns |
|----------|-------------|---------|
| `BrokerRouter.detect_region(symbol)` | Determines market region from ticker | `"us"` or `"india"` |
| `BrokerRouter.get_broker(symbol)` | Returns the appropriate broker instance | `BaseBroker` |
| `BrokerRouter.execute_trade(symbol, action, quantity, price)` | Routes and executes a trade | `Trade` |

---

## Pydantic Models (Non-DB)

### AISignal

```python
class AISignal(BaseModel):
    decision: Literal["BUY_CALL", "BUY_PUT", "BUY_STOCK", "SELL", "HOLD"]
    confidence: float                # 0.0 to 1.0
    reasoning: str
    recommended_option: str | None
    stop_loss_suggestion: float | None
    take_profit_suggestion: float | None
```

### RiskReviewResult

```python
class RiskReviewResult(BaseModel):
    is_approved: bool
    decision: str                    # "APPROVE" or "REJECT"
    reasoning: str
```

### EarningsInfo

```python
class EarningsInfo(BaseModel):
    symbol: str
    earnings_date: str | None        # ISO date string
    days_until_earnings: int | None
    eps_estimate: float | None
    revenue_estimate: float | None
    is_within_warning_window: bool   # True if earnings < 7 days away
```

### LLMCache

```python
class LLMCache:
    def __init__(self, ttl_seconds=900, max_entries=200)
    def get(self, prompt: str) -> Optional[Any]
    def put(self, prompt: str, value: Any) -> None
    
    @property
    def stats(self) -> dict          # {"hits", "misses", "hit_rate", "entries"}
```
