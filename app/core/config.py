from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "VoiceGuard AI"
    environment: str = "development"

    database_url: str = "sqlite:///./data/voiceguard.db"

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    # Exotel telephony integration
    exotel_enabled: bool = False
    exotel_account_sid: str | None = None
    exotel_api_key: str | None = None
    exotel_api_token: str | None = None
    exotel_base_url: str = "https://api.in.exotel.com"
    exotel_stream_url: str | None = None
    exotel_webhook_token: str | None = None
    exotel_stream_token: str | None = None
    exotel_caller_id: str | None = None
    exotel_status_callback_url: str | None = None



    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
