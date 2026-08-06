from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bizatlas_mode: str = "snapshot"
    bizatlas_db_path: str = str(ROOT / "data" / "bizatlas.sqlite")
    bizatlas_upload_dir: str = str(ROOT / "uploads")
    bizatlas_export_dir: str = str(ROOT / "exports")
    bizatlas_providers_registry: str = str(ROOT / "content" / "providers" / "registry.yaml")
    bizatlas_rules_dir: str = str(ROOT / "content" / "rules")

    tushare_token: str = ""
    tianyancha_token: str = ""
    qichacha_token: str = ""
    company_json_dir: str = str(ROOT / "content" / "fixtures" / "company_json")

    llm_provider: str = "openai_compatible"
    llm_api_base: str = ""
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"

    api_host: str = "127.0.0.1"
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def root(self) -> Path:
        return ROOT


@lru_cache
def get_settings() -> Settings:
    return Settings()
