import asyncio
import hashlib
import json
import time as time_module
from collections import OrderedDict
from openai import AsyncAzureOpenAI, AsyncOpenAI
from google import genai
from pydantic import BaseModel, Field
from typing import Any, Literal, Optional
import structlog
import os
import sys

# Import settings
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent_config import settings

logger = structlog.get_logger()


# ──────────────────────────────────────────────
# LLM Response Cache
# ──────────────────────────────────────────────
class LLMCache:
    """
    In-memory TTL cache for LLM responses.
    
    - Key: SHA-256 hash of the full prompt text
    - TTL: configurable (default 15 min — market data shifts slowly within a cycle)
    - Max entries: LRU eviction when full
    - Thread-safe enough for asyncio (single-threaded event loop)
    """
    
    def __init__(self, ttl_seconds: int = 900, max_entries: int = 200):
        self.ttl = ttl_seconds
        self.max_entries = max_entries
        self._cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._hits = 0
        self._misses = 0
    
    @staticmethod
    def _hash_prompt(prompt: str) -> str:
        return hashlib.sha256(prompt.encode()).hexdigest()
    
    def get(self, prompt: str) -> Optional[Any]:
        key = self._hash_prompt(prompt)
        if key in self._cache:
            ts, value = self._cache[key]
            if time_module.time() - ts < self.ttl:
                self._cache.move_to_end(key)  # refresh LRU position
                self._hits += 1
                return value
            else:
                del self._cache[key]  # expired
        self._misses += 1
        return None
    
    def put(self, prompt: str, value: Any) -> None:
        key = self._hash_prompt(prompt)
        self._cache[key] = (time_module.time(), value)
        self._cache.move_to_end(key)
        # Evict oldest if over limit
        while len(self._cache) > self.max_entries:
            self._cache.popitem(last=False)
    
    @property
    def stats(self) -> dict:
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{(self._hits / total * 100):.1f}%" if total > 0 else "0%",
            "entries": len(self._cache),
        }


# Shared cache instance (lives for the duration of the process)
_llm_cache = LLMCache(ttl_seconds=900, max_entries=200)

class AISignal(BaseModel):
    decision: Literal["BUY_CALL", "BUY_PUT", "BUY_STOCK", "SELL", "HOLD"]
    confidence: float = Field(..., description="0.0 to 1.0")
    reasoning: str
    recommended_option: Optional[str] = Field(None, description="Recommended option contract (e.g. AAPL 150 CALL 2023-10-27)")
    stop_loss_suggestion: Optional[float] = None
    take_profit_suggestion: Optional[float] = None

class RiskReviewResult(BaseModel):
    """Structured result from the devil's advocate review."""
    is_approved: bool
    decision: str  # "APPROVE" or "REJECT"
    reasoning: str

class AIAnalyzer:
    def __init__(self):
        self.provider = settings.ai_provider
        
        if self.provider == "azure_openai":
            self.client = AsyncOpenAI(
                api_key=settings.azure_openai_api_key,
                # api_version=settings.azure_openai_api_version,
                base_url=settings.azure_openai_endpoint
            )
            self.model = settings.azure_openai_deployment_name
        
        elif self.provider == "gemini":
            self.gemini_client = genai.Client(api_key=settings.gemini_api_key)
            self.gemini_model = "gemini-1.5-pro-latest"
            
        else:
            # Fallback to standard OpenAI
            self.client = AsyncOpenAI(api_key=settings.openai_api_key)
            self.model = "gpt-5"

    def _format_options_table(self, options: list, current_price: float) -> str:
        """Formats the top 5 liquid calls and puts into a string table."""
        if not options:
            return "No options data available."

        # Separate Calls and Puts
        calls = [o for o in options if o.option_type == 'call']
        puts = [o for o in options if o.option_type == 'put']

        # Sort by Volume (Liquidity) and filter near ATM
        # Simple heuristic: Top 5 by Volume
        top_calls = sorted(calls, key=lambda x: x.volume, reverse=True)[:5]
        top_puts = sorted(puts, key=lambda x: x.volume, reverse=True)[:5]

        table = "Top Liquid Options (Calls):\n"
        table += f"| {'Strike':<8} | {'Expiry':<10} | {'Last':<6} | {'Vol':<6} | {'OI':<6} | {'IV':<5} |\n"
        table += "-" * 60 + "\n"
        for o in top_calls:
            table += f"| {o.strike:<8} | {o.expiry:<10} | {o.last_price:<6} | {o.volume:<6} | {o.open_interest:<6} | {o.implied_volatility:.2f} |\n"
        
        table += "\nTop Liquid Options (Puts):\n"
        table += f"| {'Strike':<8} | {'Expiry':<10} | {'Last':<6} | {'Vol':<6} | {'OI':<6} | {'IV':<5} |\n"
        table += "-" * 60 + "\n"
        for o in top_puts:
            table += f"| {o.strike:<8} | {o.expiry:<10} | {o.last_price:<6} | {o.volume:<6} | {o.open_interest:<6} | {o.implied_volatility:.2f} |\n"
            
        return table

    async def analyze(self, symbol: str, price: float, tech: dict, news: list, options: list, earnings: dict = None, cross_impact: str = None) -> AISignal:
        """Generates a trading signal using LLM. Results are cached by prompt hash."""
        from database.db import save_api_call_log
        from database.models import APICallLog
        from trader.router import BrokerRouter
        
        # Construct Prompt
        news_summary = "\n".join([f"- {n.title} ({n.source})" for n in news[:5]])
        options_table = self._format_options_table(options, price)
        
        earnings_section = ""
        if earnings:
            earnings_section = f"""
        ⚠️ EARNINGS ALERT:
        - Next Earnings Date: {earnings.get('next_earnings_date', 'Unknown')}
        - Days Until Earnings: {earnings.get('days_until_earnings', 'Unknown')}
        - EPS Estimate: {earnings.get('eps_estimate', 'N/A')}
        - Revenue Estimate: {earnings.get('revenue_estimate', 'N/A')}
        
        IMPORTANT: Earnings announcements can cause significant volatility. Factor this into your risk assessment.
        If earnings are within 3 days, prefer HOLD unless the setup is very strong.
        """
        
        cross_impact_section = ""
        if cross_impact:
            cross_impact_section = f"""
        🔗 RELATED STOCKS / CROSS-IMPACT:
        The following correlated stocks have notable recent activity that may affect {symbol}:
        {cross_impact}
        
        IMPORTANT: Consider sector contagion, supply chain effects, and competitor dynamics.
        Strong moves or earnings from competitors/suppliers/customers can signal sector-wide trends.
        """
        
        
        # Select Strategy Persona based on Config
        style = settings.trading_style
        if style == "intraday":
            strategy_persona = "INTRADAY SCALPER"
            goal_instruction = """
            Goal: Maximize INTRADAY profit. Focus on immediate price action (1-min to 15-min charts).
            
            STRATEGY CRITERIA:
            1. **Trend & Momentum**:
               - **VWAP**: bullish if Price > VWAP; bearish if Price < VWAP.
               - **RSI (14)**: Look for reversals at extremes (>70 sell, <30 buy) OR momentum breakouts (crossing 50).
            
            2. **Valid Setups**:
               - **Breakout**: Price clears resistance with Volume > 1.2x average.
               - **Pullback**: Retest of broken resistance or moving average (EMA 9/20) holding support.
               - **Mean Reversion**: Extreme extension from EMA + Reversal Candle (Hammer/Shooting Star).
               
            3. **Risk Management**:
               - Stop Loss must be TIGHT (0.5% - 1.5%).
               - Take Profit at next technical level (Pivot/High of Day).
               - If choppy/sideways, signal HOLD.
            """
        elif style == "long_term":
            strategy_persona = "VALUE INVESTOR"
            goal_instruction = """
            Goal: Long-term capital appreciation. Focus on fundamentals and macro trends.
            
            STRATEGY CRITERIA:
            1. **Business Quality**: Consistent earnings growth, wide moat.
            2. **Valuation**: Is P/E reasonable? RSI oversold on Weekly?
            3. **Execution**: Buy dips to 200-day SMA in strong uptrends.
            """
        else: # Default or short_term
            strategy_persona = "SWING TRADER"
            goal_instruction = """
            Goal: Capture SWING moves (2-10 days). Focus on Daily/4H structure.
            
            STRATEGY CRITERIA:
            1. **Market Structure**: Look for Higher Highs/Higher Lows (Uptrend).
            2. **Key Levels**: Buy at Support/Trendline retest. Sell at Resistance.
            3. **Oscillators**: MACD Crossover or RSI divergence.
            4. **Stop Loss**: Moderate (2% - 5%).
            """

        prompt = f"""
        You are an expert {strategy_persona}. Analyze the following data for {symbol} and provide a trading decision.
        
        Current Price: {price}
        
        Technical Indicators:
        {json.dumps(tech, indent=2)}
        
        Recent News:
        {news_summary}
        
        Options Chain Analysis:
        {options_table}
        {earnings_section}{cross_impact_section}
        
        {goal_instruction}

        Prioritize recent price action, RSI extremes, and immediate catalysts.
        If recommending BUY_CALL or BUY_PUT, YOU MUST SELECT the best specific contract from the Options Chain table above and populate 'recommended_option'.
        
        CRITICAL: Be DECISIVE.
        - If the setup is good, Confidence MUST be > 0.7.
        - If the setup is weak or ambiguous, Confidence MUST be < 0.5.
        - Avoid the "mushy middle" (0.5 - 0.65). If you are unsure, HOLD.
        
        Output JSON format ONLY:
        {{
            "decision": "BUY_CALL" | "BUY_PUT" | "BUY_STOCK" | "SELL" | "HOLD",
            "confidence": float (0.0-1.0),
            "reasoning": "string explanation",
            "recommended_option": "string (e.g. CALL 150 EXP 2023-10-27) or null",
            "stop_loss_suggestion": float,
            "take_profit_suggestion": float
        }}
        """
        
        # ── Cache check ──
        cached = _llm_cache.get(prompt)
        if cached is not None:
            logger.info("llm_cache_hit", symbol=symbol, source="ai_analyze",
                       cache_stats=_llm_cache.stats)
            try:
                await save_api_call_log(APICallLog(
                    source="ai_analyze_cached",
                    provider=self.provider,
                    endpoint="cache",
                    symbol=symbol,
                    region=BrokerRouter.detect_region(symbol),
                    latency_ms=0,
                    success=True,
                ))
            except Exception:
                pass
            return cached
        
        # ── LLM call ──
        content = None
        start_time = time_module.perf_counter()
        prompt_tokens = completion_tokens = total_tokens = None
        success = True
        error_msg = None
        
        try:
            if self.provider == "gemini":
                response = await self.gemini_client.aio.models.generate_content(
                    model=self.gemini_model,
                    contents=prompt,
                    config={"response_mime_type": "application/json"}
                )
                content = response.text
                
            else:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": f"You are a professional {strategy_persona}. Respond only in valid JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"}
                )
                content = response.choices[0].message.content
                
                # Extract token usage from OpenAI response
                if hasattr(response, 'usage') and response.usage:
                    prompt_tokens = response.usage.prompt_tokens
                    completion_tokens = response.usage.completion_tokens
                    total_tokens = response.usage.total_tokens
            
            # Parse JSON
            if content and "```json" in content:
                content = content.replace("```json", "").replace("```", "")
            if content and "```" in content:
                content = content.replace("```", "")
                
            data = json.loads(content.strip())
            result = AISignal(**data)
            
            # ── Cache store ──
            _llm_cache.put(prompt, result)
            return result

        except Exception as e:
            success = False
            error_msg = str(e)
            logger.error("ai_analysis_error", symbol=symbol, provider=self.provider, error=str(e), content_preview=str(content)[:100] if content else "None")
            return AISignal(decision="HOLD", confidence=0.0, reasoning=f"Error ({self.provider}): {str(e)}")
        
        finally:
            latency_ms = int((time_module.perf_counter() - start_time) * 1000)
            try:
                await save_api_call_log(APICallLog(
                    source="ai_analyze",
                    provider=self.provider,
                    endpoint=getattr(self, 'model', getattr(self, 'gemini_model', 'unknown')),
                    symbol=symbol,
                    region=BrokerRouter.detect_region(symbol),
                    latency_ms=latency_ms,
                    success=success,
                    error_message=error_msg,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                ))
            except Exception:
                pass  # Don't let stats tracking break the main flow

    async def review_trade(self, symbol: str, signal: AISignal, price: float, tech: dict, news: list) -> RiskReviewResult:
        """
        Acts as a Risk Manager (Devil's Advocate).
        Reviews a generated signal and tries to find reasons to REJECT it.
        Returns a RiskReviewResult with the decision and reasoning.
        """
        from database.db import save_api_call_log
        from database.models import APICallLog
        from trader.router import BrokerRouter
        
        if signal.decision == "HOLD":
            return RiskReviewResult(is_approved=True, decision="APPROVE", reasoning="HOLD signal, no review needed.")

        news_summary = "\n".join([f"- {n.title}" for n in news[:3]])
        
        prompt = f"""
        ROLE: Strict Risk Manager.
        TASK: Critique this proposed trade for {symbol}.
        
        Proposed Trade: {signal.decision} @ ${price}
        Reasoning: {signal.reasoning}
        Confidence: {signal.confidence}
        
        Context:
        - Tech Indicators: {json.dumps(tech, indent=2)}
        - Recent News: {news_summary}
        
        YOUR JOB: 
        Critique the trade. You are a "Devil's Advocate".
        
        GUIDELINES:
        1. **Allow Non-Stock Assets**: ETFs, Commodities are VALID.
        2. **Value Macro Context**: War/Bonds/Rates are valid reasons.
        3. **Confidence Filter**:
           - **0.60 Threshold**: For Intraday/Swing strategies.
           - If Confidence > 0.60: Reject ONLY if there is a **FATAL Technical Flaw** (e.g. Buying directly into major resistance, ignoring bearish divergence).
           - Do NOT reject for generic reasons like "market uncertainty".
        4. **Liquidity**: Do NOT reject Major Caps (Tata, Reliance, Apple, etc) for "low volume" unless it's < 10% of average.
        
        RISK CHECKLIST (Critique these points):
        - **Trend Alignment**: Is the trade fighting a strong higher-timeframe trend without a reversal signal?
        - **R:R Ratio**: Is the Stop Loss too wide (>2% for scalp)?
        - **Overhead Supply**: Are we buying at the top of a range?
        
        Look for:
        - Buying into resistance / Selling into support
        - RSI extremes (Buying > 75, Selling < 25) - UNLESS Mean Reversion
        - Counter-trend trades without confirmation
        
        NOTE: This is a SHORT-TERM strategy. Do not reject trades solely because "long term trend is bearish" if short-term momentum is bullish.
        
        Output JSON ONLY:
        {{
            "decision": "APPROVE" | "REJECT",
            "risk_analysis": "Brief explanation of risks found or why it's clean."
        }}
        """
        
        # ── Cache check ──
        cached = _llm_cache.get(prompt)
        if cached is not None:
            logger.info("llm_cache_hit", symbol=symbol, source="ai_review",
                       cache_stats=_llm_cache.stats)
            try:
                await save_api_call_log(APICallLog(
                    source="ai_review_cached",
                    provider=self.provider,
                    endpoint="cache",
                    symbol=symbol,
                    region=BrokerRouter.detect_region(symbol),
                    latency_ms=0,
                    success=True,
                ))
            except Exception:
                pass
            return cached
        
        # ── LLM call ──
        content = None
        start_time = time_module.perf_counter()
        prompt_tokens = completion_tokens = total_tokens = None
        success = True
        error_msg = None
        
        try:
            # Use same client/model as analyze
            if self.provider == "gemini":
                response = await self.gemini_client.aio.models.generate_content(
                    model=self.gemini_model,
                    contents=prompt,
                    config={"response_mime_type": "application/json"}
                )
                content = response.text
            else:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "You are a conservative Risk Manager. Output JSON only."},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"}
                )
                content = response.choices[0].message.content
                
                if hasattr(response, 'usage') and response.usage:
                    prompt_tokens = response.usage.prompt_tokens
                    completion_tokens = response.usage.completion_tokens
                    total_tokens = response.usage.total_tokens

            if content and "```json" in content:
                content = content.replace("```json", "").replace("```", "")
            if content and "```" in content:
                content = content.replace("```", "")

            data = json.loads(content.strip())
            decision = data.get("decision", "REJECT").upper()
            risk_reason = data.get("risk_analysis", "No reason provided")
            
            logger.info("ai_risk_review", symbol=symbol, decision=decision, reason=risk_reason)
            
            result = RiskReviewResult(
                is_approved=(decision == "APPROVE"),
                decision=decision,
                reasoning=risk_reason
            )
            
            # ── Cache store ──
            _llm_cache.put(prompt, result)
            return result

        except Exception as e:
            success = False
            error_msg = str(e)
            logger.error("ai_risk_review_error", symbol=symbol, error=str(e))
            return RiskReviewResult(
                is_approved=False,
                decision="REJECT",
                reasoning=f"Review failed with error: {str(e)}"
            )
        
        finally:
            latency_ms = int((time_module.perf_counter() - start_time) * 1000)
            try:
                await save_api_call_log(APICallLog(
                    source="ai_review",
                    provider=self.provider,
                    endpoint=getattr(self, 'model', getattr(self, 'gemini_model', 'unknown')),
                    symbol=symbol,
                    region=BrokerRouter.detect_region(symbol),
                    latency_ms=latency_ms,
                    success=success,
                    error_message=error_msg,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                ))
            except Exception:
                pass

    async def generate_text(self, prompt: str) -> str:
        """Generates raw text response for a given prompt (used by Scanner)."""
        try:
            if self.provider == "gemini":
                # Gemini Text Generation
                response = await self.gemini_client.aio.models.generate_content(
                    model=self.gemini_model,
                    contents=prompt
                )
                return response.text
            else:
                # OpenAI / Azure Text Generation
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}]
                )
                return response.choices[0].message.content
        except Exception as e:
            logger.error("ai_generation_error", error=str(e))
            return ""
