# ⚙️ Configuration Guide

All configuration is managed through environment variables, loaded from a `.env` file at the project root.

## Setup

```bash
cp .env.example .env
# Edit .env with your credentials
```

## Environment Variables

### AI Provider

| Variable | Description | Required |
|----------|-------------|----------|
| `AI_PROVIDER` | LLM provider: `azure_openai`, `openai`, or `gemini` | Yes |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI API key | If Azure |
| `AZURE_OPENAI_ENDPOINT` | Azure endpoint URL | If Azure |
| `AZURE_OPENAI_API_VERSION` | Azure API version | If Azure |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | Azure model deployment name | If Azure |
| `OPENAI_API_KEY` | Standard OpenAI API key | If OpenAI |
| `GEMINI_API_KEY` | Google Gemini API key | If Gemini |

### Trading Mode

| Variable | Description | Default |
|----------|-------------|---------|
| `TRADING_MODE` | `paper` (simulated) or `live` (real money) | `paper` |

> ⚠️ **Always start with paper mode.** Switch to live only after thorough testing.

### Broker Credentials

#### US — Robinhood
| Variable | Description |
|----------|-------------|
| `RH_USERNAME` | Robinhood username |
| `RH_PASSWORD` | Robinhood password |
| `RH_MFA_CODE` | Base32 TOTP secret (not the 6-digit code) |

#### India — Zerodha
| Variable | Description |
|----------|-------------|
| `KITE_API_KEY` | Kite Connect API key |
| `KITE_ACCESS_TOKEN` | Kite access token |

#### India — ICICI Direct
| Variable | Description |
|----------|-------------|
| `ICICI_API_KEY` | Breeze API key |
| `ICICI_SECRET_KEY` | Breeze secret key |
| `ICICI_SESSION_TOKEN` | Breeze session token |

### Broker Preferences

| Variable | Description | Default |
|----------|-------------|---------|
| `US_PREFERRED_BROKER` | US broker to use | `robinhood` |
| `INDIA_PREFERRED_BROKER` | Primary India broker | `zerodha` |
| `INDIA_FALLBACK_BROKER` | Fallback India broker | `icici` |

### Per-Region Watchlists

| Variable | Description | Default |
|----------|-------------|---------|
| `US_WATCHLIST` | Comma-separated US tickers | `AAPL,TSLA,SPY,QQQ,MSFT` |
| `INDIA_WATCHLIST` | Comma-separated Indian tickers | `RELIANCE.NS,TCS.NS,INFY.NS` |

> **Note:** Indian tickers automatically get `.NS` suffix if not provided (e.g., `RELIANCE` → `RELIANCE.NS`).

### Capital Limits

| Variable | Description | Default |
|----------|-------------|---------|
| `US_MAX_CAPITAL` | Maximum total US capital (USD) | `500.00` |
| `US_MAX_PER_TRADE` | Max per-trade in US (USD) | 20% of `US_MAX_CAPITAL` |
| `INDIA_MAX_CAPITAL` | Maximum total India capital (INR) | `12000.00` |
| `INDIA_MAX_PER_TRADE` | Max per-trade in India (INR) | 20% of `INDIA_MAX_CAPITAL` |
| `MAX_CAPITAL` | Legacy global capital limit | `1000.00` |
| `MAX_RISK_PER_TRADE` | Max risk percentage per trade | `0.02` (2%) |

---

## Example `.env`

```env
# AI Provider
AI_PROVIDER=gemini
GEMINI_API_KEY=AI...

# Trading
TRADING_MODE=paper

# Watchlists
US_WATCHLIST=AAPL,TSLA,SPY,QQQ,MSFT,GOOGL
INDIA_WATCHLIST=RELIANCE,TCS,INFY,HDFCBANK

# Capital
US_MAX_CAPITAL=500.00
INDIA_MAX_CAPITAL=12000.00

# Broker (India)
INDIA_PREFERRED_BROKER=zerodha
KITE_API_KEY=your_key
KITE_ACCESS_TOKEN=your_token
```

---

## Watchlist Configuration

### Adding Tickers
Simply add comma-separated symbols to the appropriate env var:

```env
US_WATCHLIST=AAPL,TSLA,SPY,QQQ,MSFT,GOOGL,AMZN,NVDA
INDIA_WATCHLIST=RELIANCE,TCS,INFY,HDFCBANK,TATASTEEL,ITC
```

### How Region Detection Works

The `BrokerRouter.detect_region()` method determines the market:
- Symbols ending in `.NS` or `.BO` → `india`
- All other symbols → `us`

The watchlist in `agent_config.py` auto-appends `.NS` to India tickers if missing:
```python
# .env: INDIA_WATCHLIST=RELIANCE,TCS
# Becomes: ['RELIANCE.NS', 'TCS.NS']
```

### Combined Ticker List

`agent_config.settings.all_tickers` provides the merged list of US + India tickers, used by `main.py` for the analysis loop and by the dashboard for the earnings calendar.
