import asyncio
import json
from openai import AsyncAzureOpenAI, AsyncOpenAI
from google import genai
from pydantic import BaseModel, Field
from typing import Literal, Optional
import structlog
import os
import sys

# Import settings
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

logger = structlog.get_logger()

class AISignal(BaseModel):
    decision: Literal["BUY_CALL", "BUY_PUT", "BUY_STOCK", "SELL", "HOLD"]
    confidence: float = Field(..., description="0.0 to 1.0")
    reasoning: str
    recommended_option: Optional[str] = Field(None, description="Recommended option contract (e.g. AAPL 150 CALL 2023-10-27)")
    stop_loss_suggestion: Optional[float] = None
    take_profit_suggestion: Optional[float] = None

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
            self.model = "gpt-5-turbo"

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

    async def analyze(self, symbol: str, price: float, tech: dict, news: list, options: list) -> AISignal:
        """Generates a trading signal using LLM."""
        
        # Construct Prompt
        news_summary = "\n".join([f"- {n.title} ({n.source})" for n in news[:5]])
        options_table = self._format_options_table(options, price)
        
        prompt = f"""
        You are an expert autonomous stock trader. Analyze the following data for {symbol} and provide a trading decision.
        
        Current Price: {price}
        
        Technical Indicators:
        {json.dumps(tech, indent=2)}
        
        Recent News:
        {news_summary}
        
        Options Chain Analysis:
        {options_table}
        
        Goal: Optimal Profit with Managed Risk. Prefer high probability setups. 
        If recommending BUY_CALL or BUY_PUT, YOU MUST SELECT the best specific contract from the Options Chain table above and populate 'recommended_option'.
        
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
        
        content = None
        try:
            if self.provider == "gemini":
                # Google Gemini Call using new SDK
                response = await self.gemini_client.aio.models.generate_content(
                    model=self.gemini_model,
                    contents=prompt,
                    config={"response_mime_type": "application/json"}
                )
                content = response.text
                
            else:
                # OpenAI / Azure Call
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "You are a professional algorithmic trader. Respond only in valid JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    # temperature=0.2, # Removed as some Azure models only support default (1.0)
                    response_format={"type": "json_object"}
                )
                content = response.choices[0].message.content
            
            # Parse JSON
            # Sometimes LLMs wrap json in ```json ... ```
            if content and "```json" in content:
                content = content.replace("```json", "").replace("```", "")
            if content and "```" in content: # Generic code block
                content = content.replace("```", "")
                
            data = json.loads(content.strip())
            return AISignal(**data)

        except Exception as e:
            logger.error("ai_analysis_error", symbol=symbol, provider=self.provider, error=str(e), content_preview=str(content)[:100] if content else "None")
            return AISignal(decision="HOLD", confidence=0.0, reasoning=f"Error ({self.provider}): {str(e)}")

    async def review_trade(self, symbol: str, signal: AISignal, price: float, tech: dict, news: list) -> bool:
        """
        Acts as a Risk Manager (Devil's Advocate).
        Reviews a generated signal and tries to find reasons to REJECT it.
        Returns True if the trade survives the review, False if rejected.
        """
        if signal.decision == "HOLD":
            return True

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
        Find potential flaws, risks, or reasons WHY COMPLIANCE SHOULD REJECT THIS TRADE.
        Be skeptical. Look for conflicting signals (e.g. Buying Calls when RSI is 80, or Buying Puts when Support is near).
        
        Output JSON ONLY:
        {{
            "decision": "APPROVE" | "REJECT",
            "risk_analysis": "Brief explanation of risks found or why it's clean."
        }}
        """
        
        content = None
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

            if content and "```json" in content:
                content = content.replace("```json", "").replace("```", "")
            if content and "```" in content:
                content = content.replace("```", "")

            data = json.loads(content.strip())
            decision = data.get("decision", "REJECT").upper()
            risk_reason = data.get("risk_analysis", "No reason provided")
            
            logger.info("ai_risk_review", symbol=symbol, decision=decision, reason=risk_reason)
            
            return decision == "APPROVE"

        except Exception as e:
            logger.error("ai_risk_review_error", symbol=symbol, error=str(e))
            # Fallback: If AI fails, strict mode says REJECT or standard says APPROVED?
            # Let's fail safe -> Reject if we can't verify.
            return False

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
