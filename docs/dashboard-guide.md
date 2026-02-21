# 📊 Dashboard Guide

The trading agent includes a high-performance **FastAPI + Vanilla JS Single Page Application (SPA)** for real-time monitoring.

## 🚀 Launch

1. Start the dashboard backend:
```bash
python dashboard_api.py
```

2. Open your browser to:
   **[http://localhost:8050](http://localhost:8050)**

---

## 🧭 Navigation & Views

The dashboard is organized into 5 main views, accessible via the sidebar:

### 1. 💼 Portfolio
*   **Active Holdings**: Real-time view of current positions with Unrealized P&L.
*   **Performance Chart**: Interactive equity curve showing portfolio value over time (US vs India).
*   **Recent Trades**: Log of executed trades with status and Net P&L.
*   **Metrics**: Daily trade counts and fees paid.

### 2. 🧠 AI Decisions
Detailed inspection of the agent's thought process:
*   **Feed**: Chronological list of all AI trade signals (BUY/SELL/HOLD).
*   **Deep Dive**: Click "Show Analysis Details" to see:
    *   **Reasoning**: The AI's logic for the decision.
    *   **Risk Review**: The "Devil's Advocate" critique and whether it blocked the trade.
    *   **Technicals**: The exact indicators (RSI, MACD, etc.) used at that moment.
    *   **News**: Headlines that influenced the decision.

### 3. 🔍 Discovery
*   **Sector Scan**: Real-time performance of key sectors (Tech, Finance, Energy) in both US and India.
*   **Market Status**: Quick view of global market trends.

### 4. ⚡ Analysis & Trade
Manual execution and AI vetting portal:
*   **Get AI Analysis**: Input any symbol (and optional option derivatives like Strike/Expiry). The AI will fetch live data, compute technicals, read news, and provide a BUY/HOLD/SELL verdict with target prices and confidence before you trade.
*   **Manual Trade Execution**: Log manual trades outside the automated loop into the local database to keep portfolio performance and equity charts perfectly aligned. Supports Market, Limit, and Stop Loss orders.
*   **Visual Execution Chart**: Instantly plot your exact historical entries and exits directly on a candlestick price chart.

### 5. ⚡ AI Metrics
Operational health monitoring:
*   **API Usage**: Track token consumption, latency, and costs for OpenAI/Gemini.
*   **Cache Performance**: Hit rates for the semantic cache (saving money/time).
*   **System Health**: Error rates and API availability.

### 5. ⚙️ Settings
*   **Configuration**: Update capital limits, risk settings, and watchlists dynamically.
*   **Danger Zone**: Clear trade history or logs (for testing resets).
*   **Theme**: Toggle between **Light**, **Dark**, or **System** theme.

---

## 🎨 Theming

The dashboard supports **Dark Mode** (default) and **Light Mode**.
*   Toggle via the sun/moon icon in the sidebar.
*   Preference is saved to your browser's local storage.
*   Charts automatically adapt colors for maximum legibility in both modes.

---

## 🏗️ Architecture

*   **Backend**: FastAPI (Python) serving REST APIs at `/api/*`.
*   **Frontend**: Vanilla JavaScript (ES6+), CSS3 Variables, and HTML5.
*   **No Build Step**: Pure static files serving, no `npm install` or `webpack` required.
