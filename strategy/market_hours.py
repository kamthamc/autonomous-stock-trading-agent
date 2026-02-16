"""
Market hours, holidays, and early close detection.

Uses `exchange_calendars` for comprehensive holiday/schedule data:
- NYSE (US stocks)
- NSE (Indian stocks ending .NS)
- BSE (Indian stocks ending .BO)

Supports:
- Full holidays (market closed all day)
- Early closes (e.g. day before Thanksgiving, Diwali Muhurat)
- Pre-market analysis window (30min before open)
"""

from datetime import datetime, time, timedelta, date
from typing import List, Tuple, Optional
import pytz
import structlog
import exchange_calendars as xcals

logger = structlog.get_logger()

# Timezones
US_EASTERN = pytz.timezone('US/Eastern')
INDIA_IST = pytz.timezone('Asia/Kolkata')

# Pre-market window (analyze stocks this many minutes before open)
PRE_MARKET_MINUTES = 30

# Calendar instances (loaded once, cached)
_calendars = {}


def _get_calendar(exchange: str) -> xcals.ExchangeCalendar:
    """Lazily load and cache exchange calendars."""
    if exchange not in _calendars:
        _calendars[exchange] = xcals.get_calendar(exchange)
    return _calendars[exchange]


def _exchange_for_symbol(symbol: str) -> str:
    """Map a ticker symbol to its exchange calendar ID."""
    if symbol.endswith('.BO'):
        return 'XBOM'  # BSE / Bombay
    elif symbol.endswith('.NS'):
        return 'BSE'   # NSE uses BSE calendar (same Indian holiday schedule)
    else:
        return 'XNYS'  # NYSE (default for US)


def get_session_info(symbol: str, target_date: Optional[date] = None) -> dict:
    """
    Returns detailed session info for a symbol on a given date.
    
    Returns dict with:
        is_holiday: bool - Market is completely closed
        is_open_today: bool - Market has a session today
        is_early_close: bool - Market closes early today
        open_time: time or None - Market open time (local)
        close_time: time or None - Market close time (local, may be early)
        holiday_name: str or None - Name of the holiday if closed
        exchange: str - Exchange calendar ID
    """
    exchange = _exchange_for_symbol(symbol)
    cal = _get_calendar(exchange)
    tz = pytz.timezone(str(cal.tz))
    
    if target_date is None:
        target_date = datetime.now(tz).date()
    
    # Convert to pandas Timestamp for exchange_calendars
    import pandas as pd
    ts = pd.Timestamp(target_date)
    
    result = {
        'exchange': exchange,
        'date': str(target_date),
        'is_holiday': False,
        'is_open_today': False,
        'is_early_close': False,
        'open_time': None,
        'close_time': None,
        'holiday_name': None,
    }
    
    # Check if it's a valid session day
    if not cal.is_session(ts):
        result['is_holiday'] = True
        
        if target_date.weekday() > 4:
            result['holiday_name'] = "Weekend"
        else:
            result['holiday_name'] = "Market Holiday"
        
        return result
    
    # It's a valid session
    result['is_open_today'] = True
    
    # Get session open/close times
    session_open = cal.session_open(ts)
    session_close = cal.session_close(ts)
    
    # Convert to local time
    local_open = session_open.astimezone(tz)
    local_close = session_close.astimezone(tz)
    
    result['open_time'] = local_open.strftime("%H:%M")
    result['close_time'] = local_close.strftime("%H:%M")
    
    # Detect early close by comparing to standard hours
    _standard_closes = {'BSE': time(15, 30), 'XBOM': time(15, 30), 'XNYS': time(16, 0)}
    standard_close = _standard_closes.get(exchange, time(16, 0))
    
    if local_close.time() < standard_close:
        result['is_early_close'] = True
    
    return result


def is_market_open(symbol: str) -> bool:
    """
    Checks if the market is currently open for the given symbol.
    Uses exchange_calendars for accurate holiday and schedule data.
    """
    exchange = _exchange_for_symbol(symbol)
    cal = _get_calendar(exchange)
    tz = pytz.timezone(str(cal.tz))
    now = datetime.now(tz)
    
    import pandas as pd
    ts = pd.Timestamp(now.date())
    
    if not cal.is_session(ts):
        return False
    
    session_open = cal.session_open(ts).astimezone(tz)
    session_close = cal.session_close(ts).astimezone(tz)
    
    return session_open <= now <= session_close


def is_in_analysis_window(symbol: str) -> bool:
    """
    Returns True if the symbol's market is open OR within the pre-market
    analysis window (30 min before open). Also returns False on holidays.
    """
    exchange = _exchange_for_symbol(symbol)
    cal = _get_calendar(exchange)
    tz = pytz.timezone(str(cal.tz))
    now = datetime.now(tz)
    
    import pandas as pd
    ts = pd.Timestamp(now.date())
    
    if not cal.is_session(ts):
        return False
    
    session_open = cal.session_open(ts).astimezone(tz)
    session_close = cal.session_close(ts).astimezone(tz)
    
    pre_market_start = session_open - timedelta(minutes=PRE_MARKET_MINUTES)
    
    return pre_market_start <= now <= session_close


def get_market_status() -> dict:
    """
    Returns a summary of which regional markets are currently open/in analysis window.
    Includes holiday info and early close detection.
    """
    us_info = get_session_info("SPY")      # NYSE proxy
    in_info = get_session_info("NIFTY.NS") # NSE proxy
    
    now_us = datetime.now(US_EASTERN)
    now_in = datetime.now(INDIA_IST)
    
    return {
        "us": {
            "time": now_us.strftime("%H:%M"),
            "is_open": is_market_open("SPY"),
            "in_analysis_window": is_in_analysis_window("SPY"),
            "is_holiday": us_info['is_holiday'],
            "holiday_name": us_info['holiday_name'],
            "is_early_close": us_info['is_early_close'],
            "close_time": us_info['close_time'],
        },
        "india": {
            "time": now_in.strftime("%H:%M"),
            "is_open": is_market_open("NIFTY.NS"),
            "in_analysis_window": is_in_analysis_window("NIFTY.NS"),
            "is_holiday": in_info['is_holiday'],
            "holiday_name": in_info['holiday_name'],
            "is_early_close": in_info['is_early_close'],
            "close_time": in_info['close_time'],
        }
    }


def filter_tickers_by_market_hours(tickers: List[str], paper_mode: bool = False) -> Tuple[List[str], List[str]]:
    """
    Splits tickers into active (should analyze) and skipped (market closed/holiday).
    
    In paper mode, all tickers are considered active to allow full testing.
    In live mode, only tickers whose markets are in the analysis window are active.
    
    Returns:
        (active_tickers, skipped_tickers)
    """
    if paper_mode:
        return tickers, []
    
    active = []
    skipped = []
    
    for ticker in tickers:
        if is_in_analysis_window(ticker):
            active.append(ticker)
        else:
            skipped.append(ticker)
    
    return active, skipped
