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
    - TTL: configurable per trading style
    - Max entries: LRU eviction when full
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
                self._cache.move_to_end(key)
                self._hits += 1
                return value
            else:
                del self._cache[key]
        self._misses += 1
        return None
    
    def put(self, prompt: str, value: Any) -> None:
        key = self._hash_prompt(prompt)
        self._cache[key] = (time_module.time(), value)
        self._cache.move_to_end(key)
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


# Cache TTL from active style profile
_style_profile = settings.active_style_profile
_llm_cache = LLMCache(ttl_seconds=_style_profile.llm_cache_ttl_seconds, max_entries=200)

class AISignal(BaseModel):
    decision: Literal["BUY_CALL", "BUY_PUT", "BUY_STOCK", "SELL", "HOLD"]
    confidence: float = Field(..., description="0.0 to 1.0")
    reasoning: str
    recommended_option: Optional[str] = Field(None, description="Recommended option contract")
    stop_loss_suggestion: Optional[float] = None
    take_profit_suggestion: Optional[float] = None
    allocation_pct: Optional[float] = Field(None, description="Fraction of available capital to use (0.05 to 1.0)")
    was_cache_hit: bool = False  # Set by the caller, not by the LLM

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
                base_url=settings.azure_openai_endpoint
            )
            self.model = settings.azure_openai_deployment_name
        
        elif self.provider == "gemini":
            self.gemini_client = genai.Client(api_key=settings.gemini_api_key)
            self.gemini_model = "gemini-1.5-pro-latest"
            
        else:
            self.client = AsyncOpenAI(api_key=settings.openai_api_key)
            self.model = "gpt-5"

    def _format_options_table(self, options: list, current_price: float) -> str:
        """Formats the top 5 liquid calls and puts into a string table."""
        if not options:
            return "No options data available."

        calls = [o for o in options if o.option_type == 'call']
        puts = [o for o in options if o.option_type == 'put']
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

    def _get_strategy_prompt(self) -> tuple[str, str]:
        """Returns (persona_name, goal_instruction) based on trading style."""
        style = settings.trading_style
        
        if style == "optimistic":
            return "OPTIMISTIC MOMENTUM TRADER", """
            Goal: Maximize AGGRESSIVE upside capture. Buy with conviction, trail to the top, take partial profits.

            STRATEGY CRITERIA:
            1. **Bias**: DEFAULT TO BUY unless there is a CLEAR, IMMEDIATE threat.
               - "Might go down" is NOT a reason to hold. RSI overbought in a strong trend is a BUY signal.
               - Only HOLD if the stock is in a CONFIRMED downtrend (Lower Lows on Daily + Bearish MACD).

            2. **Entry Sizing** (set allocation_pct):
               - Strong momentum + positive news + favorable macro → allocation_pct: 0.30 (aggressive)
               - Standard conviction → allocation_pct: 0.15 (normal)
               - Uncertain but potential → allocation_pct: 0.08 (small starter)

            3. **Exit Logic** (CRITICAL — DO NOT SELL EVERYTHING AT ONCE):
               - If news is catastrophic (fraud, bankruptcy, SEC probe) → SELL with allocation_pct: 1.0 (full exit)
               - If moderately negative → SELL with allocation_pct: 0.50 (half exit)
               - For profit-taking → let trailing stop and partial sell system handle it (signal HOLD)
               - Only signal SELL if there's an ACTIVE reason to exit NOW.

            4. **Macro Awareness**:
               - Positive geopolitics (trade deals, stimulus, rate cuts) → increase allocation_pct by +0.10
               - Company buybacks, guidance raises, new contracts → increase confidence +0.15
               - Competitor weakness → BUY the strong player more aggressively
               - B2B supply chain growth → BUY supply chain beneficiaries
               - Negative macro (war, policy risk) → reduce allocation_pct, DON'T avoid entirely

            5. **News Impact**: Consider ONLY genuinely actionable news. Ignore generic market commentary.
               - If all news is old/recycled, treat as neutral — DON'T let stale headlines weigh decisions.

            6. **Cost Awareness**: Each trade has transaction fees. Avoid churning (buying and selling frequently).
               - Don't signal SELL just because of a tiny dip. Trailing stop handles that.
            """
        
        elif style == "intraday":
            return "INTRADAY SCALPER", """
            Goal: Maximize INTRADAY profit. Focus on immediate price action.
            
            STRATEGY CRITERIA:
            1. **Trend & Momentum**: VWAP: bullish if Price > VWAP. RSI extremes for reversals.
            2. **Valid Setups**: Breakout (Vol > 1.2x avg), Pullback to EMA, Mean Reversion at extremes.
            3. **Risk**: Stop Loss 0.5-1.5%. Take Profit at next technical level.
            4. **Sizing**: allocation_pct 0.10-0.20 per trade. Don't oversize intraday.
            """
        
        elif style == "long_term":
            return "VALUE INVESTOR", """
            Goal: Long-term capital appreciation. Focus on fundamentals and macro trends.
            
            STRATEGY CRITERIA:
            1. **Business Quality**: Consistent earnings growth, wide moat.
            2. **Valuation**: Reasonable P/E? RSI oversold on Weekly?
            3. **Execution**: Buy dips to 200-day SMA in strong uptrends.
            4. **Sizing**: allocation_pct 0.20-0.40 for conviction buys. Small starters at 0.10.
            """
        
        else:  # short_term
            return "SWING TRADER", """
            Goal: Capture SWING moves (2-10 days). Focus on Daily/4H structure.
            
            STRATEGY CRITERIA:
            1. **Market Structure**: Higher Highs/Higher Lows (Uptrend).
            2. **Key Levels**: Buy at Support/Trendline retest. Sell at Resistance.
            3. **Oscillators**: MACD Crossover or RSI divergence.
            4. **Sizing**: allocation_pct 0.15-0.25. Conservative for unclear setups.
            """

    async def analyze(self, symbol: str, price: float, tech: dict, news: list, options: list, earnings: dict = None, cross_impact: str = None) -> AISignal:
        """Generates a trading signal using LLM. Results are cached by prompt hash."""
        from database.db import save_api_call_log
        from database.models import APICallLog
        from trader.router import BrokerRouter
        
        # Construct Prompt
        news_summary = "\n".join([f"- [{n.sentiment.upper()}] {n.title} ({n.source})" for n in news[:5]])
        options_table = self._format_options_table(options, price)
        
        earnings_section = ""
        if earnings:
            earnings_section = f"""
        ⚠️ EARNINGS ALERT:
        - Next Earnings Date: {earnings.get('next_earnings_date', 'Unknown')}
        - Days Until Earnings: {earnings.get('days_until_earnings', 'Unknown')}
        - EPS Estimate: {earnings.get('eps_estimate', 'N/A')}
        - Revenue Estimate: {earnings.get('revenue_estimate', 'N/A')}
        
        IMPORTANT: Earnings can cause significant volatility. Factor into risk assessment.
        If earnings are within 3 days, prefer HOLD unless the setup is very strong.
        """
        
        cross_impact_section = ""
        if cross_impact:
            cross_impact_section = f"""
        🔗 RELATED STOCKS / CROSS-IMPACT:
        {cross_impact}
        
        Consider sector contagion, supply chain effects, and competitor dynamics.
        """
        
        strategy_persona, goal_instruction = self._get_strategy_prompt()

        prompt = f"""
        You are an expert {strategy_persona}. Analyze the following data for {symbol} and provide a trading decision.
        
        Current Price: {price}
        
        Technical Indicators:
        {json.dumps(tech, indent=2)}
        
        Recent News (sentiment-tagged):
        {news_summary}
        
        Options Chain Analysis:
        {options_table}
        {earnings_section}{cross_impact_section}
        
        {goal_instruction}

        IMPORTANT RULES:
        - Be DECISIVE. Good setup → confidence > 0.7. Weak/ambiguous → confidence < 0.5. Avoid mushy middle.
        - If recommending BUY_CALL or BUY_PUT, SELECT a specific contract from the Options Chain.
        - Set allocation_pct to indicate how much of available capital to invest (0.05 to 0.40).
        - For SELL signals, set allocation_pct to indicate what fraction of the position to sell (0.25=partial, 1.0=full exit).
        - Don't signal SELL just because of a small pullback — trailing stops handle that.
        - DO NOT trade on the same news twice. If all news is generic/old, bias toward HOLD.
        
        Output JSON format ONLY:
        {{
            "decision": "BUY_CALL" | "BUY_PUT" | "BUY_STOCK" | "SELL" | "HOLD",
            "confidence": float (0.0-1.0),
            "reasoning": "string explanation including which macro/news factors influenced your decision",
            "recommended_option": "string or null",
            "stop_loss_suggestion": float,
            "take_profit_suggestion": float,
            "allocation_pct": float (0.05 to 1.0 — how much capital to use for BUY, or position fraction to sell for SELL)
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
            cached.was_cache_hit = True
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
            result.was_cache_hit = False
            
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
                pass

    async def review_trade(self, symbol: str, signal: AISignal, price: float, tech: dict, news: list) -> RiskReviewResult:
        """
        Acts as a Risk Manager (Devil's Advocate).
        Reviews a generated signal and tries to find reasons to REJECT it.
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
        Suggested Allocation: {signal.allocation_pct or 'not specified'}
        
        Context:
        - Tech Indicators: {json.dumps(tech, indent=2)}
        - Recent News: {news_summary}
        
        YOUR JOB: 
        Critique the trade. You are a "Devil's Advocate".
        
        GUIDELINES:
        1. **Allow Non-Stock Assets**: ETFs, Commodities are VALID.
        2. **Value Macro Context**: War/Bonds/Rates are valid reasons.
        3. **Confidence Filter**: If Confidence > 0.60, reject ONLY for FATAL flaws.
        4. **Cost Awareness**: Consider if this trade is worth the transaction fees.
           - Small allocation (<5% of capital) with low confidence is NOT worth the fees.
        5. **Allocation Check**: Is the suggested allocation_pct reasonable for the risk level?
        
        RISK CHECKLIST:
        - Trend Alignment: Fighting a strong higher-timeframe trend?
        - R:R Ratio: Stop Loss too wide?
        - Overhead Supply: Buying at top of range?
        - Fee Efficiency: Is the position large enough to justify transaction costs?
        
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
                response = await self.gemini_client.aio.models.generate_content(
                    model=self.gemini_model,
                    contents=prompt
                )
                return response.text
            else:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}]
                )
                return response.choices[0].message.content
        except Exception as e:
            logger.error("ai_generation_error", error=str(e))
            return ""
