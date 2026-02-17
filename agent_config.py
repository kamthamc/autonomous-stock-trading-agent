import os
from typing import List, Optional, Literal, Dict
from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# ──────────────────────────────────────────────
# Per-Style Risk Profile
# ──────────────────────────────────────────────
class TradingStyleProfile(BaseModel):
    """Risk appetite and behavior parameters for a trading style.

    These act as defaults; per-region overrides in the .env still take
    precedence for capital limits.
    """
    name: str
    max_risk_per_trade: float       # max loss as fraction of capital (0.02 = 2%)
    trailing_stop_pct: float        # trail below high-watermark (0.03 = 3%)
    min_upside_target_pct: float    # min gain before any partial sell
    partial_sell_pct: float         # fraction to sell at each scale-out
    max_scale_outs: int             # max partial sells before full exit
    confidence_threshold: float     # AI signal must exceed this to act
    llm_cache_ttl_seconds: int      # how long to cache LLM responses
    stop_loss_check_interval: int   # seconds between fast risk checks
    circuit_breaker_daily_loss_pct: float  # daily loss limit as pct of capital
    max_daily_trades: int


STYLE_PROFILES: Dict[str, TradingStyleProfile] = {
    "intraday": TradingStyleProfile(
        name="intraday",
        max_risk_per_trade=0.02,
        trailing_stop_pct=0.015,
        min_upside_target_pct=0.02,
        partial_sell_pct=0.50,
        max_scale_outs=2,
        confidence_threshold=0.60,
        llm_cache_ttl_seconds=300,    # 5 min
        stop_loss_check_interval=10,
        circuit_breaker_daily_loss_pct=0.05,
        max_daily_trades=50,
    ),
    "short_term": TradingStyleProfile(
        name="short_term",
        max_risk_per_trade=0.03,
        trailing_stop_pct=0.03,
        min_upside_target_pct=0.05,
        partial_sell_pct=0.50,
        max_scale_outs=2,
        confidence_threshold=0.55,
        llm_cache_ttl_seconds=900,    # 15 min
        stop_loss_check_interval=30,
        circuit_breaker_daily_loss_pct=0.05,
        max_daily_trades=30,
    ),
    "long_term": TradingStyleProfile(
        name="long_term",
        max_risk_per_trade=0.05,
        trailing_stop_pct=0.08,
        min_upside_target_pct=0.15,
        partial_sell_pct=0.25,
        max_scale_outs=3,
        confidence_threshold=0.50,
        llm_cache_ttl_seconds=1800,   # 30 min
        stop_loss_check_interval=60,
        circuit_breaker_daily_loss_pct=0.08,
        max_daily_trades=10,
    ),
    "optimistic": TradingStyleProfile(
        name="optimistic",
        max_risk_per_trade=0.05,
        trailing_stop_pct=0.04,
        min_upside_target_pct=0.05,
        partial_sell_pct=0.25,
        max_scale_outs=3,
        confidence_threshold=0.50,
        llm_cache_ttl_seconds=600,    # 10 min
        stop_loss_check_interval=10,
        circuit_breaker_daily_loss_pct=0.10,
        max_daily_trades=40,
    ),
}


class StockConfig(BaseModel):
    ticker: str
    enabled: bool = True
    asset_type: Literal["stock", "option"] = "stock"

class AgentSettings(BaseSettings):
    # ──────────────────────────────────────────────
    # US Broker — Robinhood
    # ──────────────────────────────────────────────
    rh_username: Optional[str] = None
    rh_password: Optional[str] = None
    rh_mfa_code: Optional[str] = None
    
    # ──────────────────────────────────────────────
    # India Broker — Zerodha / Kite Connect
    # ──────────────────────────────────────────────
    kite_api_key: Optional[str] = None
    kite_api_secret: Optional[str] = None
    kite_access_token: Optional[str] = None
    kite_request_token: Optional[str] = None

    # ──────────────────────────────────────────────
    # India Broker — ICICI Direct / Breeze
    # ──────────────────────────────────────────────
    icici_api_key: Optional[str] = None
    icici_secret_key: Optional[str] = None
    icici_session_token: Optional[str] = None

    # ──────────────────────────────────────────────
    # Broker Region Preferences
    # ──────────────────────────────────────────────
    us_preferred_broker: Literal["robinhood"] = "robinhood"
    india_preferred_broker: Literal["zerodha", "icici"] = "zerodha"
    india_fallback_broker: Optional[Literal["zerodha", "icici"]] = "icici"
    
    # ──────────────────────────────────────────────
    # Per-Region Capital Limits
    # ──────────────────────────────────────────────    # Risk Management Defaults
    us_max_capital: float = 1000.0
    us_max_per_trade: Optional[float] = None
    us_min_trade_value: float = 50.0  # Min $50 per trade
    
    india_max_capital: float = 100000.0
    india_max_per_trade: Optional[float] = None
    india_min_trade_value: float = 500.0 # Min ₹500 per trade

    # ──────────────────────────────────────────────
    # AI Provider
    # ──────────────────────────────────────────────
    ai_provider: Literal["openai", "azure_openai", "gemini", "claude"] = "azure_openai"
    openai_api_key: Optional[str] = None
    
    azure_openai_endpoint: Optional[str] = Field(None, validation_alias="AZURE_OPENAI_ENDPOINT")
    azure_openai_api_version: str = Field("2023-05-15", validation_alias="AZURE_OPENAI_API_VERSION")
    azure_openai_deployment_name: Optional[str] = Field(None, validation_alias="AZURE_OPENAI_DEPLOYMENT_NAME")
    azure_openai_api_key: Optional[str] = Field(None, validation_alias="AZURE_OPENAI_API_KEY")

    gemini_api_key: Optional[str] = None
    
    # ──────────────────────────────────────────────
    # Database Configuration
    # ──────────────────────────────────────────────
    db_dir: str = "__databases__"
    trading_db_name: str = "trading_agent.db"
    activity_db_prefix: str = "activity_"

    @property
    def trading_db_path(self) -> str:
        return os.path.join(self.db_dir, self.trading_db_name)
    
    def get_activity_db_path(self, month_key: str) -> str:
        return os.path.join(self.db_dir, f"{self.activity_db_prefix}{month_key}.db")

    # ──────────────────────────────────────────────
    # Logging Configuration
    # ──────────────────────────────────────────────
    log_dir: str = "__logs__"
    log_file_name: str = "agent.jsonl"
    ai_trade_review_file_name: str = "ai_trade_review.jsonl"
    
    @property
    def log_file_path(self) -> str:
        return os.path.join(self.log_dir, self.log_file_name)

    @property
    def ai_trade_review_file_path(self) -> str:
        return os.path.join(self.log_dir, self.ai_trade_review_file_name)

    # ──────────────────────────────────────────────
    # Trading Limits (global)
    # ──────────────────────────────────────────────
    trading_mode: Literal["paper", "live"] = "paper"
    trading_style: Literal["intraday", "short_term", "long_term", "optimistic"] = "intraday"
    max_capital: float = 1000.00
    max_risk_per_trade: float = 0.02

    # ──────────────────────────────────────────────
    # Trailing Stop & Partial Exit (overrides style defaults)
    # ──────────────────────────────────────────────
    trailing_stop_pct: Optional[float] = None
    min_upside_target_pct: Optional[float] = None
    partial_sell_pct: Optional[float] = None
    max_scale_outs: Optional[int] = None

    # ──────────────────────────────────────────────
    # Transaction Fee Estimates
    # ──────────────────────────────────────────────
    us_fee_per_trade: float = 0.50        # Flat $ per order (Robinhood: $0, but SEC/TAF ~$0.05-0.50)
    india_fee_pct: float = 0.001          # 0.1% of trade value (brokerage + STT + exchange)
    india_min_fee: float = 20.0           # Minimum ₹20 per trade

    @property
    def active_style_profile(self) -> TradingStyleProfile:
        """Returns the risk profile for the current trading style,
        with any .env overrides applied on top."""
        base = STYLE_PROFILES.get(self.trading_style, STYLE_PROFILES["intraday"]).model_copy()
        # Apply per-field overrides from .env if set
        if self.max_risk_per_trade != 0.02:  # user changed from default
            base.max_risk_per_trade = self.max_risk_per_trade
        if self.trailing_stop_pct is not None:
            base.trailing_stop_pct = self.trailing_stop_pct
        if self.min_upside_target_pct is not None:
            base.min_upside_target_pct = self.min_upside_target_pct
        if self.partial_sell_pct is not None:
            base.partial_sell_pct = self.partial_sell_pct
        if self.max_scale_outs is not None:
            base.max_scale_outs = self.max_scale_outs
        return base

    # ──────────────────────────────────────────────
    # Per-Region Watchlists (comma-separated tickers in .env)
    # ──────────────────────────────────────────────
    us_watchlist: str = "AAPL,TSLA,SPY,QQQ,MSFT"
    india_watchlist: str = "RELIANCE.NS,TCS.NS,INFY.NS,HDFCBANK.NS,TATASTEEL.NS"
    
    # Legacy watchlist (kept for backward compatibility)
    watchlist: List[StockConfig] = [
        StockConfig(ticker="AAPL"),
        StockConfig(ticker="TSLA"),
        StockConfig(ticker="SPY"),
    ]

    # Settable ticker lists (updated by dynamic config / dashboard)
    _us_tickers_override: Optional[List[str]] = None
    _india_tickers_override: Optional[List[str]] = None

    @property
    def us_tickers(self) -> List[str]:
        """Parsed list of US tickers from the comma-separated env var."""
        if self._us_tickers_override is not None:
            return self._us_tickers_override
        return [t.strip().upper() for t in self.us_watchlist.split(",") if t.strip()]

    @us_tickers.setter
    def us_tickers(self, value: List[str]):
        """Allow dynamic config to override tickers at runtime."""
        self._us_tickers_override = value

    @property
    def india_tickers(self) -> List[str]:
        """Parsed list of India tickers. Auto-appends .NS if no suffix present."""
        if self._india_tickers_override is not None:
            return self._india_tickers_override
        tickers = []
        for t in self.india_watchlist.split(","):
            t = t.strip().upper()
            if not t:
                continue
            if not t.endswith(".NS") and not t.endswith(".BO"):
                t = f"{t}.NS"
            tickers.append(t)
        return tickers

    @india_tickers.setter
    def india_tickers(self, value: List[str]):
        """Allow dynamic config to override tickers at runtime."""
        self._india_tickers_override = value

    @property
    def all_tickers(self) -> List[str]:
        """Combined US + India tickers for the full analysis universe."""
        return self.us_tickers + self.india_tickers

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = AgentSettings()
