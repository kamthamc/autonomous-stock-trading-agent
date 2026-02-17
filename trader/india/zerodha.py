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
            
            try:
                if settings.kite_access_token:
                    logger.info("kite_using_existing_access_token")
                    self.kite.set_access_token(settings.kite_access_token)
                    
                elif settings.kite_request_token and settings.kite_api_secret:
                    logger.info("kite_generating_session")
                    data = self.kite.generate_session(settings.kite_request_token, api_secret=settings.kite_api_secret)
                    self.kite.set_access_token(data["access_token"])
                    logger.info("kite_session_active")
                else:
                    logger.warning("kite_missing_credentials_for_login")
            except Exception as e:
                logger.error("kite_login_failed", error=str(e))

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
        if self.is_paper: 
            try:
                import yfinance as yf
                # yfinance needs suffixes .NS or .BO, symbol might differ
                # Zerodha symbols usually come in as RELIANCE.NS, normalized?
                # Base class normalize_symbol handles it.
                ticker = yf.Ticker(symbol)
                # fast_info is faster
                price = ticker.fast_info.last_price
                if not price:
                    # Fallback
                    hist = ticker.history(period="1d")
                    if not hist.empty:
                        price = hist['Close'].iloc[-1]
                    else:
                        price = 0.0
                return Decimal(str(price)) if price else Decimal("0.00")
            except:
                return Decimal("0.00")
        
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
        
        try:
            loop = asyncio.get_running_loop()
            
            # Fetch both Holdings (T+1) and Positions (Today/T+0)
            holdings_future = loop.run_in_executor(self._executor, self.kite.holdings)
            positions_future = loop.run_in_executor(self._executor, self.kite.positions)
            
            holdings, positions_resp = await asyncio.gather(holdings_future, positions_future)
            
            net_positions = positions_resp.get('net', [])
            
            combined_positions = {}
            
            # Process Holdings
            for h in holdings:
                symbol = h['tradingsymbol']
                exchange = h['exchange']
                if exchange == 'NSE' and not symbol.endswith('.NS'):
                    symbol = f"{symbol}.NS"
                elif exchange == 'BSE' and not symbol.endswith('.BO'):
                    symbol = f"{symbol}.BO"
                
                qty = Decimal(str(h['quantity']))
                if qty > 0:
                    avg_price = Decimal(str(h['average_price']))
                    curr_price = Decimal(str(h['last_price']))
                    combined_positions[symbol] = Position(
                        symbol=symbol,
                        quantity=qty,
                        average_price=avg_price,
                        current_price=curr_price,
                        market_value=qty * curr_price,
                        unrealized_pnl=(curr_price - avg_price) * qty
                    )

            # Process Today's Positions (merge with holdings)
            for p in net_positions:
                symbol = p['tradingsymbol']
                exchange = p['exchange']
                if exchange == 'NSE' and not symbol.endswith('.NS'):
                    symbol = f"{symbol}.NS"
                elif exchange == 'BSE' and not symbol.endswith('.BO'):
                    symbol = f"{symbol}.BO"
                
                qty = Decimal(str(p['quantity']))
                # If quantity is not 0 (open position)
                if qty != 0:
                    current_qty = qty
                    existing = combined_positions.get(symbol)
                    
                    avg_price = Decimal(str(p['average_price']))
                    curr_price = Decimal(str(p['last_price']))

                    if existing:
                        # Additive logic: Holdings (T+1) + Net Position (Today's change)
                        # e.g., Hold 10, Sell 2 -> 10 + (-2) = 8.
                        # e.g., Hold 10, Buy 5 -> 10 + 5 = 15.
                        
                        new_qty = existing.quantity + qty
                        
                        if new_qty != 0:
                            # Calculate weighted average price
                            total_cost = (existing.quantity * existing.average_price) + (qty * avg_price)
                            new_avg = total_cost / new_qty
                            
                            combined_positions[symbol] = Position(
                                symbol=symbol,
                                quantity=new_qty,
                                average_price=new_avg,
                                current_price=curr_price,
                                market_value=new_qty * curr_price,
                                unrealized_pnl=(curr_price - new_avg) * new_qty
                            )
                        else:
                            # Position closed out completely
                            del combined_positions[symbol]
                    else:
                        combined_positions[symbol] = Position(
                            symbol=symbol,
                            quantity=qty,
                            average_price=avg_price,
                            current_price=curr_price,
                            market_value=qty * curr_price,
                            unrealized_pnl=(curr_price - avg_price) * qty
                        )

            # Filter out zero/negative positions (closed out)
            return {k: v for k, v in combined_positions.items() if v.quantity > 0}
            
        except Exception as e:
            logger.error("kite_get_positions_failed", error=str(e))
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
