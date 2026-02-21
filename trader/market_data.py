import asyncio
import yfinance as yf
import pandas as pd
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime
import structlog
from concurrent.futures import ThreadPoolExecutor

logger = structlog.get_logger()

class MarketSnapshot(BaseModel):
    symbol: str
    price: float
    timestamp: datetime
    volume: int
    open: float
    high: float
    low: float
    close: float

class OptionData(BaseModel):
    symbol: str
    strike: float
    expiry: str
    option_type: str  # "call" or "put"
    last_price: float
    bid: float = 0.0
    ask: float = 0.0
    volume: int
    open_interest: int
    implied_volatility: float

class MarketDataFetcher:
    def __init__(self, broker: Optional[Any] = None):
        self._executor = ThreadPoolExecutor(max_workers=5)
        self.broker = broker

    async def get_current_price(self, symbol: str) -> Optional[MarketSnapshot]:
        """Fetches current market data snapshot. Prioritizes Broker API for real-time data."""
        try:
            price = 0.0
            # 1. Try Broker First (Real-time)
            if self.broker:
                try:
                    # broker.get_quote should return a Decimal or float
                    price_decimal = await self.broker.get_quote(symbol)
                    price = float(price_decimal)
                except Exception:
                    pass # Fallback to yfinance

            loop = asyncio.get_running_loop()
            ticker = await loop.run_in_executor(self._executor, yf.Ticker, symbol)
            
            # Use broker price if available (and > 0), else yfinance
            final_price = price
            if final_price <= 0:
                try:
                    # fast_info access can fail/block, run in executor
                    final_price = await loop.run_in_executor(self._executor, lambda: ticker.fast_info.last_price)
                except Exception:
                    final_price = 0.0
            
            # For Volume/OHLC we still need history from yfinance usually
            history = await loop.run_in_executor(self._executor, lambda: ticker.history(period="1d"))
            
            if history.empty:
                 # Raise exception to trigger retry logic
                 raise ValueError(f"No history data found for {symbol}")
            
            row = history.iloc[-1]
            
            if final_price == 0.0:
                final_price = float(row['Close'])
            
            return MarketSnapshot(
                symbol=symbol,
                price=final_price,
                timestamp=datetime.now(),
                volume=int(row['Volume']),
                open=float(row['Open']),
                high=float(row['High']),
                low=float(row['Low']),
                close=float(row['Close'])
            )
        except Exception as e:
            # Retry with .NS for Indian stocks if simplified ticker fails
            if not symbol.endswith(".NS") and not symbol.endswith(".BO") and ("currentTradingPeriod" in str(e) or "No data found" in str(e) or "delisted" in str(e)):
                try:
                    logger.info("retrying_with_ns_suffix", symbol=symbol)
                    return await self.get_current_price(f"{symbol}.NS")
                except Exception:
                    pass
            
            logger.error("fetch_price_error", symbol=symbol, error=str(e))
            return None

    async def get_history(self, symbol: str, period: str = "1mo", interval: str = "1d") -> pd.DataFrame:
        """Fetches historical OHLCV data."""
        try:
            loop = asyncio.get_running_loop()
            ticker = await loop.run_in_executor(self._executor, yf.Ticker, symbol)
            history = await loop.run_in_executor(self._executor, lambda: ticker.history(period=period, interval=interval))
            return history
        except Exception as e:
            # Retry with .NS
            if not symbol.endswith(".NS") and not symbol.endswith(".BO"):
                 try:
                    return await self.get_history(f"{symbol}.NS", period, interval)
                 except Exception:
                    pass
            
            logger.error("fetch_history_error", symbol=symbol, error=str(e))
            return pd.DataFrame()

    async def get_option_chain(self, symbol: str) -> List[OptionData]:
        """Fetches option chain data (Current Expiry)."""
        try:
            loop = asyncio.get_running_loop()
            ticker = await loop.run_in_executor(self._executor, yf.Ticker, symbol)
            
            # Get next expiry
            expirations = ticker.options
            if not expirations:
                return []
            
            next_expiry = expirations[0]
            
            opts = await loop.run_in_executor(self._executor, lambda: ticker.option_chain(next_expiry))
            
            options_list = []
            
            # Process Calls
            for _, row in opts.calls.iterrows():
                options_list.append(OptionData(
                    symbol=symbol,
                    strike=row['strike'],
                    expiry=next_expiry,
                    option_type="call",
                    last_price=row['lastPrice'],
                    bid=row.get('bid', 0.0),
                    ask=row.get('ask', 0.0),
                    volume=int(row['volume']) if not pd.isna(row['volume']) else 0,
                    open_interest=int(row['openInterest']) if not pd.isna(row['openInterest']) else 0,
                    implied_volatility=row['impliedVolatility']
                ))

            # Process Puts
            for _, row in opts.puts.iterrows():
                options_list.append(OptionData(
                    symbol=symbol,
                    strike=row['strike'],
                    expiry=next_expiry,
                    option_type="put",
                    last_price=row['lastPrice'],
                    bid=row.get('bid', 0.0),
                    ask=row.get('ask', 0.0),
                    volume=int(row['volume']) if not pd.isna(row['volume']) else 0,
                    open_interest=int(row['openInterest']) if not pd.isna(row['openInterest']) else 0,
                    implied_volatility=row['impliedVolatility']
                ))
                
            return options_list

        except Exception as e:
            # Retry with .NS
            if not symbol.endswith(".NS") and not symbol.endswith(".BO"):
                 try:
                    return await self.get_option_chain(f"{symbol}.NS")
                 except Exception:
                    pass
                    
            logger.error("fetch_option_chain_error", symbol=symbol, error=str(e))
            return []
