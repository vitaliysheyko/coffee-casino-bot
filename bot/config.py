from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: str
    admin_ids: list[int] = []
    database_url: str = "sqlite+aiosqlite:///./data/coffee_casino.db"
    web_port: int = 8080
    web_url: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
