import pandas as pd
import pandas_ta as ta
from pydantic import BaseModel
from typing import Optional
import structlog
import math

logger = structlog.get_logger()

class TechIndicators(BaseModel):
    rsi: float
    macd: float
    macd_signal: float
    bb_upper: float
    bb_lower: float
    atr: float
    sma_50: Optional[float] = None
    sma_200: Optional[float] = None

class TechAnalyzer:
    def analyze(self, df: pd.DataFrame) -> TechIndicators:
        """Calculates technical indicators for the given dataframe."""
        if df.empty:
            return None
        
        rows = len(df)
        logger.info("tech_analysis_data_points", rows=rows)
        
        if rows < 50:
            logger.warning("tech_insufficient_history_sma50", rows=rows, required=50)
        if rows < 200:
            logger.warning("tech_insufficient_history_sma200", rows=rows, required=200)
        
        try:
            # RSI
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
            
            def get_val(col_pattern: str) -> Optional[float]:
                """Safely gets an indicator value, returning None for NaN/missing."""
                cols = [c for c in df.columns if col_pattern in c]
                if not cols:
                    return None
                val = latest[cols[0]]
                if pd.isna(val) or (isinstance(val, float) and math.isnan(val)):
                    return None
                return float(val)

            sma_50 = get_val("SMA_50")
            sma_200 = get_val("SMA_200")
            
            return TechIndicators(
                rsi=get_val("RSI") or 50.0,       # Default RSI to neutral if missing
                macd=get_val("MACD_") or 0.0,
                macd_signal=get_val("MACDs_") or 0.0,
                bb_upper=get_val("BBU") or 0.0,
                bb_lower=get_val("BBL") or 0.0,
                atr=get_val("ATR") or 0.0,
                sma_50=sma_50,
                sma_200=sma_200,
            )

        except Exception as e:
            logger.error("tech_analysis_error", error=str(e))
            return None
