from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "ParcelPilot Assist API"
    app_version: str = "0.1.0"
    debug: bool = True

    groq_api_key: str = ""
    groq_api_key_2: str = ""
    groq_model: str = "openai/gpt-oss-20b"

    gemini_api_key: str = ""
    gemini_embedding_model: str = "gemini-embedding-001"
    gemini_embedding_dimensions: int = 768

    database_url: str = "postgresql://user:password@localhost:5432/parcelpilot"
    chroma_path: str = "./.chroma"
    data_path: str = "../../data"

    jwt_secret: str = "change-me-in-dev"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480

    snapshot_tz: str = "Asia/Kolkata"
    snapshot_at: str = "2026-08-16T11:00:00+05:30"

    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def resolved_data_path(self) -> Path:
        base = Path(__file__).resolve().parent.parent
        return (base / self.data_path).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
