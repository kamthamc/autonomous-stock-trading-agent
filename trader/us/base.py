"""
US Market Broker Base Class.

All US broker implementations (e.g. Robinhood) should inherit from this
to get US-specific symbol handling and market conventions.

Each concrete US broker overrides `get_exchange_symbol()` to produce the
format its API expects.
"""

from abc import ABC
from trader.base import Broker


class USBroker(Broker, ABC):
    """
    Abstract base for US market brokers.
    
    Provides:
    - US symbol normalization
    - Region and exchange constants
    """

    REGION = "US"
    CURRENCY = "USD"
    EXCHANGES = ["NYSE", "NASDAQ", "AMEX"]

    @staticmethod
    def normalize_symbol(symbol: str) -> str:
        """
        Strips any non-US suffixes to get a clean US ticker.

        Examples:
            "AAPL"    -> "AAPL"
            "aapl"    -> "AAPL"
        """
        return symbol.upper().strip()

    @staticmethod
    def is_us_symbol(symbol: str) -> bool:
        """Returns True if the symbol is a US market symbol (no .NS or .BO suffix)."""
        upper = symbol.upper()
        return not (upper.endswith(".NS") or upper.endswith(".BO"))
