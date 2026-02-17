import os
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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
    trading_style: Literal["intraday", "short_term", "long_term"] = "intraday"
    max_capital: float = 1000.00
    max_risk_per_trade: float = 0.02

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

    @property
    def us_tickers(self) -> List[str]:
        """Parsed list of US tickers from the comma-separated env var."""
        return [t.strip().upper() for t in self.us_watchlist.split(",") if t.strip()]
    
    @property
    def india_tickers(self) -> List[str]:
        """Parsed list of India tickers. Auto-appends .NS if no suffix present."""
        tickers = []
        for t in self.india_watchlist.split(","):
            t = t.strip().upper()
            if not t:
                continue
            if not t.endswith(".NS") and not t.endswith(".BO"):
                t = f"{t}.NS"
            tickers.append(t)
        return tickers

    @property
    def all_tickers(self) -> List[str]:
        """Combined US + India tickers for the full analysis universe."""
        return self.us_tickers + self.india_tickers

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = AgentSettings()
