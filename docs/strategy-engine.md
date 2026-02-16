# 🧠 Strategy Engine

The strategy engine is the core analysis pipeline that processes each ticker and decides whether to trade.

## Pipeline Flow

For each ticker in the watchlist, `engine.py` runs this pipeline:

```
1. Pre‐flight checks
   ├── Region detection (US or India)
   ├── Broker availability check
   └── Market hours validation (live mode)

2. Data acquisition (concurrent via asyncio.gather)
   ├── Current price snapshot
   ├── 1-year price history
   ├── Options chain
   └── Recent news articles

3. Analysis
   ├── Technical indicators
   ├── Earnings calendar lookup
   └── AI signal generation (with cache)

4. Risk review
   └── Devil's Advocate AI critique

5. Execution
   ├── Position sizing
   ├── Broker routing
   └── Trade execution (or paper simulation)
```

---

## AI Analysis (`ai.py`)

### Signal Generation

The `analyze()` method constructs a detailed prompt containing:
- **Current price**
- **Technical indicators** (RSI, MACD, Bollinger, SMA, support/resistance)
- **News summary** (top 5 recent articles)
- **Options chain** (top liquid calls and puts with greeks)
- **Earnings alert** (if within 7 days of quarterly results)

The LLM responds with a structured JSON decision:

```json
{
  "decision": "BUY_CALL",
  "confidence": 0.78,
  "reasoning": "Strong momentum with RSI at 55...",
  "recommended_option": "AAPL 190 CALL EXP 2026-03-20",
  "stop_loss_suggestion": 175.0,
  "take_profit_suggestion": 200.0
}
```

### Devil's Advocate Review

The `review_trade()` method acts as a **risk manager** that critiques the signal:
- Looks for conflicting indicators
- Checks for overextended conditions
- Validates the thesis against counter-arguments

Returns `APPROVE` or `REJECT` with reasoning.

### LLM Response Cache

To avoid redundant API calls, all LLM responses are cached in-memory:

| Property | Value |
|----------|-------|
| Cache key | SHA-256 hash of the full prompt text |
| TTL | 15 minutes |
| Max entries | 200 (LRU eviction) |
| Scope | Both `analyze()` and `review_trade()` share the same cache |

**Natural invalidation**: Since the prompt includes all input data (price, indicators, news), any change in the data produces a different hash → cache miss → fresh LLM call.

**Observability**: Cache hits are logged to the API call stats as `ai_analyze_cached` / `ai_review_cached` with `latency_ms=0`.

---

## Technical Analysis (`technical.py`)

Computes the following indicators from 1-year price history:

| Indicator | Period | Usage |
|-----------|--------|-------|
| RSI | 14 | Overbought (>70) / Oversold (<30) detection |
| MACD | 12/26/9 | Momentum and trend direction |
| Bollinger Bands | 20/2 | Volatility and mean reversion |
| SMA-50 | 50 | Short-term trend |
| SMA-200 | 200 | Long-term trend |
| Support/Resistance | Recent lows/highs | Price level analysis |

---

## Market Hours (`market_hours.py`)

Uses `exchange_calendars` for accurate session data:

| Exchange | Calendar | Timezone |
|----------|----------|----------|
| NYSE (US) | `XNYS` | America/New_York |
| BSE (India) | `XBOM` | Asia/Kolkata |

### Features
- **Holiday detection** — knows all market holidays (Presidents' Day, Diwali, etc.)
- **Early close detection** — identifies shortened sessions (e.g., Thanksgiving eve → close at 13:00)
- **Pre-market window** — configurable analysis window before official open
- **`get_market_status()`** — returns full status dict for both regions (used by dashboard sidebar)

---

## Earnings Calendar (`earnings.py`)

Fetches upcoming quarterly results dates via `yfinance`:

| Feature | Detail |
|---------|--------|
| Data source | `yfinance.Ticker.calendar` |
| Cache TTL | 6 hours |
| Warning window | 7 days before earnings |
| Data fields | Earnings date, EPS estimate, revenue estimate |

When earnings are within 7 days:
- Agent logs a `earnings_approaching` warning
- AI prompt includes an **Earnings Alert** section
- AI is instructed to prefer HOLD unless the setup is very strong (within 3 days)

---

## Risk Management (`risk.py`)

### Pre-Trade Checks
1. **Sufficient capital** — regional capital must exceed minimum threshold
2. **Position sizing** — based on `MAX_RISK_PER_TRADE` percentage
3. **Per-trade limits** — enforces `US_MAX_PER_TRADE` / `INDIA_MAX_PER_TRADE`

### Capital Allocation
Each region has independent capital tracking:
- US capital limit in USD
- India capital limit in INR
- No cross-region capital leakage

---

## News Intelligence (`news.py`)

| Feature | Detail |
|---------|--------|
| Source | GoogleNews library |
| Cache TTL | 10 minutes |
| Articles per query | Top 5 |
| Query format | `"{SYMBOL} stock news"` |

News is included in the AI prompt as a bullet list of headlines with sources.

---

## Market Scanner (`scanner.py`)

The scanner runs periodically to identify market-wide trends:
- Analyzes broad market indices
- Detects sector rotations
- Identifies macro themes (e.g., "tech rally", "flight to safety")
- Results stored in `trading_agent.db` and displayed on dashboard
