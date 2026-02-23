from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_project_root() -> Path:
    """Walk up from this file's directory until we find pyproject.toml."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "pyproject.toml").exists():
            return current
        current = current.parent
    raise FileNotFoundError("Could not find project root (no pyproject.toml found)")


PROJECT_ROOT = _find_project_root()


def _load_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache
def load_llm_config() -> dict:
    return _load_yaml(str(PROJECT_ROOT / "config" / "llm.yml"))


@lru_cache
def load_seed_sources() -> list[dict]:
    data = _load_yaml(str(PROJECT_ROOT / "config" / "seed_sources.yml"))
    return data["sources"]


@lru_cache
def load_seed_entities() -> list[dict]:
    data = _load_yaml(str(PROJECT_ROOT / "config" / "seed_entities.yml"))
    return data["entities"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str
    openrouter_api_key: str
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    brave_api_key: str = ""
    serper_api_key: str = ""
    llm_concurrency: int = 5
    http_rate_limit_per_domain: float = 1.0
    max_alerts_per_day: int = 20

    def load_llm_config(self) -> dict:
        return load_llm_config()

    def load_seed_sources(self) -> list[dict]:
        return load_seed_sources()

    def load_seed_entities(self) -> list[dict]:
        return load_seed_entities()


settings = Settings()
