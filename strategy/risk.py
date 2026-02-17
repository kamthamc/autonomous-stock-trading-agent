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
    high_watermark: float = 0.0       # Highest price since entry
    trailing_stop_level: float = 0.0  # Current trailing stop price
    scale_outs: int = 0               # Number of partial sells executed
    min_upside_target: float = 0.0    # Min % gain before considering partial sell

class RiskManager:
    """
    Risk manager for a single region's capital pool.
    
    Create one per region (US, IN) with region-specific capital and trade limits.
    """
    
    def __init__(self, 
                 region: str = "US",
                 max_capital: float = settings.max_capital,
                 max_per_trade: Optional[float] = None,
                 min_trade_value: float = 0.0,
                 max_risk_per_trade: Optional[float] = None):
        
        # Load style profile for defaults
        profile = settings.active_style_profile
        
        self.region = region
        self.current_capital = Decimal(str(max_capital))
        self.initial_capital = Decimal(str(max_capital))
        self.max_risk_per_trade = Decimal(str(max_risk_per_trade if max_risk_per_trade is not None else profile.max_risk_per_trade))
        self.min_trade_value = Decimal(str(min_trade_value))
        
        # Per-trade allocation limit
        if max_per_trade is not None:
            self.max_capital_per_trade = Decimal(str(max_per_trade))
        else:
            self.max_capital_per_trade = self.current_capital * Decimal("0.20")  # Default: 20% of capital
        
        # Position tracking
        self.positions: Dict[str, PositionRecord] = {}
        
        # Circuit breaker: daily loss limit (from style profile)
        self._daily_loss = Decimal("0.0")
        self._daily_trade_count = 0
        self._current_date = date.today()
        self.max_daily_loss = self.initial_capital * Decimal(str(profile.circuit_breaker_daily_loss_pct))
        self.max_daily_trades = profile.max_daily_trades
        
        # Trailing stop / partial sell config (from style profile)
        self.trailing_stop_pct = profile.trailing_stop_pct
        self.partial_sell_pct = profile.partial_sell_pct
        self.max_scale_outs = profile.max_scale_outs
        self.min_upside_target_pct = profile.min_upside_target_pct
        
        logger.info("risk_manager_initialized", 
                     region=region,
                     style=profile.name,
                     capital=str(self.current_capital),
                     max_per_trade=str(self.max_capital_per_trade),
                     max_risk_pct=str(self.max_risk_per_trade),
                     trailing_stop_pct=self.trailing_stop_pct,
                     min_upside=self.min_upside_target_pct,
                     min_trade_value=str(self.min_trade_value))

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

        # 1.5 Check Minimum Trade Value (Avoid charges inefficiency)
        if total_cost < self.min_trade_value:
             logger.warning("risk_reject_min_trade_value", region=self.region,
                           cost=str(total_cost), min_required=str(self.min_trade_value))
             return False

        # 2. Check Total Allocation Limit (Existing + New)
        existing_value = Decimal("0.0")
        if request.symbol in self.positions:
             pos = self.positions[request.symbol]
             # Estimate current value of holding using the current trade price
             existing_value = Decimal(str(pos.quantity)) * Decimal(str(request.price))

        projected_exposure = existing_value + total_cost
        
        if projected_exposure > self.max_capital_per_trade:
             logger.warning("risk_reject_max_allocation", region=self.region,
                           projected_exposure=str(projected_exposure), 
                           max_allowed=str(self.max_capital_per_trade),
                           existing_value=str(existing_value),
                           new_cost=str(total_cost))
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

    def sync_from_broker(self, positions: Dict[str, 'Position'], balance: Decimal):
        """
        Syncs the internal risk manager state with the broker's actual data.
        
        Args:
            positions: Dictionary of active positions from the broker.
            balance: Current available cash balance from the broker.
        """
        self.current_capital = balance
        
        # Preserve existing watermark / trailing stop data for known symbols
        old_positions = dict(self.positions)
        self.positions.clear()
        
        for symbol, pos in positions.items():
            old = old_positions.get(symbol)
            current_price = float(pos.current_price) if hasattr(pos, 'current_price') else float(pos.average_price)
            
            self.positions[symbol] = PositionRecord(
                symbol=symbol,
                quantity=int(pos.quantity),
                average_price=float(pos.average_price),
                high_watermark=max(current_price, old.high_watermark if old else 0.0),
                trailing_stop_level=old.trailing_stop_level if old else 0.0,
                scale_outs=old.scale_outs if old else 0,
                min_upside_target=old.min_upside_target if old else self.min_upside_target_pct,
            )
            
        logger.info("risk_manager_synced", region=self.region, 
                    balance=str(self.current_capital), 
                    positions_count=len(self.positions))

    # ──────────────────────────────────────────────
    # Trailing Stop & Partial Exit
    # ──────────────────────────────────────────────

    def update_trailing_stop(self, symbol: str, current_price: float) -> Optional[float]:
        """
        Updates the trailing stop for a position.

        The trailing stop ratchets UP as price makes new highs, but never
        moves down.  Returns the new trailing stop level, or None if no
        position is held.
        """
        pos = self.positions.get(symbol)
        if not pos or pos.quantity <= 0:
            return None

        # Update high watermark
        if current_price > pos.high_watermark:
            pos.high_watermark = current_price

        # Calculate new trailing stop level
        new_stop = pos.high_watermark * (1.0 - self.trailing_stop_pct)

        # Only ratchet UP, never down
        if new_stop > pos.trailing_stop_level:
            pos.trailing_stop_level = new_stop
            logger.debug("trailing_stop_updated", symbol=symbol,
                        high_watermark=f"{pos.high_watermark:.2f}",
                        trailing_stop=f"{pos.trailing_stop_level:.2f}")

        return pos.trailing_stop_level

    def get_partial_sell_quantity(self, symbol: str, current_price: float) -> int:
        """
        Determines how many shares to sell for a partial exit.

        Returns 0 if no partial sell is warranted (below min upside target
        or max scale-outs already reached).
        """
        pos = self.positions.get(symbol)
        if not pos or pos.quantity <= 0:
            return 0

        # Check if we've exceeded max scale-outs
        if pos.scale_outs >= self.max_scale_outs:
            return 0

        # Check if min upside target is met
        if pos.average_price <= 0:
            return 0
        pnl_pct = (current_price - pos.average_price) / pos.average_price
        if pnl_pct < pos.min_upside_target:
            return 0

        # Calculate partial sell quantity
        sell_qty = max(1, int(pos.quantity * self.partial_sell_pct))
        # Never sell the last share via partial sell — leave for trailing stop
        sell_qty = min(sell_qty, pos.quantity - 1) if pos.quantity > 1 else 0
        return sell_qty

    def record_partial_sell(self, symbol: str, quantity: int, price: float):
        """Records a partial sell and increments the scale-out counter."""
        pos = self.positions.get(symbol)
        if pos:
            pos.scale_outs += 1
            # Raise the min upside target for next scale-out
            pos.min_upside_target += self.min_upside_target_pct
            logger.info("partial_sell_recorded", symbol=symbol,
                       scale_out_number=pos.scale_outs,
                       next_target=f"{pos.min_upside_target*100:.1f}%")
        self.record_trade(symbol, "sell", quantity, price)
