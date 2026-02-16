import structlog
from decimal import Decimal
from typing import Dict, Any, Optional
from datetime import datetime
from breeze_connect import BreezeConnect
from config import settings
from .base import Broker, Order, Position

logger = structlog.get_logger()

class ICICITrader(Broker):
    """
    ICICI Direct Broker Implementation using breeze-connect.
    """
    def __init__(self):
        self.breeze = BreezeConnect(api_key=settings.icici_api_key)
        self.is_authenticated = False
        self.session_token = settings.icici_session_token
        self.secret_key = settings.icici_secret_key

    async def authenticate(self) -> bool:
        """
        Authenticates with ICICI Direct API.
        Requires a valid session_token generate from the login URL.
        """
        if not settings.icici_api_key or not self.session_token:
            logger.warning("icici_credentials_missing")
            return False

        try:
            self.breeze.generate_session(
                api_secret=self.secret_key,
                session_token=self.session_token
            )
            self.is_authenticated = True
            logger.info("icici_login_successful")
            return True
        except Exception as e:
            logger.error("icici_login_failed", error=str(e))
            return False

    async def get_quote(self, symbol: str) -> Decimal:
        """
        Fetches LTP for a symbol. 
        Symbol format expected: "INFY" (Automatically maps to NSE).
        """
        if not self.is_authenticated: return Decimal(0)
        try:
            # Defaulting to NSE Equity
            data = self.breeze.get_quotes(
                stock_code=symbol,
                exchange_code="NSE",
                expiry_date="",
                product_type="cash",
                right="",
                strike_price=""
            )
            if data and 'Success' in data and data['Success']:
                # Parse LTP. Structure varies, usually check 'ltt' or list
                # Breeze API returns a list in 'Success' usually
                 quotes = data['Success']
                 if quotes and len(quotes) > 0:
                     return Decimal(str(quotes[0]['ltp']))
            return Decimal(0)
        except Exception as e:
            logger.error("icici_get_quote_error", symbol=symbol, error=str(e))
            return Decimal(0)

    async def get_positions(self) -> Dict[str, Position]:
        if not self.is_authenticated: return {}
        try:
            response = self.breeze.get_portfolio_positions()
            positions = {}
            if response and 'Success' in response and response['Success']:
                for p in response['Success']:
                    # Map breeze fields to Position model
                    symbol = p.get('stock_code', 'UNKNOWN')
                    qty = Decimal(str(p.get('quantity', 0)))
                    avg_price = Decimal(str(p.get('average_price', 0)))
                    market_val = Decimal(0) # Breeze might not send MV directly
                    
                    # We might need to fetch current price to calc MV/PnL if not provided
                    # For now simplified
                    
                    positions[symbol] = Position(
                        symbol=symbol,
                        quantity=qty,
                        average_price=avg_price,
                        current_price=avg_price, # Placeholder
                        market_value=market_val,
                        unrealized_pnl=Decimal(0)
                    )
            return positions
        except Exception as e:
            logger.error("icici_get_positions_error", error=str(e))
            return {}

    async def get_account_balance(self) -> Decimal:
        if not self.is_authenticated: return Decimal(0)
        try:
            response = self.breeze.get_funds()
            if response and 'Success' in response and response['Success']:
                funds = response['Success']
                # Breeze returns generic funds details
                return Decimal(str(funds.get('bank_balance', 0)))
            return Decimal(0)
        except Exception as e:
            logger.error("icici_get_balance_error", error=str(e))
            return Decimal(0)

    async def place_order(self, symbol: str, quantity: Decimal, side: str, order_type: str = "market", price: Optional[Decimal] = None) -> Order:
        if not self.is_authenticated:
            return Order(order_id="N/A", symbol=symbol, side=side, quantity=quantity, status="REJECTED", timestamp=datetime.now())

        try:
            action = "buy" if side.lower() == "buy" else "sell"
            
            # Place Order
            response = self.breeze.place_order(
                stock_code=symbol,
                exchange_code="NSE",
                product="cash", # CNC/Delivery
                action=action,
                order_type=order_type,
                stoploss="0",
                quantity=str(int(quantity)),
                price=str(price) if price else "0",
                validity="day"
            )
            
            status = "FAILED"
            order_id = "N/A"
            
            if response and 'Success' in response and response['Success']:
                order_id = response['Success']['order_id']
                status = "PENDING"
                logger.info("icici_order_placed", order_id=order_id, symbol=symbol)
            else:
                 logger.error("icici_order_failed", response=response)

            return Order(
                order_id=order_id,
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=price,
                status=status,
                timestamp=datetime.now()
            )
        except Exception as e:
            logger.error("icici_place_order_error", error=str(e))
            return Order(order_id="ERROR", symbol=symbol, side=side, quantity=quantity, status="ERROR", timestamp=datetime.now())

    async def get_option_chain(self, symbol: str) -> Any:
        # Breeze has get_option_chain_quotes
        # Not fully implemented yet
        return []
