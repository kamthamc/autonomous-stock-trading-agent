# Autonomous Stock Trading Agent 🤖📈

> [!CAUTION]
> **DISCLAIMER: EXPERIMENTAL SOFTWARE**
> This project is for **EDUCATIONAL AND RESEARCH PURPOSES ONLY**. 
> - It is **NOT** financial advice.
> - The software is **untested** in live market conditions.
> - Using this software for live trading carries significant risk of financial loss.
> - The authors and contributors assume **NO RESPONSIBILITY** for any trades executed or money lost.
> - **ALWAYS** use Paper Trading mode (`trading_mode=paper`) for testing.
> - Never hardcode API keys or secrets; always use the `.env` file.

An advanced, AI-powered autonomous trading agent capable of analyzing market data, news, and technical indicators to execute trades on US and Indian stock markets.

## 🚀 Features

*   **Multi-Broker Support**: Integration with **Robinhood** (US), **Zerodha** (India), and **ICICI Direct** (India).
*   **AI-Driven Analysis**: Uses LLMs (OpenAI/Azure OpenAI/Gemini) to analyze technicals, news sentiment, and option chains.
*   **Smart Risk Management**:
    *   **Capital Allocation**: Dynamic position sizing based on risk appetite.
    *   **AI Risk Review (Devil's Advocate)**: A secondary AI agent critiques every trade to prevent hallucinations.
    *   **Pre-Trade Checks**: Validates funds and market hours before analysis.
*   **Options Intelligence**:
    *   Analyzes Option Chains (Volume, OI, Greeks).
    *   Recommends specific contracts (e.g., "AAPL 150 CALL").
*   **Real-Time Dashboard**:
    *   Streamlit-based UI for monitoring trades, signals, and PnL.
    *   Live logs and AI reasoning transparency.
*   **News Intelligence**:
    *   Fetches and caches news for 10 minutes to respect API rate limits.
    *   Analyzes sentiment and geopolitical events.

## ⚠️ Broker Integration & Safety

### Official APIs (Recommended)
*   **Zerodha (Kite Connect)**: Official, stable, and secure. Recommended for Indian markets.
*   **ICICI Direct (Breeze)**: Official, stable, and secure. Recommended for Indian markets.

### Unofficial APIs (Use with Caution)
*   **Robinhood**: Uses `robin_stocks`, an unofficial wrapper.
    *   **Risk**: Robinhood does not officially support API trading for retail accounts. They may flag or lock accounts using automated scripts.
    *   **Fragility**: Changes to Robinhood's internal API may break this integration at any time.
    *   **Recommendation**: Use for **Paper Trading only** or small experimental accounts. Do not use with primary life savings.

## 🛠️ Installation

1.  **Clone the Repository**:
    ```bash
    git clone <repository_url>
    cd autonomous-stock-trading-agent
    ```

2.  **Set up Virtual Environment**:
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows: .venv\Scripts\activate
    ```

3.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure Environment**:
    Copy `.env.example` to `.env` and fill in your keys:
    ```bash
    cp .env.example .env
    ```
    *Required Keys*: `OPENAI_API_KEY` (or Azure/Gemini), Broker Credentials.

## 🏃‍♂️ Usage

### 1. Run the Agent
The main agent runs in the background, analyzing stocks and executing trades.
```bash
python main.py
```

### 2. Launch the Dashboard
Monitor performance, logs, and signals in real-time.
```bash
streamlit run dashboard.py
```

## 🧠 Architecture

*   **`main.py`**: Entry point. Manages the trading loop and broker connections.
*   **`strategy/`**:
    *   `engine.py`: Orchestrates data fetching, analysis, and execution.
    *   `ai.py`: Handles LLM prompts for Analysis and Risk Review.
    *   `market_hours.py`: Checks market status for US/IN exchanges.
    *   `news.py`: Fetches and caches news.
*   **`trader/`**: Broker integrations (Robinhood, Zerodha).
*   **`database/`**: SQLModel definitions and DB interactions.

## 🛡️ Safety Mechanisms

1.  **Paper Trading Mode**: Default mode (`trading_mode=paper` in `.env`) simulates trades without real money.
2.  **Funds Check**: Prevents trading if capital < $100.
3.  **AI Devil's Advocate**: Rejects trades if the Risk Manager AI finds flaws in the thesis.

## 🤝 Contributing

Contributions are welcome! Please open an issue or PR for major changes.

## 📄 License

MIT License
