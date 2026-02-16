# 📊 Dashboard Guide

The trading agent includes a **Streamlit-based real-time dashboard** for monitoring all agent activity.

## Launch

```bash
streamlit run dashboard.py
```

Opens at `http://localhost:8501`.

---

## Sidebar Controls

### Filters
- **Symbol** — Filter all sections by a specific ticker (e.g., `AAPL`)
- **Rows to Load** — Slider to control how many records to display (default: 500)

### Auto-Refresh
- **Enable Auto-Refresh** — Toggle to automatically reload data
- **Refresh Interval** — Dropdown to select refresh frequency (default: 60 seconds)
- **Refresh Now** — Button for manual refresh

### Market Status
Live indicators at the bottom of the sidebar:

| Icon | Meaning |
|------|---------|
| 🟢 | Market is currently open |
| 🟡 | Pre-market window or early close day |
| 🔴 | Market closed (holiday — name shown) |
| ⚫ | Market closed (regular hours) |

Example:
```
US (09:45 ET): 🟢 Open
India (20:15 IST): ⚫ Closed
```

---

## Dashboard Sections

### 1. 🧠 AI Strategy Signals

Shows all generated trading signals from the AI analyzer.

| Column | Description |
|--------|-------------|
| `timestamp` | When the signal was generated |
| `symbol` | Ticker symbol |
| `decision` | BUY_CALL, BUY_PUT, BUY_STOCK, SELL, HOLD |
| `confidence` | AI confidence score (0.0–1.0) |
| `recommended_option` | Specific option contract (if applicable) |
| `reasoning` | AI's explanation for the decision |

**Source:** `trading_agent.db → signals`

### 2. 📅 Upcoming Earnings Calendar

Expandable section showing upcoming quarterly results for all watched tickers.

| Column | Description |
|--------|-------------|
| `Symbol` | Ticker symbol |
| `Earnings Date` | Expected earnings report date |
| `Days Until` | Number of days until earnings |
| `EPS Estimate` | Consensus EPS estimate |
| `Alert` | ⚠️ if earnings within 7 days |

Sorted by proximity (nearest earnings first).

### 3. 😈 Devil's Advocate Reviews

Risk review decisions from the secondary AI agent.

| Column | Description |
|--------|-------------|
| `timestamp` | When the review occurred |
| `symbol` | Ticker symbol |
| `original_decision` | The AI's proposed trade |
| `original_confidence` | Original confidence score |
| `review_decision` | APPROVE or REJECT |
| `was_overridden` | Whether the review changed the outcome |
| `review_reasoning` | Risk manager's explanation |

**Color coding:**
- 🟢 APPROVE rows
- 🔴 REJECT rows

**Source:** `activity_YYYY_MM.db → risk_reviews`

### 4. 💰 Recent Trades

Executed trades (real or paper).

| Column | Description |
|--------|-------------|
| `timestamp` | Trade execution time |
| `symbol` | Ticker symbol |
| `action` | BUY, SELL, etc |
| `quantity` | Number of shares/contracts |
| `price` | Execution price |
| `pnl` | Profit/Loss if closed |

**Source:** `trading_agent.db → trades`

### 5. 📈 Market Scanner Trends

AI-detected market-wide trends and themes.

| Column | Description |
|--------|-------------|
| `timestamp` | When the scan occurred |
| `trend` | Detected market trend/theme |
| `assessment` | AI's interpretation |

**Source:** `trading_agent.db → market_trends`

### 6. 📊 API Usage & Performance

Detailed tracking of all external API calls.

#### Time Range Filter
- Today
- Last 6 hours
- Last 1 hour
- All (this month)

#### Summary Metrics
| Metric | Description |
|--------|-------------|
| Total Calls | Number of API calls in the period |
| Success Rate | Percentage of successful calls |
| Avg Latency | Mean response time in milliseconds |
| Total Tokens | Combined prompt + completion tokens |

#### Charts
- **Calls by Source** — Pie chart (ai_analyze, ai_review, cached, etc.)
- **Calls by Provider** — Pie chart (azure_openai, gemini, cache)

#### Detailed Log Table
Full API call log with columns: timestamp, source, provider, symbol, latency, success, token counts, errors.

**Source:** `activity_YYYY_MM.db → api_call_logs`

### 7. 📝 Live Agent Logs

Raw JSON-structured logs from the agent process.

Displays logs from `agent_activity.log` with fields like:
- timestamp, level, event, symbol, decision, confidence

---

## Data Sources

The dashboard reads from two SQLite databases:

| Database | File | Contents |
|----------|------|----------|
| Trading DB | `trading_agent.db` | Signals, trades, market trends |
| Activity DB | `activity_YYYY_MM.db` | Risk reviews, API call logs, events |

The activity DB path is shown in the sidebar footer and rotates monthly.
