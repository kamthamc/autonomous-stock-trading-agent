import asyncio
import structlog
from typing import List, Optional
from pydantic import BaseModel

from .technical import TechAnalyzer
from .ai import AIAnalyzer, AISignal
from .news import NewsFetcher
from .risk import RiskManager, TradeRequest
from trader.market_data import MarketDataFetcher
from .market_hours import is_market_open
from .technical import TechAnalyzer
from .ai import AIAnalyzer, AISignal
from .news import NewsFetcher
from .risk import RiskManager, TradeRequest
from .market_hours import is_market_open
from config import settings

logger = structlog.get_logger()

class TradeSignal(BaseModel):
    symbol: str
    action: str  # BUY, SELL, HOLD
    asset_type: str # STOCK, CALL, PUT
    quantity: int = 0
    price: float = 0.0
    reason: str
    confidence: float
    recommended_option: Optional[str] = None

class StrategyEngine:
    # ... (init unchanged) ...
    def __init__(self, 
                 market_data: Optional[MarketDataFetcher] = None, 
                 news_fetcher: Optional[NewsFetcher] = None, 
                 tech_analyzer: Optional[TechAnalyzer] = None, 
                 ai_analyzer: Optional[AIAnalyzer] = None, 
                 risk_manager: Optional[RiskManager] = None):
        
        self.market_data = market_data or MarketDataFetcher()
        self.news_fetcher = news_fetcher or NewsFetcher()
        self.tech_analyzer = tech_analyzer or TechAnalyzer()
        self.ai_analyzer = ai_analyzer or AIAnalyzer()
        self.risk_manager = risk_manager or RiskManager()

    async def analyze_symbol(self, symbol: str) -> Optional[TradeSignal]:
        """Runs full analysis cycle for a single symbol."""
        logger.info("analyzing_symbol", symbol=symbol)
        
        # 0a. Check Available Funds (Skip analysis if broke)
        if not await self.risk_manager.has_sufficient_funds(100.0): # Minimum to trade
            logger.warning("insufficient_funds_pausing_analysis", symbol=symbol)
            return None

        # 0b. Market Hours Check (Skip if Live and Closed)
        if settings.trading_mode == "live" and not is_market_open(symbol):
            logger.info("market_closed", symbol=symbol)
            return None
        
        # 1. Fetch Data Concurrently
        price_snapshot, history, options, news = await asyncio.gather(
            self.market_data.get_current_price(symbol),
            self.market_data.get_history(symbol),
            self.market_data.get_option_chain(symbol),
            self.news_fetcher.get_news(f"{symbol} stock news")
        )
        
        if not price_snapshot or history.empty:
            logger.warning("insufficient_data", symbol=symbol)
            return None

        # 2. Technical Analysis
        tech_indicators = self.tech_analyzer.analyze(history)
        if not tech_indicators:
            return None

        # 3. AI Analysis
        # Convert Pydantic models to dict for JSON serialization in prompt
        ai_signal = await self.ai_analyzer.analyze(
            symbol=symbol,
            price=price_snapshot.price,
            tech=tech_indicators.model_dump(),
            news=news,
            options=options
        )
        
        logger.info("ai_signal_generated", symbol=symbol, decision=ai_signal.decision, confidence=ai_signal.confidence)

        # Save Internal Signal to DB
        from database.db import save_signal
        from database.models import Signal
        
        await save_signal(Signal(
            symbol=symbol,
            decision=ai_signal.decision,
            confidence=ai_signal.confidence,
            reasoning=ai_signal.reasoning,
            recommended_option=ai_signal.recommended_option,
            stop_loss=ai_signal.stop_loss_suggestion,
            take_profit=ai_signal.take_profit_suggestion
        ))

        # 3.5 AI Risk Review (Devil's Advocate)
        # Only run if we have a potential trade (not HOLD) and decent confidence
        if ai_signal.decision != "HOLD" and ai_signal.confidence >= 0.6:
            is_approved = await self.ai_analyzer.review_trade(
                symbol=symbol,
                signal=ai_signal,
                price=price_snapshot.price,
                tech=tech_indicators.model_dump(),
                news=news
            )
            
            if not is_approved:
                logger.info("ai_risk_review_rejected", symbol=symbol, original_decision=ai_signal.decision)
                return TradeSignal(symbol=symbol, action="HOLD", asset_type="STOCK", reason="AI Risk Manager Rejected", confidence=ai_signal.confidence)

        # 4. Filter Low Confidence
        if ai_signal.confidence < 0.7:
            return TradeSignal(symbol=symbol, action="HOLD", asset_type="STOCK", reason="Low AI Confidence", confidence=ai_signal.confidence)

        # 5. Construct Trade Request based on AI Signal
        action = "HOLD"
        asset_type = "STOCK"
        quantity = 0 
        
        if "BUY" in ai_signal.decision:
            action = "BUY"
            if "CALL" in ai_signal.decision: asset_type = "CALL"
            elif "PUT" in ai_signal.decision: asset_type = "PUT"
            else: asset_type = "STOCK"
            
            # Simple position sizing for now
            quantity = 1 
            
            # 6. Risk Check
            trade_req = TradeRequest(
                symbol=symbol,
                action="BUY",
                quantity=quantity,
                price=price_snapshot.price, 
                stop_loss=ai_signal.stop_loss_suggestion
            )
            
            if not await self.risk_manager.validate_trade(trade_req):
                 return TradeSignal(symbol=symbol, action="HOLD", asset_type=asset_type, reason="Risk Check Failed", confidence=ai_signal.confidence)

        elif "SELL" in ai_signal.decision:
            action = "SELL"
            asset_type = "STOCK" # Simplified
            quantity = 1
        
        return TradeSignal(
            symbol=symbol,
            action=action,
            asset_type=asset_type,
            quantity=quantity,
            price=price_snapshot.price,
            reason=ai_signal.reasoning,
            confidence=ai_signal.confidence,
            recommended_option=ai_signal.recommended_option
        )

    async def run_cycle(self, watchlist: List[str]) -> List[TradeSignal]:
        """Runs analysis on all watchlist symbols."""
        tasks = [self.analyze_symbol(sym) for sym in watchlist]
        results = await asyncio.gather(*tasks)
        return [r for r in results if r is not None and r.action != "HOLD"]
