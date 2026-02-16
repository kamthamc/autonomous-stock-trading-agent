
import asyncio
import os
import sys
import structlog
import yfinance as yf
import sqlite3
from agent_config import settings
from strategy.ai import AIAnalyzer
from trader.router import BrokerRouter
from trader.us.robinhood import RobinhoodTrader
from trader.india.zerodha import ZerodhaTrader
from trader.india.icici import ICICITrader
from database.db import init_db

# Configure simplified logging to console
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
        structlog.dev.ConsoleRenderer()
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
)
# We still keep logger for dependencies, but testing functions will use print()

async def test_env_vars():
    print("Checking Environment Variables...")
    required_keys = ["AI_PROVIDER", "TRADING_MODE"]
    
    missing = []
    for key in required_keys:
        val = str(getattr(settings, key.lower(), os.getenv(key)))
        if not val or val == "None":
            missing.append(key)
        else:
            masked = val[:4] + "*" * 4 if len(val) > 8 else val
            print(f"✅ {key}: {masked}")

    if settings.ai_provider == "azure_openai":
        if not settings.azure_openai_api_key: missing.append("AZURE_OPENAI_API_KEY")
        if not settings.azure_openai_endpoint: missing.append("AZURE_OPENAI_ENDPOINT")
    elif settings.ai_provider == "openai":
         if not settings.openai_api_key: missing.append("OPENAI_API_KEY")

    if missing:
        print(f"❌ Missing Critical Env Vars: {missing}")
        return False
    return True

async def test_database():
    print(f"Checking Database Connection at {settings.trading_db_path}...")
    try:
        os.makedirs(os.path.dirname(settings.trading_db_path), exist_ok=True)
        await init_db()
        
        with sqlite3.connect(settings.trading_db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [r[0] for r in cursor.fetchall()]
            print(f"✅ Database initialized. Tables found: {len(tables)} ({', '.join(tables[:3])}...)")
        return True
    except Exception as e:
        print(f"❌ Database Error: {e}")
        return False

async def test_market_data():
    print("Testing Market Data (YFinance)...")
    symbol = "SPY"
    try:
        t = yf.Ticker(symbol)
        price = t.fast_info.last_price
        if price:
            print(f"✅ Market Data Live: {symbol} Price = ${price:.2f}")
            return True
        else:
            print(f"❌ Market Data: Price is None for {symbol}")
            return False
    except Exception as e:
        print(f"❌ Market Data Failed: {e}")
        return False

async def test_llm():
    provider = settings.ai_provider
    if not provider or provider == "None":
        print("ℹ️ LLM: Skipped (Not Configured)")
        return False, "None"
        
    print(f"Testing LLM Provider: {provider}...")
    try:
        analyzer = AIAnalyzer()
        response = await analyzer.generate_text("Respond with a single word: 'Connected'.")
        if response and len(response) > 0:
            print(f"✅ LLM Response Received: '{response.strip()}'")
            return True, provider
        else:
            print("❌ LLM Response Empty or Unexpected")
            return False, provider
    except Exception as e:
        print(f"❌ LLM Connection Failed: {e}")
        return False, provider

async def test_brokers():
    print("Testing Configured Brokers...")
    all_good = True
    tested = []
    
    # --- US BROKERS ---
    # Robinhood
    if settings.rh_username and settings.rh_password:
        print(f"🇺🇸 Robinhood Configured. Testing Auth...")
        tested.append("Robinhood")
        try:
            rh_trader = RobinhoodTrader()
            auth = await rh_trader.authenticate()
            if auth:
                print("✅ Robinhood: Authenticated")
            else: 
                print("❌ Robinhood: Authentication Failed")
                all_good = False
        except Exception as e:
            print(f"❌ Robinhood Error: {e}")
            all_good = False
    else:
        print("ℹ️ Robinhood: Skipped (Not Configured)")

    # --- INDIA BROKERS ---
    # Zerodha (Kite)
    if settings.kite_api_key:
        print(f"🇮🇳 Zerodha Configured. Testing Auth...")
        tested.append("Zerodha")
        try:
            kite = ZerodhaTrader()
            auth = await kite.authenticate()
            if auth:
                print("✅ Zerodha: Authenticated")
                # Fetch Balance
                try:
                    balance = await kite.get_account_balance()
                    print(f"💰 Zerodha Funds: ₹{balance:,.2f}")
                except Exception as e:
                    print(f"❌ Zerodha Balance Fetch Failed: {e}")
            else:
                print("❌ Zerodha: Authentication Failed")
                all_good = False
        except Exception as e:
            print(f"❌ Zerodha Error: {e}")
            all_good = False
    else:
        print("ℹ️ Zerodha: Skipped (Not Configured)")

    # ICICI Direct
    if settings.icici_api_key:
        print(f"🇮🇳 ICICI Direct Configured. Testing Auth...")
        tested.append("ICICI")
        try:
            icici = ICICITrader()
            auth = await icici.authenticate()
            if auth:
                 print("✅ ICICI: Authenticated")
            else:
                 print("❌ ICICI: Authentication Failed")
                 all_good = False
        except Exception as e:
            print(f"❌ ICICI Error: {e}")
            all_good = False
    else:
        print("ℹ️ ICICI: Skipped (Not Configured)")
            
    return all_good, tested

async def main():
    print("="*60)
    print("🕵️  AUTONOMOUS AGENT | CONNECTION TESTER")
    print("="*60)
    
    # Run tests sequentially with explicit headers
    print("\n--- 1. Environment Variables ---")
    env_res = await test_env_vars()
    
    print("\n--- 2. Database ---")
    db_res = await test_database()
    
    print("\n--- 3. Market Data ---")
    mkt_res = await test_market_data()
    
    print("\n--- 4. LLM Provider ---")
    llm_res, llm_prov = await test_llm()
    
    print("\n--- 5. Brokers ---")
    brk_res, brk_list = await test_brokers()

    # Summary
    results = [
        ("Env Vars", env_res),
        ("Database", db_res),
        ("Market Data", mkt_res),
        (f"LLM ({llm_prov})", llm_res),
        (f"Brokers ({', '.join(brk_list) if brk_list else 'None Configured'})", brk_res)
    ]
    
    print("\n" + "="*60)
    print("📊 DIAGNOSTIC SUMMARY")
    print("="*60)
    
    all_pass = True
    for label, passed in results:
        status = "PASS ✅" if passed else "FAIL ❌"
        # Special case
        if "Brokers" in label and "None Configured" in label:
             status = "SKIPPED ℹ️"
        
        print(f"{label:<40} : {status}")
        
        if not passed: 
            all_pass = False
        
    print("="*60)
    if all_pass:
        print("🚀 SYSTEM READY FOR LAUNCH")
        sys.exit(0)
    else:
        print("🛑 SYSTEM HAS ISSUES - CHECK LOGS ABOVE")
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
