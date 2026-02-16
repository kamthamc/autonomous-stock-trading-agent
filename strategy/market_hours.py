from datetime import datetime, time
import pytz

# Timezones
US_EASTERN = pytz.timezone('US/Eastern')
INDIA_IST = pytz.timezone('Asia/Kolkata')

def is_market_open(symbol: str) -> bool:
    """
    Checks if the market is open for the given symbol.
    
    Rules:
    - US Stocks (default): 9:30 AM - 4:00 PM ET, Mon-Fri
    - Indian Stocks (ends with .NS or .BO): 9:15 AM - 3:30 PM IST, Mon-Fri
    """
    now_utc = datetime.now(pytz.utc)
    
    # Check for Indian Stock Suffixes
    if symbol.endswith('.NS') or symbol.endswith('.BO'):
        now_in = now_utc.astimezone(INDIA_IST)
        # Weekday check (0=Mon, 4=Fri)
        if now_in.weekday() > 4:
            return False
            
        current_time = now_in.time()
        market_start = time(9, 15)
        market_end = time(15, 30)
        return market_start <= current_time <= market_end

    else:
        # Default to US Market
        now_us = now_utc.astimezone(US_EASTERN)
        if now_us.weekday() > 4:
            return False
            
        current_time = now_us.time()
        market_start = time(9, 30)
        market_end = time(16, 0)
        return market_start <= current_time <= market_end
