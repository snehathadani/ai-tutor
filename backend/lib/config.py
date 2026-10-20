from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    livekit_url: str
    livekit_api_key: str
    livekit_api_secret: str

    deepseek_api_key: str
    deepseek_model: str = "deepseek-v4-pro"
    deepseek_base_url: str = "https://api.deepseek.com"

    redis_url: str = "redis://redis:6379/0"

    stt_model: str = "deepgram/nova-3"
    tts_model: str = "cartesia/sonic-3.5"
    tts_voice: str = "79a125e8-cd45-4c13-8a67-188112f4dd22"

    log_level: str = "INFO"


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def set_settings(settings: Settings) -> None:
    global _settings
    _settings = settings
