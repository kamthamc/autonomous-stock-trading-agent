import pandas as pd
import pandas_ta as ta
from pydantic import BaseModel
import structlog

logger = structlog.get_logger()

class TechIndicators(BaseModel):
    rsi: float
    macd: float
    macd_signal: float
    bb_upper: float
    bb_lower: float
    atr: float
    sma_50: float
    sma_200: float

class TechAnalyzer:
    def analyze(self, df: pd.DataFrame) -> TechIndicators:
        """Calculates technical indicators for the given dataframe."""
        if df.empty:
            return None
        
        try:
            # ROI
            df.ta.rsi(length=14, append=True)
            
            # MACD
            df.ta.macd(append=True)
            
            # Bollinger Bands
            df.ta.bbands(append=True)
            
            # ATR
            df.ta.atr(append=True)
            
            # SMAs
            df.ta.sma(length=50, append=True)
            df.ta.sma(length=200, append=True)
            
            # Get latest row
            latest = df.iloc[-1]
            
            # Column names in pandas-ta can be dynamic, standardizing access
            # RSI_14, MACD_12_26_9, MACDs_12_26_9, BBU_5_2.0, BBL_5_2.0, ATR_14, SMA_50, SMA_200
            
            # Helper to safely get value
            def get_val(col_pattern):
                cols = [c for c in df.columns if col_pattern in c]
                return float(latest[cols[0]]) if cols else 0.0

            return TechIndicators(
                rsi=get_val("RSI"),
                macd=get_val("MACD_"),
                macd_signal=get_val("MACDs_"),
                bb_upper=get_val("BBU"),
                bb_lower=get_val("BBL"),
                atr=get_val("ATR"),
                sma_50=get_val("SMA_50"),
                sma_200=get_val("SMA_200")
            )

        except Exception as e:
            logger.error("tech_analysis_error", error=str(e))
            return None
