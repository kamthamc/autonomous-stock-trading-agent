import yfinance as yf
import structlog
from datetime import datetime, timedelta

logger = structlog.get_logger()

_cache = {
    'rate': 89.5, # Safe fallback conversion rate
    'timestamp': None
}

def get_usd_inr_rate() -> float:
    """Gets the live USD to INR exchange rate, cached for 1 hour."""
    now = datetime.now()
    if _cache['timestamp'] and (now - _cache['timestamp']) < timedelta(hours=1):
        return _cache['rate']
        
    try:
        # Fetch from Yahoo Finance
        ticker = yf.Ticker("INR=X")
        data = ticker.history(period="1d")
        if not data.empty:
            rate = data['Close'].iloc[-1]
            _cache['rate'] = float(rate)
            _cache['timestamp'] = now
            logger.info("fx_rate_updated", rate=_cache['rate'], pair="USD/INR")
    except Exception as e:
        logger.error("fx_rate_error", error=str(e), fallback=_cache['rate'])
        
    return _cache['rate']
