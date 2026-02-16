from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from decimal import Decimal
from pydantic import BaseModel
from datetime import datetime

class Position(BaseModel):
    symbol: str
    quantity: Decimal
    average_price: Decimal
    current_price: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal

class Order(BaseModel):
    order_id: str
    symbol: str
    side: str  # buy, sell
    quantity: Decimal
    price: Optional[Decimal] = None
    status: str
    timestamp: datetime

class Broker(ABC):
    """Abstract base class for all broker implementations."""

    @abstractmethod
    def get_exchange_symbol(self, symbol: str) -> str:
        """
        Converts a canonical symbol (e.g. "AAPL", "RELIANCE.NS") into the
        format required by this broker's API.

        Each broker overrides this to handle its own symbol conventions.
        """
        pass

    @abstractmethod
    async def authenticate(self) -> bool:
        """Authenticates with the broker API."""
        pass

    @abstractmethod
    async def get_quote(self, symbol: str) -> Decimal:
        """Fetches the current price of a symbol."""
        pass

    @abstractmethod
    async def get_positions(self) -> Dict[str, Position]:
        """Returns a dictionary of current positions keyed by symbol."""
        pass

    @abstractmethod
    async def get_account_balance(self) -> Decimal:
        """Returns the available cash balance."""
        pass

    @abstractmethod
    async def place_order(self, symbol: str, quantity: Decimal, side: str, order_type: str = "market", price: Optional[Decimal] = None) -> Order:
        """Places a buy or sell order."""
        pass
    
    @abstractmethod
    async def get_option_chain(self, symbol: str) -> Any:
        # TODO: Define a standard OptionChain model
        pass
