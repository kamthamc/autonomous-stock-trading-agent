"""
Broker Router — Routes trade orders to the correct broker based on market region.

Regions:
  - US: Symbols without region suffix (e.g. AAPL, TSLA, SPY)
  - IN (India): Symbols ending with .NS (NSE) or .BO (BSE)

The router respects the user's broker preferences configured in agent_config.py:
  - us_preferred_broker: Which broker to use for US trades
  - india_preferred_broker: Which broker to prefer for Indian trades
  - india_fallback_broker: Fallback if the preferred India broker is unavailable
"""

import structlog
from typing import Dict, Optional, Literal
from trader.base import Broker
from strategy.market_hours import is_market_open

logger = structlog.get_logger()

# Type alias for market region
MarketRegion = Literal["US", "IN"]


class BrokerRouter:
    """
    Manages broker instances by region and routes orders to the appropriate broker.
    
    Symbol conversion is NOT the router's responsibility — each broker handles
    its own symbol format internally via get_exchange_symbol().
    """

    def __init__(self):
        # Brokers keyed by their config name (e.g. "robinhood", "zerodha", "icici")
        self._us_brokers: Dict[str, Broker] = {}
        self._india_brokers: Dict[str, Broker] = {}
        
        # Preferences (set during init from config)
        self.us_preferred: Optional[str] = None
        self.india_preferred: Optional[str] = None
        self.india_fallback: Optional[str] = None

    def register_broker(self, name: str, broker: Broker, region: MarketRegion):
        """Register an authenticated broker for a specific region."""
        if region == "US":
            self._us_brokers[name] = broker
            logger.info("broker_registered", name=name, region="US")
        elif region == "IN":
            self._india_brokers[name] = broker
            logger.info("broker_registered", name=name, region="IN")

    def set_preferences(self, us_preferred: str, india_preferred: str, india_fallback: Optional[str] = None):
        """Set broker preferences from config."""
        self.us_preferred = us_preferred
        self.india_preferred = india_preferred
        self.india_fallback = india_fallback
        logger.info("broker_preferences_set", 
                     us=us_preferred, india=india_preferred, india_fallback=india_fallback)

    @staticmethod
    def detect_region(symbol: str) -> MarketRegion:
        """
        Determines the market region from a symbol string.
        
        - Symbols ending with .NS or .BO → India
        - Everything else → US
        """
        upper = symbol.upper()
        if upper.endswith(".NS") or upper.endswith(".BO"):
            return "IN"
        return "US"

    def get_broker_for_symbol(self, symbol: str) -> Optional[Broker]:
        """
        Returns the best available broker for a given symbol's region.
        
        The caller passes the canonical symbol directly to the broker's methods
        (get_quote, place_order, etc.) — the broker handles symbol format
        conversion internally via get_exchange_symbol().
        """
        region = self.detect_region(symbol)

        if region == "US":
            return self._get_us_broker()
        else:
            return self._get_india_broker()

    def _get_us_broker(self) -> Optional[Broker]:
        """Get the preferred US broker, if available."""
        if self.us_preferred and self.us_preferred in self._us_brokers:
            return self._us_brokers[self.us_preferred]
        # Fallback: return any available US broker
        if self._us_brokers:
            return next(iter(self._us_brokers.values()))
        return None

    def _get_india_broker(self) -> Optional[Broker]:
        """Get the preferred India broker, falling back to the secondary."""
        if self.india_preferred and self.india_preferred in self._india_brokers:
            return self._india_brokers[self.india_preferred]
        if self.india_fallback and self.india_fallback in self._india_brokers:
            logger.info("india_broker_fallback", preferred=self.india_preferred, using=self.india_fallback)
            return self._india_brokers[self.india_fallback]
        # Last resort: any available India broker
        if self._india_brokers:
            return next(iter(self._india_brokers.values()))
        return None

    def is_market_open_for_symbol(self, symbol: str) -> bool:
        """Checks if the relevant market is open for this symbol."""
        return is_market_open(symbol)

    @property
    def has_us_broker(self) -> bool:
        return len(self._us_brokers) > 0

    @property
    def has_india_broker(self) -> bool:
        return len(self._india_brokers) > 0

    @property
    def all_broker_names(self) -> list:
        """Returns names of all registered brokers."""
        us = [f"{name} (US)" for name in self._us_brokers]
        india = [f"{name} (IN)" for name in self._india_brokers]
        return us + india
