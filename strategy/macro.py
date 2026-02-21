import asyncio
import structlog
from pydantic import BaseModel, Field
from typing import List, Dict, Any
from datetime import datetime

from .ai import AIAnalyzer
from .news import NewsFetcher
import yfinance as yf

logger = structlog.get_logger()

class MacroState(BaseModel):
    regime: str = Field(description="One of: BULLISH, NEUTRAL, CAUTION, BEARISH")
    vix_level: float
    reasoning: str
    circuit_breaker_active: bool = False

class MacroAgent:
    """
    Monitors global indices (SPY, QQQ, VIX) and macro news to determine overall market regime.
    Can act as a global circuit breaker.
    """
    def __init__(self, ai_analyzer: AIAnalyzer, news_fetcher: NewsFetcher):
        self.ai = ai_analyzer
        self.news_fetcher = news_fetcher
        self.current_state = MacroState(
            regime="NEUTRAL",
            vix_level=15.0,
            reasoning="Initializing",
            circuit_breaker_active=False
        )

    async def analyze_regime(self) -> MacroState:
        try:
            logger.info("macro_agent_analyzing_regime")
            
            # 1. Fetch Key Indices (SPY, QQQ, VIX, ^NSEI)
            tickers = ["SPY", "QQQ", "^VIX", "^NSEI"]
            data_points = {}
            for t in tickers:
                try:
                    ticker = yf.Ticker(t)
                    hist = ticker.history(period="5d")
                    if not hist.empty:
                        last_close = hist['Close'].iloc[-1]
                        prev_close = hist['Close'].iloc[-2] if len(hist) > 1 else last_close
                        change_pct = ((last_close - prev_close) / prev_close) * 100
                        data_points[t] = {
                            "price": round(last_close, 2),
                            "1d_change_pct": round(change_pct, 2)
                        }
                except Exception as e:
                    logger.error("macro_agent_ticker_fetch_failed", symbol=t, error=str(e))
            
            # 2. Fetch Macro News
            macro_news = await self.news_fetcher.get_news("Global Economy SPY QQQ Market Crash Fed Interest Rates")
            news_headlines = [n.title for n in macro_news[:8]]
            
            # 3. AI Regime Analysis
            system_prompt = "You are the Chief Macro Economist for a quantitative trading fund. Output only valid JSON."
            
            user_prompt = f"""
Analyze the current market data and news to determine the global market regime.

Indices Data:
{data_points}

Latest Macro News:
{news_headlines}

Based on this, classify the market regime into one of: BULLISH, NEUTRAL, CAUTION, BEARISH.
If the VIX is spiking dangerously (> 25) or major indices are crashing (-2% drops), or severe systemic news is breaking, you MUST output BEARISH.
If BEARISH, the trading system will activate a CIRCUIT BREAKER, halting all new buys and aggressively tightening stop losses.

Return a JSON object exactly like this:
{{
  "regime": "BULLISH" | "NEUTRAL" | "CAUTION" | "BEARISH",
  "reasoning": "brief explanation..."
}}
"""
            result = await self.ai._get_completion_json(system_prompt, user_prompt)
            
            regime = result.get("regime", "NEUTRAL").upper()
            reasoning = result.get("reasoning", "No reasoning provided.")
            
            vix_entry = data_points.get("^VIX", {})
            vix_level = vix_entry.get("price", 15.0)
            
            # Safety overrides based on raw VIX
            circuit_breaker = False
            if regime == "BEARISH" or vix_level > 28.0:
                circuit_breaker = True
                regime = "BEARISH"
                
            state = MacroState(
                regime=regime,
                vix_level=float(vix_level),
                reasoning=reasoning,
                circuit_breaker_active=circuit_breaker
            )
            
            logger.info("macro_regime_updated", regime=state.regime, 
                        vix=state.vix_level, breaker=state.circuit_breaker_active)
            
            self.current_state = state
            return state
            
        except Exception as e:
            logger.error("macro_agent_failed", error=str(e))
            return self.current_state
