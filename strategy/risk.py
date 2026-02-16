from decimal import Decimal
from pydantic import BaseModel, Field
import structlog
from typing import Optional

# Import settings from config (assuming it's in parent directory, might need adjustment)
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

logger = structlog.get_logger()

class TradeRequest(BaseModel):
    symbol: str
    action: str # buy, sell
    quantity: int
    price: float
    stop_loss: Optional[float] = None

class RiskManager:
    def __init__(self, current_capital: float = settings.max_capital):
        self.current_capital = Decimal(str(current_capital))
        self.max_risk_per_trade = Decimal(str(settings.max_risk_per_trade))
        self.max_capital_per_trade = self.current_capital * Decimal("0.20") # Max 20% capital in one trade
        
        # Track simulated positions if paper trading
        self.positions = {} 

    async def validate_trade(self, request: TradeRequest) -> bool:
        """Checks if a trade request violates risk parameters."""
        
        total_cost = Decimal(str(request.price)) * Decimal(str(request.quantity))
        
        # 1. Check Capital Availability
        if total_cost > self.current_capital:
            logger.warning("risk_reject_insufficient_funds", 
                           cost=total_cost, capital=self.current_capital)
            return False

        # 2. Check Allocation Limit
        if total_cost > self.max_capital_per_trade:
             logger.warning("risk_reject_max_allocation", 
                           cost=total_cost, max_allowed=self.max_capital_per_trade)
             return False

        # 3. Check Stop Loss Risk (if provided)
        if request.stop_loss:
            risk_amount = (Decimal(str(request.price)) - Decimal(str(request.stop_loss))) * Decimal(str(request.quantity))
            allowed_risk = self.current_capital * self.max_risk_per_trade
            if risk_amount > allowed_risk:
                logger.warning("risk_reject_stop_loss_exceeded", 
                               risk=risk_amount, allowed=allowed_risk)
                return False

        return True

    def update_capital(self, amount: float):
        """Updates available capital (e.g. after a trade)."""
        self.current_capital += Decimal(str(amount))
        logger.info("capital_updated", new_balance=self.current_capital)

    async def has_sufficient_funds(self, amount: float) -> bool:
        """Checks if there is enough capital for an operation."""
        return self.current_capital >= Decimal(str(amount))
