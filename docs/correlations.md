# 🔗 Correlations & Cross-Impact Analysis

The trading agent goes beyond isolated stock analysis by understanding the **relationships between companies** and **macro-economic sensitivities**. This allows the AI to factor in sector-wide trends, competitor earnings, and geopolitical events.

---

## 1. Peer Relationships

The system maps stocks to their peers (competitors, suppliers, customers) to detect cross-impacts.

### Discovery Methods

1.  **Hardcoded Map**: High-confidence relationships that are hard to detect automatically.
    *   *Example*: `NVDA` → `TSM` (Supplier), `MSFT` (Customer), `AMD` (Competitor).
2.  **Reverse Lookup**: If Stock A lists Stock B as a peer, Stock B automatically lists Stock A.
3.  **Dynamic Discovery**: For any stock not in the map, the system uses **yfinance sector & industry data** to find peers from your watchlist and the known universe.

### What the AI Sees
When analyzing a target stock (e.g., `GOOGL`), the AI is told about:
*   **Peer Earnings**: "MSFT (competitor) just reported earnings."
*   **Price Moves**: "META (competitor) moved +4.5% in the last session."

---

## 2. Macro & Geopolitical Sensitivities

Each stock is tagged with **macro themes** it is sensitive to. This guides the AI on *which news topics* to weigh heavily.

### Examples

| Symbol | Sensitive Themes |
| :--- | :--- |
| **NVDA** | AI industry developments, US-China chip export controls, Data center capex |
| **AAPL** | US-China tariffs, Big Tech antitrust, Consumer spending, USD strength |
| **TSLA** | EV subsidies/policy, Interest rates, Autonomous driving regulation |
| **TCS.NS** | US H-1B visa policy, USD/INR exchange rate, Enterprise IT budgets |
| **RELIANCE.NS** | Crude oil prices, India telecom policy, India retail market |

---

## 3. How It Works in Analysis

When `engine.py` runs an analysis cycle:

1.  **Fetch Data**: Gets price, tech indicators, and news for the target stock.
2.  **Cross-Impact Check**:
    *   Finds all peers.
    *   Checks if any peer has earnings within 14 days (or reported in last 3).
    *   Checks if any peer moved >3% recently.
3.  **Prompt Injection**:
    *   Injects a `🔗 RELATED STOCKS / CROSS-IMPACT` section into the LLM prompt.
    *   Lists significant peer activity.
    *   Lists specific macro themes to scan for in the news.

### Example Prompt Section

```text
🔗 RELATED STOCKS / CROSS-IMPACT:
The following correlated stocks have notable recent activity:
  - MSFT (competitor) has earnings in 2 days (EPS est: 2.85)
  - META (competitor) moved +4.2% (up) in last session

Macro/Political Sensitivities (scan news for these):
  - AI industry developments (new models, tools, partnerships)
  - Big Tech antitrust regulation and lawsuits
  - Digital ad spending trends
```

This context prevents the AI from analyzing a stock in a vacuum. It helps it understand *why* a stock might be moving (e.g., "Sympathy move with NVDA") or identify risks (e.g., "Competitor earnings ahead").

---

**See Also:** [Architecture Overview](./architecture.md) for how the Cross-Impact Engine fits into the broader system.
