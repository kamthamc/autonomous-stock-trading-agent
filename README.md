# Autonomous Stock Trading Agent 🤖📈

> [!CAUTION]
> **DISCLAIMER: EXPERIMENTAL SOFTWARE**
> This project is for **EDUCATIONAL AND RESEARCH PURPOSES ONLY**. 
> - It is **NOT** financial advice.
> - The software is **untested** in live market conditions.
> - Using this software for live trading carries significant risk of financial loss.
> - The authors and contributors assume **NO RESPONSIBILITY** for any trades executed or money lost.
> - **ALWAYS** use Paper Trading mode (`TRADING_MODE=paper`) for testing.
> - Never hardcode API keys or secrets; always use the `.env` file.

An advanced, AI-powered autonomous trading agent capable of analyzing market data, news, technical indicators, and option chains to execute trades on **US and Indian stock markets**.

<p align="center">
  <img src="docs/architecture.svg" alt="Architecture Diagram" width="100%"/>
</p>

---

## ✨ Features

### AI-Driven Analysis
- **LLM-Powered Signals** — Uses OpenAI, Azure OpenAI, or Google Gemini to analyze technicals + news + options and generate BUY/SELL/HOLD decisions
- **Devil's Advocate Risk Review** — A secondary AI agent critiques every trade before execution, reducing hallucination-driven trades
- **Earnings Awareness** — Automatically detects upcoming quarterly results and warns the AI to factor in volatility risk
- **LLM Response Cache** — In-memory TTL cache (15 min) keyed by prompt hash; avoids redundant API calls when data hasn't changed
- **Cross-Impact Analysis** — Factors in peer earnings, competitor moves, and macro/political sensitivities (e.g., tariffs, AI regulation)

### Multi-Market Support
- **US Market**: Robinhood (via `robin_stocks`)
- **India Market**: Zerodha (Kite Connect) and ICICI Direct (Breeze)
- **Smart Broker Routing** — Automatic region detection (`.NS`/`.BO` → India, else US) with preferred + fallback broker configuration
- **Per-Region Capital Limits** — Separate capital allocation for US (USD) and India (INR)

### Market Intelligence
- **Technical Analysis** — RSI, MACD, Bollinger Bands, SMA-50/200, Support/Resistance levels
- **Options Chain Analysis** — Volume, Open Interest, Implied Volatility; recommends specific contracts
- **News Sentiment** — Fetches and caches news with 10-minute TTL
- **Market Scanner** — AI-powered trend detection for identifying new opportunities
- **Market Hours & Holidays** — Uses `exchange_calendars` for NYSE/BSE session detection, holiday handling, and early close alerts

### Data & Observability
- **Dual Database Architecture**:
  - `trading_agent.db` — Core data (signals, trades, market trends)
  - `activity_YYYY_MM.db` — High-volume operational data with monthly rotation (risk reviews, API call logs, agent events)
- **API Call Tracking** — Every LLM/broker/data call is logged with latency, token usage, and success status
- **Real-Time Dashboard** — High-performance SPA with auto-refresh, showing signals, trades, PnL, risk reviews, API stats, earnings calendar, and market status

---

## 🏗️ Architecture

```
autonomous-stock-trading-agent/
├── main.py                  # Entry point — async event loop, ticker routing, market gating
├── agent_config.py          # Pydantic settings — env vars, watchlists, capital limits
├── dashboard_api.py         # FastAPI backend for dashboard
├── dashboard/               # SPA frontend (HTML/CSS/JS)
├── telemetry.py             # OpenTelemetry instrumentation
├── setup.sh                 # One-command project setup
│
├── strategy/                # Analysis & decision engine
│   ├── engine.py            #   Orchestrator — fetches data, runs AI, manages trade flow
│   ├── ai.py                #   LLM analysis + risk review + response cache
│   ├── technical.py         #   Technical indicators (RSI, MACD, Bollinger, SMA)
│   ├── news.py              #   News fetching & caching (GoogleNews)
│   ├── risk.py              #   Position sizing, capital allocation, risk rules
│   ├── scanner.py           #   AI market trend scanner
│   ├── market_hours.py      #   Market open/close, holidays, early close detection
│   └── earnings.py          #   Quarterly earnings calendar & warnings
│
├── trader/                  # Broker integrations & market data
│   ├── router.py            #   Region-aware broker routing (US/India)
│   ├── market_data.py       #   Price, history, options via yfinance
│   ├── base.py              #   Abstract broker interface
│   ├── us/
│   │   └── robinhood.py     #   Robinhood integration (robin_stocks)
│   └── india/
│       ├── zerodha.py       #   Zerodha/Kite Connect integration
│       └── icici.py         #   ICICI Direct/Breeze integration
│
├── database/                # Persistence layer
│   ├── models.py            #   SQLModel definitions (Signal, Trade, RiskReview, APICallLog)
│   └── db.py                #   Async DB operations, monthly activity rotation
│
├── docs/                    # Documentation
│   ├── architecture.svg     #   System architecture diagram
│   └── *.md                 #   Browsable documentation
│
├── requirements.txt         # Python dependencies (grouped & annotated)
└── .env.example             # Environment variable template
```

---

## 🚀 Quick Start

### Prerequisites
- **Python 3.11+**
- API keys for at least one AI provider (OpenAI, Azure OpenAI, or Google Gemini)
- Broker credentials (optional — paper mode works without them)

### 1. Automated Setup
```bash
git clone <repository_url>
cd autonomous-stock-trading-agent
./setup.sh
```

### 2. Manual Setup
```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys
```

### 3. Configure Watchlists
Edit `.env` to set your per-region watchlists:
```env
# US stocks/ETFs
US_WATCHLIST=AAPL,TSLA,SPY,QQQ,MSFT

# Indian stocks (.NS suffix auto-added if missing)
INDIA_WATCHLIST=RELIANCE,TCS,INFY,HDFCBANK
```

### 4. Run
```bash
# Start the trading agent
python main.py

# In another terminal — launch the dashboard
# In another terminal — launch the dashboard backend (access at http://localhost:8050)
python dashboard_api.py
```

---

## ⚙️ Configuration

All configuration is via environment variables (`.env` file). See [`.env.example`](.env.example) for the full list.

### Key Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `TRADING_MODE` | `paper` (simulated) or `live` (real money) | `paper` |
| `AI_PROVIDER` | `azure_openai`, `openai`, or `gemini` | `azure_openai` |
| `US_WATCHLIST` | Comma-separated US tickers | `AAPL,TSLA,SPY` |
| `INDIA_WATCHLIST` | Comma-separated Indian tickers | `RELIANCE.NS,TCS.NS` |
| `US_MAX_CAPITAL` | Max US capital (USD) | `500.00` |
| `INDIA_MAX_CAPITAL` | Max India capital (INR) | `12000.00` |
| `US_PREFERRED_BROKER` | US broker to use | `robinhood` |
| `INDIA_PREFERRED_BROKER` | India broker to use | `zerodha` |
| `INDIA_FALLBACK_BROKER` | India fallback broker | `icici` |

---

## 📊 Dashboard

The FastAPI + Vanilla JS dashboard provides real-time visibility into the agent's activity:

| Section | Description |
|---------|-------------|
| **🧠 AI Strategy Signals** | All generated trade signals with decisions, confidence, and AI reasoning |
| **📅 Earnings Calendar** | Upcoming quarterly results with ⚠️ warnings for stocks reporting within 7 days |
| **😈 Devil's Advocate Reviews** | Risk manager decisions (Approve/Reject) with color-coded status |
| **💰 Recent Trades** | Executed trades with PnL tracking |
| **📈 Market Scanner Trends** | AI-detected market-wide trends |
| **📊 API Usage & Performance** | Call counts, latency, token usage, success rates with time-range filtering |
| **📝 Live Agent Logs** | JSON-structured logs from the agent process |
| **🌐 Market Status** | Sidebar indicators showing US/India market open/closed/holiday/early close |

---

## ⚠️ Broker Integration & Safety

### Official APIs ✅
| Broker | Market | API | Notes |
|--------|--------|-----|-------|
| **Zerodha** | India | Kite Connect | Official, stable. Recommended for India. |
| **ICICI Direct** | India | Breeze | Official, stable. Good fallback option. |

### Unofficial APIs ⚠️
| Broker | Market | API | Notes |
|--------|--------|-----|-------|
| **Robinhood** | US | robin_stocks | Unofficial wrapper. May flag accounts. Use for paper trading only. |

---

## 🛡️ Safety Mechanisms

1. **Paper Trading Mode** — Default mode simulates all trades without real money
2. **Funds Check** — Prevents trading if capital < $100
3. **AI Devil's Advocate** — Secondary AI reviews each trade for flaws before execution
4. **Regional Market Hours** — Skips tickers whose markets are closed/on holiday (enforced in live mode)
5. **Earnings Warning** — AI factors in earnings volatility for stocks reporting within 7 days

6. **Capital Limits** — Per-region max capital prevents overexposure
7. **Monthly DB Rotation** — Activity data is split into monthly databases to prevent unbounded growth

For full details, see [**Security & Safety**](docs/security.md).

---

## 🔧 Development

### Running Tests
```bash
python -m pytest test_agent.py test_agent_di.py -v
```

### Project Dependencies
Dependencies are organized into groups in `requirements.txt`:
- **Core** — async runtime, data models, config
- **AI / LLM** — OpenAI, Gemini SDKs
- **Market Data** — yfinance, exchange_calendars, pandas_ta
- **Broker SDKs** — robin_stocks, kiteconnect, breeze-connect
- **Dashboard** — FastAPI, Uvicorn, Vanilla JS
- **Observability** — OpenTelemetry

---

## 🤝 Contributing

Contributions are welcome! Please open an issue or PR for major changes.

## 📄 License

MIT License
