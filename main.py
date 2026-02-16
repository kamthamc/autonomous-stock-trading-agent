import asyncio
import structlog
import sys
import os
from datetime import datetime

# Adjust path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agent_config import settings
from trader.us.robinhood import RobinhoodTrader
from trader.india.zerodha import ZerodhaTrader
from trader.india.icici import ICICITrader
from trader.router import BrokerRouter
from strategy.engine import StrategyEngine
from strategy.risk import RiskManager

logger = structlog.get_logger()

# Configure Logging
# Ensure log directory exists
os.makedirs(settings.log_dir, exist_ok=True)

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
file_handler = logging.FileHandler(settings.log_file_path)
# Use JSON Formatting for file so Dashboard can parse it
json_formatter = structlog.stdlib.ProcessorFormatter(
    processor=structlog.processors.JSONRenderer(),
)
file_handler.setFormatter(json_formatter)
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

from database.db import init_db, save_trade, trading_session
from database.models import Trade, AppConfig
from sqlmodel import select


def validate_config():
    """Validates that necessary configuration is present before starting the trading loop."""
    errors = []
    
    # At least one AI provider must be configured
    ai = settings.ai_provider
    if ai == "openai" and not settings.openai_api_key:
        errors.append("AI_PROVIDER is 'openai' but OPENAI_API_KEY is not set.")
    elif ai == "azure_openai" and (not settings.azure_openai_api_key or not settings.azure_openai_endpoint):
        errors.append("AI_PROVIDER is 'azure_openai' but AZURE_OPENAI_API_KEY or AZURE_OPENAI_ENDPOINT is not set.")
    elif ai == "gemini" and not settings.gemini_api_key:
        errors.append("AI_PROVIDER is 'gemini' but GEMINI_API_KEY is not set.")

    # At least one broker should be configured (or we're paper trading)
    if settings.trading_mode == "live":
        has_rh = settings.rh_username and settings.rh_password
        has_kite = settings.kite_api_key
        has_icici = settings.icici_api_key
        if not (has_rh or has_kite or has_icici):
            errors.append("TRADING_MODE is 'live' but no broker credentials are configured.")

    # Capital validation
    if settings.us_max_capital <= 0 and settings.india_max_capital <= 0:
        errors.append("At least one of US_MAX_CAPITAL or INDIA_MAX_CAPITAL must be > 0.")
    
    if errors:
        for e in errors:
            logger.error("config_validation_error", detail=e)
        return False
        
    logger.info("config_validation_passed", ai_provider=ai, mode=settings.trading_mode,
                 us_capital=settings.us_max_capital, india_capital=settings.india_max_capital)
    return True


async def setup_broker_router() -> BrokerRouter:
    """
    Initializes all broker instances, authenticates them, and registers
    them in the BrokerRouter by their market region.
    """
    router = BrokerRouter()
    router.set_preferences(
        us_preferred=settings.us_preferred_broker,
        india_preferred=settings.india_preferred_broker,
        india_fallback=settings.india_fallback_broker,
    )

    # --- US Brokers ---
    rh_trader = RobinhoodTrader()
    rh_auth = await rh_trader.authenticate()
    if rh_auth:
        router.register_broker("robinhood", rh_trader, region="US")
    else:
        logger.warning("broker_auth_failed", broker="robinhood", region="US")

    # --- India Brokers ---
    if settings.kite_api_key:
        kite_trader = ZerodhaTrader()
        kite_auth = await kite_trader.authenticate()
        if kite_auth:
            router.register_broker("zerodha", kite_trader, region="IN")
        else:
            logger.warning("broker_auth_failed", broker="zerodha", region="IN")

    if settings.icici_api_key:
        icici_trader = ICICITrader()
        icici_auth = await icici_trader.authenticate()
        if icici_auth:
            router.register_broker("icici", icici_trader, region="IN")
        else:
            logger.warning("broker_auth_failed", broker="icici", region="IN")

    # --- Validation ---
    if not router.has_us_broker and not router.has_india_broker:
        if settings.trading_mode == "live":
            logger.error("no_brokers_authenticated", mode="live")
            raise RuntimeError("No brokers authenticated in live mode. Cannot proceed.")
        else:
            logger.warning("no_brokers_authenticated_paper_mode", fallback="robinhood_paper")
            router.register_broker("robinhood", rh_trader, region="US")

    logger.info("broker_router_ready", brokers=router.all_broker_names)
    return router


async def load_dynamic_config(risk_managers=None):
    """Overrides global settings with values from the database (Dashboard config)."""
    try:
        async with trading_session() as session:
            result = await session.execute(select(AppConfig))
            configs = result.scalars().all()
            config_map = {c.key: c.value for c in configs}
            
            if "US_TICKERS" in config_map:
                try: 
                    settings.us_tickers = [t.strip() for t in config_map["US_TICKERS"].split(",") if t.strip()]
                    logger.info("config_override", key="US_TICKERS", count=len(settings.us_tickers))
                except: pass
                
            if "INDIA_TICKERS" in config_map:
                try:
                    settings.india_tickers = [t.strip() for t in config_map["INDIA_TICKERS"].split(",") if t.strip()]
                    logger.info("config_override", key="INDIA_TICKERS", count=len(settings.india_tickers))
                except: pass
            
            # Risk Updates
            if risk_managers and "RISK_MAX_RISK_PCT" in config_map:
                try:
                    risk_pct = Decimal(config_map["RISK_MAX_RISK_PCT"]) / 100
                    for rm in risk_managers.values():
                        rm.max_risk_per_trade = risk_pct
                    logger.info("config_risk_update", max_risk_pct=str(risk_pct))
                except: pass

            if risk_managers and "RISK_MAX_ALLOC_PCT" in config_map:
                try:
                    alloc_pct = Decimal(config_map["RISK_MAX_ALLOC_PCT"]) / 100
                    for rm in risk_managers.values():
                        # Update relative to CURRENT capital available
                        rm.max_capital_per_trade = rm.current_capital * alloc_pct
                    logger.info("config_risk_update", max_alloc_pct=str(alloc_pct))
                except: pass

    except Exception as e:
        logger.error("failed_to_load_dynamic_config", error=str(e))


async def trading_loop():
    logger.info("agent_starting", mode=settings.trading_mode)
    
    # Validate configuration
    if not validate_config():
        logger.error("agent_startup_failed", reason="Configuration validation failed. Check your .env file.")
        return
    
    await init_db()
    
    # Set up Broker Router (US vs India)
    router = await setup_broker_router()
    
    # Create per-region risk managers from .env config
    risk_managers = {
        "US": RiskManager(
            region="US",
            max_capital=settings.us_max_capital,
            max_per_trade=settings.us_max_per_trade,
        ),
        "IN": RiskManager(
            region="IN",
            max_capital=settings.india_max_capital,
            max_per_trade=settings.india_max_per_trade,
        ),
    }

    # Load initial dynamic config
    await load_dynamic_config(risk_managers)

    # Inject US broker into MarketData for real-time pricing
    from trader.market_data import MarketDataFetcher
    from strategy.scanner import MarketScanner
    
    # Use generic broker for data if specific one fails
    us_broker_for_data = router.get_broker_for_symbol("AAPL")
    market_data = MarketDataFetcher(broker=us_broker_for_data)
    
    # Strategy Engine with per-region risk managers
    engine = StrategyEngine(market_data=market_data, risk_managers=risk_managers)
    
    # Market Scanner
    scanner = MarketScanner(news_fetcher=engine.news_fetcher, ai_analyzer=engine.ai_analyzer)

    # Main Loop
    last_scan_time = datetime.min
    is_paper = settings.trading_mode != "live"
    
    from strategy.market_hours import filter_tickers_by_market_hours, get_market_status
    
    while True:
        try:
            # Refresh config (Dashboard settings & Risk Params)
            await load_dynamic_config(risk_managers)
            
            # CHECK KILL SWITCH
            async with trading_session() as session:
                result = await session.execute(select(AppConfig).where(AppConfig.key == "TRADING_STATUS"))
                status_row = result.scalar_one_or_none()
                if status_row and status_row.value == "PAUSED":
                    logger.warning("trading_paused_by_kill_switch", status="PAUSED")
                    await asyncio.sleep(10)
                    continue
            
            current_time = datetime.now()
            
            # Log market status each cycle
            market_status = get_market_status()
            logger.info("cycle_started", time=str(current_time),
                        us_market=market_status["us"],
                        india_market=market_status["india"])
            
            tickers = list(settings.all_tickers)  # Copy so we can extend with trending
            
            # Market scan every 30 minutes
            if (current_time - last_scan_time).total_seconds() > 1800:
                trending_tickers = await scanner.scan_market()
                if trending_tickers:
                    logger.info("adding_trending_stocks", tickers=trending_tickers)
                    for t in trending_tickers:
                        if t not in tickers:
                            tickers.append(t)
                last_scan_time = current_time

            # Filter tickers by regional market hours
            active_tickers, skipped_tickers = filter_tickers_by_market_hours(tickers, paper_mode=is_paper)
            
            if skipped_tickers:
                logger.info("tickers_skipped_market_closed", skipped=skipped_tickers)
            
            if not active_tickers:
                logger.info("no_active_markets", sleeping="60s")
                await asyncio.sleep(60)
                continue

            # Analyze only tickers whose markets are active
            signals = await engine.run_cycle(active_tickers)
            
            for signal in signals:
                logger.info("trade_signal_received", signal=signal.model_dump())
                
                # Route to the correct broker for this symbol's region
                region = BrokerRouter.detect_region(signal.symbol)
                broker = router.get_broker_for_symbol(signal.symbol)
                
                if not broker:
                    logger.warning("no_broker_for_region", symbol=signal.symbol, region=region)
                    continue
                
                # Check market hours for the relevant region
                if settings.trading_mode == "live" and not router.is_market_open_for_symbol(signal.symbol):
                    logger.info("market_closed_skipping_order", symbol=signal.symbol, region=region)
                    continue
                
                # Execute Trade — broker handles symbol conversion internally
                order = await broker.place_order(
                    symbol=signal.symbol,
                    quantity=signal.quantity,
                    side=signal.action.lower(),
                )
                logger.info("order_placed", 
                            order_id=order.order_id, status=order.status,
                            region=region)
                
                # Record trade in the region's risk manager
                if order.status not in ("failed", "FAILED", "ERROR", "REJECTED"):
                    rm = risk_managers.get(region, risk_managers["US"])
                    rm.record_trade(
                        symbol=signal.symbol,
                        action=signal.action,
                        quantity=signal.quantity,
                        price=signal.price
                    )
                
                # Persist to DB
                await save_trade(Trade(
                    symbol=signal.symbol,
                    action=signal.action,
                    quantity=signal.quantity,
                    price=signal.price,
                    status=order.status,
                    order_id=order.order_id
                ))
            
            # Log end-of-cycle status per region
            for rgn, rm in risk_managers.items():
                logger.info("cycle_region_status", 
                            region=rgn,
                            capital_remaining=str(rm.current_capital),
                            open_positions=len(rm.positions))
            
            await asyncio.sleep(60)

        except KeyboardInterrupt:
            logger.info("agent_stopping_user_request")
            break
        except Exception as e:
            logger.exception("main_loop_error", error=str(e))
            await asyncio.sleep(10)

if __name__ == "__main__":
    try:
        asyncio.run(trading_loop())
    except KeyboardInterrupt:
        pass
