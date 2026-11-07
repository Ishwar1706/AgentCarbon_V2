"""Central configuration. Everything is driven by environment variables / .env."""
from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    app_name: str = "AgentCarbon API"

    # SQLite works out of the box. Use a postgresql+psycopg:// URL for Postgres.
    database_url: str = f"sqlite:///{(PROJECT_ROOT / 'data' / 'agentcarbon.db').as_posix()}"

    jwt_secret_key: str = ""
    jwt_expire_minutes: int = 480

    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    groq_call_delay_seconds: float = 2.0
    groq_max_retries: int = 5
    groq_request_timeout_seconds: float = 120.0
    groq_reasoning_effort: str = "low"
    groq_max_completion_tokens: int = 4000
    agent_debate_rounds: int = 1  # 0 = skip rebuttal round (fewer tokens)

    demo_mode: bool = True
    demo_password: str = "Demo@12345"
    seed_on_startup: bool = True

    upload_dir: str = "uploads"
    report_dir: str = "reports"
    data_dir: str = "data"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"), extra="ignore"
    )

    def path(self, name: str) -> Path:
        p = Path(getattr(self, name))
        p = p if p.is_absolute() else PROJECT_ROOT / p
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def groq_configured(self) -> bool:
        return bool(self.groq_api_key.strip())

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
if not settings.database_url.strip():
    settings.database_url = Settings.model_fields["database_url"].default


@lru_cache
def jwt_secret() -> str:
    """Use JWT_SECRET_KEY when set, otherwise create and persist a random key."""
    if settings.jwt_secret_key.strip():
        return settings.jwt_secret_key.strip()
    key_file = settings.path("data_dir") / "jwt_secret.key"
    if key_file.exists():
        return key_file.read_text().strip()
    key = secrets.token_urlsafe(48)
    key_file.write_text(key)
    return key
