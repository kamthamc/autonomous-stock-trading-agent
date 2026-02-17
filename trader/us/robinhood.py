import robin_stocks.robinhood as rh
import pyotp
from decimal import Decimal
from typing import Dict, Any, Optional
from datetime import datetime
import structlog
import asyncio
from concurrent.futures import ThreadPoolExecutor

from .base import USBroker
from ..base import Position, Order
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from agent_config import settings

logger = structlog.get_logger()

class RobinhoodTrader(USBroker):
    """
    Robinhood broker — US market.
    
    Symbol format: plain uppercase ticker (e.g. "AAPL", "TSLA").
    """

    def __init__(self):
        self._executor = ThreadPoolExecutor(max_workers=1)
        self.is_paper = settings.trading_mode == "paper"

    def get_exchange_symbol(self, symbol: str) -> str:
        """Robinhood uses plain uppercase tickers."""
        return self.normalize_symbol(symbol)

    async def authenticate(self) -> bool:
        if self.is_paper:
            logger.info("rh_paper_trading_auth_simulated")
            return True

        if not settings.rh_username or not settings.rh_password:
             logger.warning("rh_credentials_missing_skipping_login")
             return False
        
        try:
            loop = asyncio.get_running_loop()
            
            def login():
                totp = pyotp.TOTP(settings.rh_mfa_code).now() if settings.rh_mfa_code else None
                rh.login(settings.rh_username, settings.rh_password, mfa_code=totp)
                
            await loop.run_in_executor(self._executor, login)
            logger.info("rh_login_success")
            return True
        except Exception as e:
            logger.error("rh_login_failed", error=str(e))
            return False

    async def get_quote(self, symbol: str) -> Decimal:
        exchange_symbol = self.get_exchange_symbol(symbol)
        
        if self.is_paper:
            try:
                import yfinance as yf
                ticker = yf.Ticker(exchange_symbol)
                # fast_info is faster and reliable for US stocks
                price = ticker.fast_info.last_price
                if not price:
                    # Fallback
                    hist = ticker.history(period="1d")
                    price = hist['Close'].iloc[-1] if not hist.empty else 0.0
                return Decimal(str(price)) if price else Decimal("0.00")
            except:
                return Decimal("0.00")

        try:
            loop = asyncio.get_running_loop()
            quotes = await loop.run_in_executor(self._executor, lambda: rh.get_quotes(exchange_symbol))
            if quotes and len(quotes) > 0:
                return Decimal(str(quotes[0]['last_trade_price']))
            return Decimal("0.00")
        except Exception as e:
            logger.error("rh_get_quote_error", error=str(e))
            return Decimal("0.00")

    async def get_positions(self) -> Dict[str, Position]:
        if self.is_paper:
            return {}

        try:
            loop = asyncio.get_running_loop()
            my_positions = await loop.run_in_executor(self._executor, rh.build_holdings)
            
            positions = {}
            for symbol, data in my_positions.items():
                positions[symbol] = Position(
                    symbol=symbol,
                    quantity=Decimal(str(data['quantity'])),
                    average_price=Decimal(str(data['average_buy_price'])),
                    current_price=Decimal(str(data['price'])),
                    market_value=Decimal(str(data['equity'])),
                    unrealized_pnl=Decimal(str(data['equity_change']))
                )
            return positions
        except Exception as e:
            logger.error("rh_get_positions_error", error=str(e))
            return {}

    async def get_account_balance(self) -> Decimal:
        if self.is_paper:
            return Decimal(str(settings.us_max_capital))

        try:
            loop = asyncio.get_running_loop()
            profile = await loop.run_in_executor(self._executor, rh.load_account_profile)
            return Decimal(str(profile['portfolio_cash']))
        except Exception as e:
            logger.error("rh_get_balance_error", error=str(e))
            return Decimal("0.00")

    async def place_order(self, symbol: str, quantity: Decimal, side: str, order_type: str = "market", price: Optional[Decimal] = None) -> Order:
        exchange_symbol = self.get_exchange_symbol(symbol)
        timestamp = datetime.now()
        
        if self.is_paper:
            logger.info("rh_paper_order", symbol=exchange_symbol, side=side, quantity=quantity)
            return Order(
                order_id=f"paper_{timestamp.timestamp()}",
                symbol=exchange_symbol,
                side=side,
                quantity=quantity,
                price=price or Decimal("100.00"),
                status="filled",
                timestamp=timestamp
            )

        try:
            loop = asyncio.get_running_loop()
            
            def execute():
                if side == "buy":
                    return rh.order_buy_market(exchange_symbol, float(quantity))
                else:
                    return rh.order_sell_market(exchange_symbol, float(quantity))
            
            result = await loop.run_in_executor(self._executor, execute)
            
            return Order(
                order_id=result.get('id', 'unknown'),
                symbol=exchange_symbol,
                side=side,
                quantity=quantity,
                status=result.get('state', 'queued'),
                timestamp=timestamp
            )
        except Exception as e:
            logger.error("rh_order_failed", error=str(e))
            return Order(order_id="error", symbol=exchange_symbol, side=side, quantity=quantity, status="failed", timestamp=timestamp)

    async def get_option_chain(self, symbol: str) -> list:
         return []
