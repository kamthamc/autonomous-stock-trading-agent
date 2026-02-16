from decimal import Decimal
from pydantic import BaseModel, Field
import structlog
from typing import Dict, Optional
from datetime import datetime, date

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent_config import settings

logger = structlog.get_logger()

class TradeRequest(BaseModel):
    symbol: str
    action: str # buy, sell
    quantity: int
    price: float
    stop_loss: Optional[float] = None

class PositionRecord(BaseModel):
    """Tracks a held position for a single symbol."""
    symbol: str
    quantity: int = 0
    average_price: float = 0.0

class RiskManager:
    """
    Risk manager for a single region's capital pool.
    
    Create one per region (US, IN) with region-specific capital and trade limits.
    """
    
    def __init__(self, 
                 region: str = "US",
                 max_capital: float = settings.max_capital,
                 max_per_trade: Optional[float] = None,
                 max_risk_per_trade: float = settings.max_risk_per_trade):
        
        self.region = region
        self.current_capital = Decimal(str(max_capital))
        self.initial_capital = Decimal(str(max_capital))
        self.max_risk_per_trade = Decimal(str(max_risk_per_trade))
        
        # Per-trade allocation limit
        if max_per_trade is not None:
            self.max_capital_per_trade = Decimal(str(max_per_trade))
        else:
            self.max_capital_per_trade = self.current_capital * Decimal("0.20")  # Default: 20% of capital
        
        # Position tracking
        self.positions: Dict[str, PositionRecord] = {}
        
        # Circuit breaker: daily loss limit
        self._daily_loss = Decimal("0.0")
        self._daily_trade_count = 0
        self._current_date = date.today()
        self.max_daily_loss = self.initial_capital * Decimal("0.05")  # 5% of initial capital
        self.max_daily_trades = 50
        
        logger.info("risk_manager_initialized", 
                     region=region,
                     capital=str(self.current_capital),
                     max_per_trade=str(self.max_capital_per_trade))

    def _reset_daily_counters_if_new_day(self):
        """Resets daily loss and trade counters at the start of a new trading day."""
        today = date.today()
        if today != self._current_date:
            logger.info("daily_counters_reset", region=self.region,
                        previous_date=str(self._current_date), 
                        daily_loss=str(self._daily_loss), daily_trades=self._daily_trade_count)
            self._daily_loss = Decimal("0.0")
            self._daily_trade_count = 0
            self._current_date = today

    def is_circuit_breaker_triggered(self) -> bool:
        """Returns True if the circuit breaker is active (daily limits exceeded)."""
        self._reset_daily_counters_if_new_day()
        
        if self._daily_loss >= self.max_daily_loss:
            logger.warning("circuit_breaker_daily_loss", region=self.region,
                           daily_loss=str(self._daily_loss), limit=str(self.max_daily_loss))
            return True
        
        if self._daily_trade_count >= self.max_daily_trades:
            logger.warning("circuit_breaker_max_trades", region=self.region,
                           count=self._daily_trade_count, limit=self.max_daily_trades)
            return True
        
        return False

    async def validate_trade(self, request: TradeRequest) -> bool:
        """Checks if a trade request violates risk parameters."""
        
        # Circuit breaker check
        if self.is_circuit_breaker_triggered():
            return False

        total_cost = Decimal(str(request.price)) * Decimal(str(request.quantity))
        
        if request.action.lower() == "sell":
            # Check that we actually hold enough of this symbol
            position = self.positions.get(request.symbol)
            if not position or position.quantity < request.quantity:
                held = position.quantity if position else 0
                logger.warning("risk_reject_no_position", region=self.region,
                               symbol=request.symbol, requested=request.quantity, held=held)
                return False
            return True

        # BUY checks:

        # 1. Check Capital Availability
        if total_cost > self.current_capital:
            logger.warning("risk_reject_insufficient_funds", region=self.region,
                           cost=total_cost, capital=self.current_capital)
            return False

        # 2. Check Per-Trade Allocation Limit
        if total_cost > self.max_capital_per_trade:
             logger.warning("risk_reject_max_allocation", region=self.region,
                           cost=total_cost, max_allowed=self.max_capital_per_trade)
             return False

        # 3. Check Stop Loss Risk (if provided)
        if request.stop_loss:
            risk_amount = (Decimal(str(request.price)) - Decimal(str(request.stop_loss))) * Decimal(str(request.quantity))
            allowed_risk = self.current_capital * self.max_risk_per_trade
            if risk_amount > allowed_risk:
                logger.warning("risk_reject_stop_loss_exceeded", region=self.region,
                               risk=risk_amount, allowed=allowed_risk)
                return False

        return True

    def record_trade(self, symbol: str, action: str, quantity: int, price: float):
        """
        Updates capital and positions after a trade is executed.
        Must be called after every successful order placement.
        """
        self._reset_daily_counters_if_new_day()
        
        cost = Decimal(str(price)) * Decimal(str(quantity))
        
        if action.lower() == "buy":
            self.current_capital -= cost
            
            if symbol in self.positions:
                pos = self.positions[symbol]
                total_qty = pos.quantity + quantity
                if total_qty > 0:
                    pos.average_price = float(
                        (Decimal(str(pos.average_price)) * Decimal(str(pos.quantity)) + cost) / Decimal(str(total_qty))
                    )
                pos.quantity = total_qty
            else:
                self.positions[symbol] = PositionRecord(
                    symbol=symbol, quantity=quantity, average_price=price
                )
            
            self._daily_trade_count += 1
            logger.info("trade_recorded_buy", region=self.region, symbol=symbol, quantity=quantity, 
                        price=price, remaining_capital=str(self.current_capital))

        elif action.lower() == "sell":
            self.current_capital += cost
            
            pnl = Decimal("0.0")
            if symbol in self.positions:
                pos = self.positions[symbol]
                pnl = (Decimal(str(price)) - Decimal(str(pos.average_price))) * Decimal(str(quantity))
                pos.quantity -= quantity
                if pos.quantity <= 0:
                    del self.positions[symbol]
            
            if pnl < 0:
                self._daily_loss += abs(pnl)
            
            self._daily_trade_count += 1
            logger.info("trade_recorded_sell", region=self.region, symbol=symbol, quantity=quantity, 
                        price=price, pnl=str(pnl), remaining_capital=str(self.current_capital))

    def get_position(self, symbol: str) -> Optional[PositionRecord]:
        """Returns the current position for a symbol, or None if not held."""
        return self.positions.get(symbol)

    def update_capital(self, amount: float):
        """Manually adjusts available capital (e.g. deposit/withdrawal)."""
        self.current_capital += Decimal(str(amount))
        logger.info("capital_updated", region=self.region, new_balance=str(self.current_capital))

    async def has_sufficient_funds(self, amount: float) -> bool:
        """Checks if there is enough capital for an operation."""
        return self.current_capital >= Decimal(str(amount))
