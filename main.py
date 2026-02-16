import asyncio
import structlog
import sys
import os
from datetime import datetime

# Adjust path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import settings
from trader.robinhood import RobinhoodTrader
from trader.zerodha import ZerodhaTrader
from strategy.engine import StrategyEngine

logger = structlog.get_logger()

# Configure Logging
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

# File Handler
import logging
file_handler = logging.FileHandler("agent_activity.log")
file_handler.setFormatter(logging.Formatter("%(message)s"))
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter("%(message)s"))

root_logger = logging.getLogger()
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)
root_logger.setLevel(logging.INFO)

# OpenTelemetry Setup
try:
    from telemetry import setup_telemetry
    otel_handler = setup_telemetry("autonomous-trader")
    root_logger.addHandler(otel_handler)
    print("OpenTelemetry Initialized.")
except Exception as e:
    print(f"Failed to initialize OpenTelemetry: {e}")

from database.db import init_db, save_trade, save_signal
from database.models import Trade, Signal

async def trading_loop():
    logger.info("agent_starting", mode=settings.trading_mode)
    
    # Initialize Database
    await init_db()
    
    # 1. Initialize Components
    rh_trader = RobinhoodTrader()
    kite_trader = ZerodhaTrader()
    
    # Inject primary broker (Robinhood) into MarketData for real-time pricing
    # (For a more complex setup, we'd need a multi-broker router)
    from trader.market_data import MarketDataFetcher
    from strategy.scanner import MarketScanner
    
    market_data = MarketDataFetcher(broker=rh_trader)
    
    # Using Dependency Injection in StrategyEngine allows swapping components for testing
    engine = StrategyEngine(market_data=market_data)
    
    # Initialize Scanner
    scanner = MarketScanner(news_fetcher=engine.news_fetcher, ai_analyzer=engine.ai_analyzer)

    # 2. Authenticate Brokers
    # In a real app, handle auth failures gracefully
    await rh_trader.authenticate()
    if settings.kite_api_key:
        await kite_trader.authenticate()
    
    # 3. Main Loop
    last_scan_time = datetime.min
    
    while True:
        try:
            current_time = datetime.now()
            # Market hours check could be added here
            
            logger.info("cycle_started", time=str(current_time))
            
            # Fetch watchlist from settings
            tickers = [s.ticker for s in settings.watchlist if s.enabled]
            
            # Run Market Scan every 30 minutes to find new hot stocks
            if (current_time - last_scan_time).total_seconds() > 1800:
                trending_tickers = await scanner.scan_market()
                if trending_tickers:
                    logger.info("adding_trending_stocks", tickers=trending_tickers)
                    # Add new tickers to the list (avoid duplicates)
                    for t in trending_tickers:
                        if t not in tickers:
                            tickers.append(t)
                last_scan_time = current_time

            # Run Analysis
            signals = await engine.run_cycle(tickers)
            
            for signal in signals:
                logger.info("trade_signal_received", signal=signal.model_dump())
                
                # Determine Broker
                # Simple logic: NSE stocks usually have suffix or specific format. 
                # Assuming standard US stocks for default.
                broker = rh_trader
                if ".NS" in signal.symbol or "^NSE" in signal.symbol:
                    broker = kite_trader
                
                # Execute Trade
                if settings.trading_mode == "live" or settings.trading_mode == "paper":
                    # For paper mode, the broker generic class handles simulation
                    order = await broker.place_order(
                        symbol=signal.symbol,
                        quantity=signal.quantity,
                        side=signal.action.lower(), # BUY -> buy
                    )
                    logger.info("order_placed", order_id=order.order_id, status=order.status)
                    
                    # Log Trade to DB
                    trade_record = Trade(
                        symbol=signal.symbol,
                        action=signal.action,
                        quantity=signal.quantity,
                        price=signal.price, # This might need to be updated with actual fill price from order
                        status=order.status,
                        order_id=order.order_id
                    )
                    await save_trade(trade_record)
            
            logger.info("cycle_completed", signals_count=len(signals))
            
            # Wait for next cycle (e.g. 60 seconds)
            await asyncio.sleep(60)

        except KeyboardInterrupt:
            logger.info("agent_stopping_user_request")
            break
        except Exception as e:
            logger.error("main_loop_error", error=str(e))
            await asyncio.sleep(10) # Wait before retrying

if __name__ == "__main__":
    try:
        asyncio.run(trading_loop())
    except KeyboardInterrupt:
        pass
