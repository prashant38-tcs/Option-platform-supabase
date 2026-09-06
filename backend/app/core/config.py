from __future__ import annotations
from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    fyers_app_id: str = Field(default="", description="Your FYERS App ID (compliant '...200' app for Live)")
    fyers_secret_id: str = Field(default="", description="FYERS App Secret")
    fyers_redirect_uri: str = Field(default="", description="Redirect URI registered on FYERS API dashboard")
    fyers_pin: str = Field(default="", description="FYERS trading PIN")
    fyers_static_ip: Optional[str] = Field(default=None, description="Whitelisted static IP for compliant App")
    fyers_access_token_cache_key: str = "fyers:access_token"

    groq_api_key: str = Field(default="", description="Free API key from console.groq.com")
    groq_model: str = "openai/gpt-oss-120b"
    gemini_api_key: str = Field(default="", description="Free API key from aistudio.google.com")
    gemini_model: str = "gemini-2.5-flash"

    database_url: str = Field(default="", description="postgresql+asyncpg://user:pass@host:port/db")
    redis_url: str = Field(default="", description="redis://host:port/0")

    moneycontrol_rss_urls: list[str] = Field(
        default_factory=lambda: [
            "https://www.moneycontrol.com/rss/marketreports.xml",
            "https://www.moneycontrol.com/rss/business.xml",
            "https://www.moneycontrol.com/rss/results.xml",
        ]
    )

    default_trading_mode: str = "ADVISORY"
    cycle_interval_seconds: int = 60
    risk_free_rate: float = Field(default=0.065, description="Approx. India 10Y G-Sec / repo-linked rate")
    market_hours_only: bool = True

    scheduler_default_underlyings: list[str] = Field(
        default_factory=lambda: ["NIFTY50", "NIFTYBANK", "FINNIFTY", "SENSEX"],
        description="Underlyings the scheduler starts polling automatically on app startup.",
    )

    cors_allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"],
    )

    outbound_proxy_url: Optional[str] = Field(default=None, description="e.g. http://user:pass@proxy-host:port")

    def fyers_credentials_present(self) -> bool:
        return bool(self.fyers_app_id and self.fyers_secret_id and self.fyers_redirect_uri)

    def groq_configured(self) -> bool:
        return bool(self.groq_api_key)

    def gemini_configured(self) -> bool:
        return bool(self.gemini_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
