"""
Indian Market Broker Base Class.

All India broker implementations (e.g. Zerodha, ICICI Direct) should inherit
from this to get India-specific symbol handling and market conventions.

Each concrete Indian broker overrides `get_exchange_symbol()` to produce the
format its specific API expects (e.g. "NSE:RELIANCE" for Kite, "RELIANCE" for Breeze).
"""

from abc import ABC
from trader.base import Broker


class IndiaBroker(Broker, ABC):
    """
    Abstract base for Indian market brokers.
    
    Provides:
    - Indian symbol normalization (strips .NS/.BO suffixes)
    - Exchange detection from symbol suffix
    - Region and currency constants
    
    Concrete brokers (Zerodha, ICICI) override `get_exchange_symbol()`.
    """

    REGION = "IN"
    CURRENCY = "INR"
    EXCHANGES = ["NSE", "BSE"]

    @staticmethod
    def normalize_symbol(symbol: str) -> str:
        """
        Strips exchange suffixes to get a clean Indian stock code.

        Examples:
            "RELIANCE.NS" -> "RELIANCE"
            "TCS.BO"      -> "TCS"
            "INFY"        -> "INFY"
        """
        return symbol.upper().replace(".NS", "").replace(".BO", "").strip()

    @staticmethod
    def detect_exchange(symbol: str) -> str:
        """
        Detects the exchange from the symbol suffix.
        Defaults to NSE if no suffix is present.
        
        Examples:
            "RELIANCE.NS" -> "NSE"
            "RELIANCE.BO" -> "BSE"
            "RELIANCE"    -> "NSE"
        """
        upper = symbol.upper()
        if upper.endswith(".BO"):
            return "BSE"
        return "NSE"

    @staticmethod
    def is_indian_symbol(symbol: str) -> bool:
        """Returns True if the symbol has an Indian exchange suffix (.NS or .BO)."""
        upper = symbol.upper()
        return upper.endswith(".NS") or upper.endswith(".BO")
