import asyncio
import structlog
import sys
import os
from unittest.mock import MagicMock, AsyncMock

# Adjust path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import settings
from strategy.engine import StrategyEngine
from strategy.risk import RiskManager
from strategy.ai import AISignal, AIAnalyzer
from database.db import init_db

# ...

async def test_run():
    print("Starting Test Run with Dependency Injection...")
    
    # Initialize DB (creates tables if missing)
    await init_db()
    
    settings.trading_mode = "paper"
    
    # Mock AI Analyzer
    mock_ai = MagicMock(spec=AIAnalyzer)
    mock_ai.analyze = AsyncMock(return_value=AISignal(
        decision="BUY_STOCK",
        confidence=0.99,
        reasoning="DI Test - Mocked AI High Confidence",
        stop_loss_suggestion=150.0
    ))
    
    # Mock Risk Manager (Pass all trades)
    mock_risk = MagicMock(spec=RiskManager)
    mock_risk.validate_trade = AsyncMock(return_value=True)
    
    # Inject Mocks
    engine = StrategyEngine(ai_analyzer=mock_ai, risk_manager=mock_risk)
    
    symbol = "AAPL"
    print(f"Analyzing {symbol} with Mocked AI...")
    
    try:
        signal = await engine.analyze_symbol(symbol)
        
        if signal:
            print("Signal Generated:")
            print(signal.model_dump_json(indent=2))
            if signal.reason == "DI Test - Mocked AI High Confidence":
                 print("SUCCESS: Dependency Injection worked!")
            else:
                 print("FAILURE: DI did not use mocked component.")
        else:
            print("No Signal (HOLD or Error)")
            
    except Exception as e:
        print(f"Test Failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_run())
