import asyncio
import structlog
from typing import Dict, List, Optional
from pydantic import BaseModel
from decimal import Decimal

from .technical import TechAnalyzer
from .ai import AIAnalyzer, AISignal
from .news import NewsFetcher
from .risk import RiskManager, TradeRequest
from .market_hours import is_market_open
from .earnings import get_earnings_info
from .correlations import get_cross_impact
from trader.market_data import MarketDataFetcher
from trader.router import BrokerRouter
from database.db import save_signal, save_risk_review
from database.models import Signal, RiskReview
from agent_config import settings

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
    def __init__(self, 
                 market_data: Optional[MarketDataFetcher] = None, 
                 news_fetcher: Optional[NewsFetcher] = None, 
                 tech_analyzer: Optional[TechAnalyzer] = None, 
                 ai_analyzer: Optional[AIAnalyzer] = None, 
                 risk_managers: Optional[Dict[str, RiskManager]] = None):
        
        self.market_data = market_data or MarketDataFetcher()
        self.news_fetcher = news_fetcher or NewsFetcher()
        self.tech_analyzer = tech_analyzer or TechAnalyzer()
        self.ai_analyzer = ai_analyzer or AIAnalyzer()
        
        # Per-region risk managers
        self.risk_managers = risk_managers or {
            "US": RiskManager(
                region="US",
                max_capital=settings.us_max_capital,
                max_per_trade=settings.us_max_per_trade,
            ),
            "IN": RiskManager(
                region="IN",
                max_capital=settings.india_max_capital,
                max_per_trade=settings.india_max_per_trade,
            ),
        }

    def _get_risk_manager(self, symbol: str) -> RiskManager:
        """Returns the risk manager for the symbol's market region."""
        region = BrokerRouter.detect_region(symbol)
        rm = self.risk_managers.get(region)
        if rm is None:
            # Fallback to US if region not configured
            rm = self.risk_managers.get("US", list(self.risk_managers.values())[0])
        return rm

    def _calculate_position_size(self, price: float, risk_manager: RiskManager, stop_loss: Optional[float] = None) -> int:
        """
        Calculates how many shares to buy based on the region's risk parameters.
        Uses the lesser of:
        - Max allocation per trade (from config or 20% of regional capital)
        - Risk-based sizing using stop loss distance
        """
        if price <= 0:
            return 0
        
        capital = float(risk_manager.current_capital)
        max_allocation = float(risk_manager.max_capital_per_trade)
        
        # Max shares based on allocation limit
        max_shares_by_allocation = int(max_allocation / price)
        
        if stop_loss and stop_loss < price:
            risk_per_share = price - stop_loss
            allowed_risk = capital * float(risk_manager.max_risk_per_trade)
            max_shares_by_risk = int(allowed_risk / risk_per_share) if risk_per_share > 0 else max_shares_by_allocation
            return max(1, min(max_shares_by_allocation, max_shares_by_risk))
        
        return max(1, max_shares_by_allocation)

    async def analyze_symbol(self, symbol: str) -> Optional[TradeSignal]:
        """Runs full analysis cycle for a single symbol."""
        logger.info("analyzing_symbol", symbol=symbol)
        
        risk_manager = self._get_risk_manager(symbol)
        region = BrokerRouter.detect_region(symbol)
        
        # 0. Circuit breaker check
        if risk_manager.is_circuit_breaker_triggered():
            logger.warning("circuit_breaker_active_skipping", symbol=symbol, region=region)
            return None

        # 0a. Check Available Funds
        if not await risk_manager.has_sufficient_funds(100.0):
            logger.warning("insufficient_funds_pausing_analysis", symbol=symbol, region=region)
            return None

        # 0b. Market Hours Check (Skip if Live and Closed)
        if settings.trading_mode == "live" and not is_market_open(symbol):
            logger.info("market_closed", symbol=symbol, region=region)
            return None
        
        # 1. Fetch Data Concurrently
        # Request 1 year of history so SMA-200 and MACD have enough data points
        price_snapshot, history, options, news = await asyncio.gather(
            self.market_data.get_current_price(symbol),
            self.market_data.get_history(symbol, period="1y"),
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

        # 2b. Earnings Calendar
        earnings = get_earnings_info(symbol)
        if earnings.is_within_warning_window:
            logger.warning("earnings_approaching", symbol=symbol,
                          earnings_date=earnings.earnings_date,
                          days_until=earnings.days_until_earnings)

        # 2c. Cross-Impact Analysis (correlated stocks)
        cross_impact = get_cross_impact(symbol)

        # 3. AI Analysis
        # Build earnings context for the AI
        earnings_context = None
        if earnings.earnings_date:
            earnings_context = {
                "next_earnings_date": earnings.earnings_date,
                "days_until_earnings": earnings.days_until_earnings,
                "eps_estimate": earnings.eps_estimate,
                "revenue_estimate": earnings.revenue_estimate,
            }
        
        # Build cross-impact context for the AI
        cross_impact_context = None
        if cross_impact.related_news_context:
            cross_impact_context = cross_impact.related_news_context
        
        ai_signal = await self.ai_analyzer.analyze(
            symbol=symbol,
            price=price_snapshot.price,
            tech=tech_indicators.model_dump(),
            news=news,
            options=options,
            earnings=earnings_context,
            cross_impact=cross_impact_context
        )
        
        logger.info("ai_signal_generated", symbol=symbol, region=region,
                     decision=ai_signal.decision, confidence=ai_signal.confidence)

        # Save Signal to DB
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
        if ai_signal.decision != "HOLD" and ai_signal.confidence >= 0.6:
            review_result = await self.ai_analyzer.review_trade(
                symbol=symbol,
                signal=ai_signal,
                price=price_snapshot.price,
                tech=tech_indicators.model_dump(),
                news=news
            )
            
            # Determine if we'll override the rejection
            was_overridden = False
            if not review_result.is_approved and settings.trading_mode != "live":
                was_overridden = True
            
            # Save review to activity DB
            await save_risk_review(RiskReview(
                symbol=symbol,
                original_decision=ai_signal.decision,
                original_confidence=ai_signal.confidence,
                review_decision=review_result.decision,
                review_reasoning=review_result.reasoning,
                was_overridden=was_overridden
            ))
            
            if not review_result.is_approved:
                if settings.trading_mode == "live":
                    logger.info("ai_risk_review_rejected", symbol=symbol, original_decision=ai_signal.decision)
                    return TradeSignal(symbol=symbol, action="HOLD", asset_type="STOCK", reason="AI Risk Manager Rejected", confidence=ai_signal.confidence)
                else:
                    logger.warning("ai_risk_review_overridden_paper_mode",
                                   symbol=symbol, original_decision=ai_signal.decision,
                                   confidence=ai_signal.confidence)

        # 4. Filter Low Confidence
        if ai_signal.confidence < 0.55:
            return TradeSignal(symbol=symbol, action="HOLD", asset_type="STOCK", reason="Low AI Confidence", confidence=ai_signal.confidence)

        # 5. Construct Trade Signal
        action = "HOLD"
        asset_type = "STOCK"
        quantity = 0 
        
        if "BUY" in ai_signal.decision:
            action = "BUY"
            if "CALL" in ai_signal.decision: asset_type = "CALL"
            elif "PUT" in ai_signal.decision: asset_type = "PUT"
            else: asset_type = "STOCK"
            
            # Dynamic position sizing based on regional capital and risk
            quantity = self._calculate_position_size(
                price=price_snapshot.price,
                risk_manager=risk_manager,
                stop_loss=ai_signal.stop_loss_suggestion
            )
            
            # Risk Check (region-specific)
            trade_req = TradeRequest(
                symbol=symbol,
                action="buy",
                quantity=quantity,
                price=price_snapshot.price, 
                stop_loss=ai_signal.stop_loss_suggestion
            )
            
            if not await risk_manager.validate_trade(trade_req):
                 return TradeSignal(symbol=symbol, action="HOLD", asset_type=asset_type, reason="Risk Check Failed", confidence=ai_signal.confidence)

        elif "SELL" in ai_signal.decision:
            action = "SELL"
            asset_type = "STOCK"
            
            position = risk_manager.get_position(symbol)
            if not position or position.quantity <= 0:
                logger.info("sell_signal_no_position", symbol=symbol, region=region)
                return TradeSignal(symbol=symbol, action="HOLD", asset_type=asset_type, reason="No position to sell", confidence=ai_signal.confidence)
            
            quantity = position.quantity
            
            trade_req = TradeRequest(
                symbol=symbol,
                action="sell",
                quantity=quantity,
                price=price_snapshot.price
            )
            
            if not await risk_manager.validate_trade(trade_req):
                return TradeSignal(symbol=symbol, action="HOLD", asset_type=asset_type, reason="Risk Check Failed", confidence=ai_signal.confidence)
        
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
        """Runs analysis on all watchlist symbols (deduplicated)."""
        unique_symbols = list(dict.fromkeys(watchlist))
        tasks = [self.analyze_symbol(sym) for sym in unique_symbols]
        results = await asyncio.gather(*tasks)
        return [r for r in results if r is not None and r.action != "HOLD"]
