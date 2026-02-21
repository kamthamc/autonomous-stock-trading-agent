# 🏗️ Architecture

## System Overview

The trading agent is an **async Python application** that runs in a continuous loop, analyzing stocks across US and Indian markets using AI, then executing trades through region-specific brokers.

<p align="center">
  <img src="architecture.svg" alt="Architecture Diagram" width="100%"/>
</p>

---

## Layers

### 1. Orchestrator — `main.py`

The entry point runs an **async event loop** with the following cycle:

```
┌─────────────┐     ┌───────────────┐     ┌──────────────┐     ┌───────────┐
│ Market Hours │ ──▸ │ Fetch Tickers │ ──▸ │ Strategy     │ ──▸ │ Execute   │
│ Gating      │     │ by Region     │     │ Engine       │     │ via Broker│
└─────────────┘     └───────────────┘     └──────────────┘     └───────────┘
```

**Key behaviors:**
- Filters tickers by region-specific market hours (skips closed markets in live mode)
- Routes each ticker to the strategy engine
- Runs the market scanner for trend detection
- Sleeps for a configurable interval between cycles

### 2. Strategy Layer — `strategy/`

The analysis pipeline for each ticker:

```
                    ┌──────────────┐
                    │ engine.py    │
                    └──────┬───────┘
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
    ┌────────────┐  ┌────────────┐  ┌────────────┐
    │ Market Data│  │ Tech Anal. │  │ News       │
    │ + Options  │  │ + Earnings │  │ Sentiment  │
    └─────┬──────┘  └─────┬──────┘  └─────┬──────┘
          └───────────────┼───────────────┘
                          ▼
                   ┌────────────┐
                   │  AI Signal │  ◀── LLM (OpenAI/Azure/Gemini)
                   │  (analyze) │      with 15-min Cache
                   └─────┬──────┘
                         ▼
                   ┌────────────┐
                   │ Risk Review│  ◀── Devil's Advocate LLM
                   │ (review)   │
                   └─────┬──────┘
                         ▼
                   ┌────────────┐
                   │ Execute    │  ──▸ Broker Router ──▸ Trade
                   └────────────┘
```

#### Components

| Module | Purpose | Key Feature |
|--------|---------|-------------|
| `engine.py` | Orchestrates the full analysis pipeline for one ticker | Concurrent data fetching with `asyncio.gather` |
| `ai.py` | LLM-based signal generation + risk review | SHA-256 prompt cache with 15-min TTL, 200 entries |
| `correlations.py` | Cross-impact analysis (peers, macro sensitivities) | Hardcoded + Dynamic sector-based discovery |
| `technical.py` | Computes RSI, MACD, Bollinger Bands, SMA-50/200 | Uses `pandas_ta` library |
| `news.py` | Fetches news via GoogleNews | 10-minute cache TTL |
| `risk.py` | Position sizing, capital limit enforcement | Kelly Criterion and ATR-based Volatility Sizing |
| `scanner.py` | AI-powered market trend detection | Identifies sector rotations and macro trends |
| `macro.py` | Global Market Sentiment Analyzer | Triggers Circuit Breaker (Halt Buys) if VIX > 25 or bearish regime |
| `fx.py` | Live Exchange Rate Normalizer | Fetches USD/INR rates from yfinance to normalize net worth |
| `market_hours.py` | Market open/close, holiday/early close detection | Uses `exchange_calendars` for NYSE/BSE |
| `earnings.py` | Upcoming quarterly results calendar | 6-hour cache, 7-day warning window |

### 3. Trader Layer — `trader/`

```
                   ┌──────────────┐
                   │ router.py    │ ◀── Region detection (.NS → India)
                   └──────┬───────┘
              ┌───────────┼───────────┐
              ▼                       ▼
       ┌────────────┐         ┌────────────┐
       │ US Broker   │         │ India Broker│
       │ (robinhood) │         │ (zerodha)   │
       └────────────┘         │ (icici)     │
                              └────────────┘
```

**Broker Router** detects the region from the ticker symbol:
- `.NS` or `.BO` suffix → India → routes to Zerodha or ICICI Direct
- Everything else → US → routes to Robinhood

**Fallback**: If the preferred India broker fails, automatically falls back to the configured secondary broker.

### 4. Database Layer — `database/`

The system uses a **dual-database** architecture stored in `__databases__/`:

| Database | File | Purpose | Rotation |
|----------|------|---------|----------|
| **Trading DB** | `trading_agent.db` | Core data — signals, trades, market trends | None (persistent) |
| **Activity DB** | `activity_YYYY_MM.db` | High-volume operational data — risk reviews, API call logs, agent events | Monthly |

**Why monthly rotation?** Activity data (especially API call logs) grows rapidly. Monthly rotation keeps each DB file manageable while preserving historical data.

### 5. Dashboard — `dashboard_api.py` + SPA

FastAPI-based backend serving a responsive Single Page Application (SPA):
- **Backend**: `dashboard_api.py` (FastAPI) provides REST endpoints for data, including **Manual Trade Execution** directly inserted into the database.
- **Frontend**: `dashboard/` (Vanilla JS, CSS3, HTML5) handles UI rendering.
- **Features**:
  - Unified Global Portfolio (USD converted via `fx.py`)
  - Deep-dive Manual Analysis & Execution
  - Advanced Quant Metrics (Sharpe, Profit Factor, Drawdown)
  - Automatic Dark/Light mode switching


---

## Data Flow

### Signal Generation Flow (Automated)
```
1. main.py selects ticker from regional watchlist
2. macro.py runs global sentiment check (circuit breaker)
3. engine.py runs current holdings check (trailing stops via ATR)
4. engine.py checks market hours (live mode only)
5. Concurrent fetch: price + history + options + news
6. correlations.py fetches cross-impact data (peers, macro)
7. technical.py computes indicators (including ATR for volatility)
8. ai.py constructs LLM prompt with all data
   └── Cache check → hit? return cached signal
   └── Cache miss → call LLM → cache result
9. ai.py risk review (Devil's Advocate)
10. risk.py validates position size using Kelly Criterion
11. router.py routes to appropriate broker
12. Trade executed (or simulated in paper mode)
13. All steps logged to DB + API call stats
```

### Manual Pre-Trade Analysis Flow
The user can request an on-demand analysis via the Dashboard SPA without triggering an automated trade:
```
1. User enters Symbol + Options specifics in the "Analysis & Trade" UI
2. Dashboard SPA POSTs to dashboard_api.py (/api/analyze)
3. dashboard_api.py instantiates MarketDataFetcher, NewsFetcher, TechAnalyzer, AIAnalyzer
4. Concurrent fetch of identical data used in the automated loop (prices, options, news)
5. AIAnalyzer computes a decision (decision, confidence, reasoning, target values, allocations)
6. Results returned synchronously to the Dashboard UI
7. User reviews the verdict & manually submits a trade if desired
8. dashboard_api.py inserts the manual trade directly into the Trading DB
```

### LLM Cache Strategy
```
Prompt = f(symbol, price, tech_indicators, news, options, earnings)
         ↓
Cache Key = SHA-256(prompt_text)
         ↓
   ┌─── Hit (< 15 min old) ──▸ Return cached AISignal (0ms, no tokens)
   │
   └─── Miss ──▸ Call LLM ──▸ Parse ──▸ Cache result ──▸ Return
```

The cache naturally invalidates when any input data changes (new price, new news article, indicator shift), since the prompt text — and therefore the hash — will differ.

---

## External Dependencies

| Service | Used By | Purpose |
|---------|---------|---------|
| OpenAI / Azure OpenAI | `ai.py` | Trade signal generation + risk review |
| Google Gemini | `ai.py` | Alternative LLM provider |
| yfinance | `market_data.py`, `earnings.py` | Price data, history, options chains, earnings dates |
| GoogleNews | `news.py` | Real-time news fetching |
| exchange_calendars | `market_hours.py` | NYSE/BSE session schedules, holidays, early closes |
| Robinhood (robin_stocks) | `us/robinhood.py` | US broker — unofficial API |
| Zerodha (kiteconnect) | `india/zerodha.py` | India broker — official API |
| ICICI Direct (breeze) | `india/icici.py` | India broker — official API |
