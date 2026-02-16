import os
from typing import List, Optional, Literal
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class StockConfig(BaseModel):
    ticker: str
    enabled: bool = True
    asset_type: Literal["stock", "option"] = "stock"

class AgentSettings(BaseSettings):
    # API Keys
    rh_username: Optional[str] = None
    rh_password: Optional[str] = None
    rh_mfa_code: Optional[str] = None
    
    kite_api_key: Optional[str] = None
    kite_access_token: Optional[str] = None

    # ICICI Direct
    icici_api_key: Optional[str] = None
    icici_secret_key: Optional[str] = None
    icici_session_token: Optional[str] = None
    
    ai_provider: Literal["openai", "azure_openai", "gemini", "claude"] = "azure_openai"
    openai_api_key: Optional[str] = None
    
    # Azure OpenAI Specifics
    azure_openai_endpoint: Optional[str] = Field(None, validation_alias="AZURE_OPENAI_ENDPOINT")
    azure_openai_api_version: str = Field("2023-05-15", validation_alias="AZURE_OPENAI_API_VERSION")
    azure_openai_deployment_name: Optional[str] = Field(None, validation_alias="AZURE_OPENAI_DEPLOYMENT_NAME")
    azure_openai_api_key: Optional[str] = Field(None, validation_alias="AZURE_OPENAI_API_KEY")

    gemini_api_key: Optional[str] = None
    
    # Trading Limits
    trading_mode: Literal["paper", "live"] = "paper"
    max_capital: float = 1000.00
    max_risk_per_trade: float = 0.02  # 2% max risk per trade
    
    # Watchlist
    watchlist: List[StockConfig] = [
        StockConfig(ticker="AAPL"),
        StockConfig(ticker="TSLA"),
        StockConfig(ticker="SPY"),
        # Add NIFTY/SENSEX for India if needed, e.g. "^NSEI"
    ]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = AgentSettings()
