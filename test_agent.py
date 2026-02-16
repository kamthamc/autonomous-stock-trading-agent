import asyncio
import structlog
import sys
import os

# Adjust path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import settings
from strategy.engine import StrategyEngine
from strategy.ai import AISignal

# Configure logging to print to console
structlog.configure(
    processors=[
        structlog.processors.JSONRenderer(indent=2, sort_keys=True)
    ],
    logger_factory=structlog.PrintLoggerFactory(),
)

async def test_run():
    print("Starting Test Run...")
    
    # Force settings for test
    settings.trading_mode = "paper"
    
    engine = StrategyEngine()
    
    # Test with AAPL
    symbol = "AAPL"
    print(f"Analyzing {symbol}...")
    
    # Manually trigger analyze_symbol
    try:
        # Mocking AI analysis if no key present to ensure we test the flow
        if not settings.openai_api_key and not settings.azure_openai_endpoint:
            print("No AI Key found, mocking AI response for test...")
            original_analyze = engine.ai_analyzer.analyze
            async def mock_analyze(*args, **kwargs):
                return AISignal(
                    decision="BUY_STOCK",
                    confidence=0.95,
                    reasoning="Test Verification - High Confidence buy",
                    stop_loss_suggestion=150.0
                )
            engine.ai_analyzer.analyze = mock_analyze

        signal = await engine.analyze_symbol(symbol)
        
        if signal:
            print("Signal Generated:")
            print(signal.model_dump_json(indent=2))
        else:
            print("No Signal (HOLD or Error)")
            
    except Exception as e:
        print(f"Test Failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_run())
