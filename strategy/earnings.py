"""
Earnings calendar — fetches upcoming quarterly results dates for watchlist stocks.

Uses yfinance's calendar data which includes:
- Next earnings date
- Earnings estimate (EPS)
- Revenue estimate

This is used by the AI analyzer to factor in earnings risk,
and displayed on the dashboard for visibility.
"""

import yfinance as yf
import structlog
from datetime import datetime, date, timedelta
from typing import Optional, Dict, List
from pydantic import BaseModel

logger = structlog.get_logger()


class EarningsInfo(BaseModel):
    """Upcoming earnings information for a stock."""
    symbol: str
    earnings_date: Optional[str] = None          # ISO date string
    days_until_earnings: Optional[int] = None
    eps_estimate: Optional[float] = None
    revenue_estimate: Optional[float] = None
    is_within_warning_window: bool = False  # True if earnings < 7 days away


# Cache earnings to avoid hammering yfinance on every cycle
_earnings_cache: Dict[str, EarningsInfo] = {}
_cache_expiry: Dict[str, datetime] = {}
CACHE_TTL_HOURS = 6  # Refresh earnings data every 6 hours


def get_earnings_info(symbol: str) -> EarningsInfo:
    """
    Fetches the next earnings date for a symbol.
    Results are cached for CACHE_TTL_HOURS to reduce API calls.
    """
    now = datetime.now()
    
    # Check cache
    if symbol in _earnings_cache and symbol in _cache_expiry:
        if now < _cache_expiry[symbol]:
            return _earnings_cache[symbol]
    
    info = EarningsInfo(symbol=symbol)
    
    try:
        ticker = yf.Ticker(symbol)
        cal = ticker.calendar
        
        if cal is not None and not cal.empty if hasattr(cal, 'empty') else cal is not None:
            # yfinance returns calendar as a DataFrame or dict depending on version
            if isinstance(cal, dict):
                earnings_date_val = cal.get('Earnings Date')
                if earnings_date_val:
                    if isinstance(earnings_date_val, list) and len(earnings_date_val) > 0:
                        ed = earnings_date_val[0]
                    else:
                        ed = earnings_date_val
                    
                    if hasattr(ed, 'date'):
                        earnings_date = ed.date()
                    elif isinstance(ed, str):
                        earnings_date = datetime.fromisoformat(ed).date()
                    else:
                        earnings_date = None
                    
                    if earnings_date:
                        info.earnings_date = str(earnings_date)
                        info.days_until_earnings = (earnings_date - date.today()).days
                        info.is_within_warning_window = 0 <= info.days_until_earnings <= 7
                
                info.eps_estimate = cal.get('EPS Estimate')
                info.revenue_estimate = cal.get('Revenue Estimate')
            
            else:
                # DataFrame format
                import pandas as pd
                if 'Earnings Date' in cal.columns:
                    ed_val = cal['Earnings Date'].iloc[0] if len(cal) > 0 else None
                    if ed_val and pd.notna(ed_val):
                        if hasattr(ed_val, 'date'):
                            earnings_date = ed_val.date()
                        else:
                            earnings_date = pd.Timestamp(ed_val).date()
                        
                        info.earnings_date = str(earnings_date)
                        info.days_until_earnings = (earnings_date - date.today()).days
                        info.is_within_warning_window = 0 <= info.days_until_earnings <= 7
        
        logger.info("earnings_fetched", symbol=symbol, 
                     earnings_date=info.earnings_date,
                     days_until=info.days_until_earnings)
    
    except Exception as e:
        logger.warning("earnings_fetch_error", symbol=symbol, error=str(e))
    
    # Cache the result
    _earnings_cache[symbol] = info
    _cache_expiry[symbol] = now + timedelta(hours=CACHE_TTL_HOURS)
    
    return info


def get_bulk_earnings(symbols: List[str]) -> List[EarningsInfo]:
    """Fetches earnings info for a list of symbols."""
    results = []
    for symbol in symbols:
        results.append(get_earnings_info(symbol))
    return results


def get_earnings_warnings(symbols: List[str]) -> List[EarningsInfo]:
    """Returns only symbols with earnings within the next 7 days."""
    all_info = get_bulk_earnings(symbols)
    return [info for info in all_info if info.is_within_warning_window]
