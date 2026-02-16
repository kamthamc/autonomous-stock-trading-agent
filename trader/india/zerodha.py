from kiteconnect import KiteConnect
from decimal import Decimal
from typing import Dict, Any, Optional
from datetime import datetime
import structlog
import asyncio
from concurrent.futures import ThreadPoolExecutor

from .base import IndiaBroker
from ..base import Position, Order
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from agent_config import settings

logger = structlog.get_logger()

class ZerodhaTrader(IndiaBroker):
    """
    Zerodha / Kite Connect broker — Indian market.
    
    Symbol format: "EXCHANGE:SYMBOL" (e.g. "NSE:RELIANCE", "BSE:TCS").
    """

    def __init__(self):
        self._executor = ThreadPoolExecutor(max_workers=1)
        self.is_paper = settings.trading_mode == "paper"
        
        if not self.is_paper:
            self.kite = KiteConnect(api_key=settings.kite_api_key)
            if settings.kite_access_token:
                self.kite.set_access_token(settings.kite_access_token)

    def get_exchange_symbol(self, symbol: str) -> str:
        """
        Kite Connect uses EXCHANGE:SYMBOL format.
        
        Examples:
            "RELIANCE.NS" -> "NSE:RELIANCE"
            "TCS.BO"      -> "BSE:TCS"
            "INFY"        -> "NSE:INFY"
        """
        clean = self.normalize_symbol(symbol)
        exchange = self.detect_exchange(symbol)
        return f"{exchange}:{clean}"

    async def authenticate(self) -> bool:
        if self.is_paper:
            logger.info("kite_paper_auth_simulated")
            return True
        return True

    async def get_quote(self, symbol: str) -> Decimal:
        if self.is_paper: return Decimal("0.00")
        
        try:
            loop = asyncio.get_running_loop()
            exchange_symbol = self.get_exchange_symbol(symbol)
            quote = await loop.run_in_executor(self._executor, lambda: self.kite.quote(exchange_symbol))
            return Decimal(str(quote[exchange_symbol]['last_price']))
        except Exception as e:
            logger.error("kite_get_quote_error", error=str(e))
            return Decimal("0.00")

    async def get_positions(self) -> Dict[str, Position]:
        if self.is_paper: return {}
        return {}

    async def get_account_balance(self) -> Decimal:
        if self.is_paper: return Decimal(str(settings.india_max_capital))
        try:
             loop = asyncio.get_running_loop()
             margins = await loop.run_in_executor(self._executor, self.kite.margins)
             return Decimal(str(margins['equity']['available']['cash']))
        except Exception:
            return Decimal("0.00")

    async def place_order(self, symbol: str, quantity: Decimal, side: str, order_type: str = "market", price: Optional[Decimal] = None) -> Order:
        trade_symbol = self.normalize_symbol(symbol)
        exchange = self.detect_exchange(symbol)
        timestamp = datetime.now()
        
        if self.is_paper:
             logger.info("kite_paper_order", symbol=trade_symbol, side=side, exchange=exchange)
             return Order(
                 order_id=f"paper_kite_{timestamp.timestamp()}",
                 symbol=trade_symbol,
                 side=side,
                 quantity=quantity,
                 status="filled",
                 timestamp=timestamp
             )
        
        try:
            loop = asyncio.get_running_loop()
            transaction_type = self.kite.TRANSACTION_TYPE_BUY if side.lower() == "buy" else self.kite.TRANSACTION_TYPE_SELL
            kite_order_type = self.kite.ORDER_TYPE_MARKET if order_type == "market" else self.kite.ORDER_TYPE_LIMIT
            kite_exchange = self.kite.EXCHANGE_NSE if exchange == "NSE" else self.kite.EXCHANGE_BSE
            
            def execute():
                return self.kite.place_order(
                    variety=self.kite.VARIETY_REGULAR,
                    exchange=kite_exchange,
                    tradingsymbol=trade_symbol,
                    transaction_type=transaction_type,
                    quantity=int(quantity),
                    product=self.kite.PRODUCT_CNC,
                    order_type=kite_order_type,
                    price=float(price) if price and kite_order_type != self.kite.ORDER_TYPE_MARKET else None
                )
            
            order_id = await loop.run_in_executor(self._executor, execute)
            logger.info("kite_order_placed", order_id=order_id, symbol=trade_symbol)
            return Order(
                order_id=str(order_id),
                symbol=trade_symbol,
                side=side,
                quantity=quantity,
                status="placed",
                timestamp=timestamp
            )
        except Exception as e:
            logger.error("kite_order_failed", error=str(e))
            return Order(order_id="error", symbol=trade_symbol, side=side, quantity=quantity, status="failed", timestamp=timestamp)

    async def get_option_chain(self, symbol: str) -> list:
        return []
