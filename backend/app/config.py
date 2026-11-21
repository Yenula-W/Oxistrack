"""Application settings, loaded from environment variables (see .env.example)."""
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # .env.shared is committed (team-wide AI settings); a local .env overrides it; real env vars override both.
    model_config = SettingsConfigDict(env_file=(str(BASE_DIR / ".env.shared"), str(BASE_DIR / ".env")), extra="ignore")

    app_name: str = "OxisTrack"
    environment: str = "development"

    # MySQL is the supported database. SQLite URLs also work for quick local trials/tests.
    database_url: str = "mysql+pymysql://oxistrack:oxistrack@127.0.0.1:3306/oxistrack?charset=utf8mb4"

    secret_key: str = "dev-only-change-me"
    access_token_minutes: int = 60 * 24

    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    upload_dir: str = str(BASE_DIR / "storage")
    max_upload_mb: int = 15

    # AI provider: "auto" uses the LLM when LLM_API_KEY is set, otherwise the local rule-based engine.
    ai_provider: str = "auto"  # auto | heuristic | openai_compatible
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: int = 45

    # Second AI: an independent reviewer model (ideally from a different vendor than LLM_MODEL).
    # It breaks ties, double-checks Autopilot's source choices and settles unclear requirement checks.
    reviewer_base_url: str = ""  # defaults to LLM_BASE_URL
    reviewer_api_key: str = ""   # defaults to LLM_API_KEY
    reviewer_model: str = ""     # the reviewer is off until this is set

    auto_create_tables: bool = False  # tests / SQLite trials only; use Alembic otherwise

    @field_validator("database_url")
    @classmethod
    def _use_pymysql(cls, v: str) -> str:
        # Hosts such as Railway hand out plain mysql:// URLs; SQLAlchemy needs the driver named.
        return "mysql+pymysql://" + v[len("mysql://"):] if v.startswith("mysql://") else v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
