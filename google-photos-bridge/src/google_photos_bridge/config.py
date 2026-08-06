from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    photo_provider: Literal["auto", "immich", "google_web"] = "auto"

    mcp_bearer_token: str | None = None
    mcp_host: str = "127.0.0.1"
    mcp_port: int = Field(default=8765, ge=1, le=65535)

    immich_url: str = "http://127.0.0.1:2283"
    immich_api_key: str | None = None
    immich_request_timeout: float = Field(default=30.0, gt=0, le=300)

    google_photos_debug_port: int = Field(default=9222, ge=1, le=65535)
    google_photos_browser_path: str | None = None
    google_photos_headless: bool = False
    google_photos_cache_dir: Path = Path("./.cache/google-photos-bridge")
    google_photos_scroll_rounds: int = Field(default=12, ge=1, le=100)
    google_photos_wait_seconds: float = Field(default=3.0, ge=0.5, le=30)

    @field_validator("mcp_bearer_token", "immich_api_key", "google_photos_browser_path")
    @classmethod
    def empty_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("immich_url")
    @classmethod
    def normalize_immich_url(cls, value: str) -> str:
        return value.rstrip("/")
