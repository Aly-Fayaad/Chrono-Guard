from functools import lru_cache
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve backend/.env relative to this file so the API behaves the same when
# started from backend/ or from the repository root.
_BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables or .env."""

    DATABASE_URL: str = "sqlite:///./chronoguard.db"
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000"
    ENV: str = "dev"
    ALLOWED_HOSTS: str = "localhost,127.0.0.1,testserver"
    ANALYSIS_ENGINE: str = "app.ml.crew_health_engine:CrewHealthEngine"
    # Operational mission clock (single source of truth for MET / D+ labels).
    # 24.65 h is the Martian sol. It is an operational convention, not a
    # replacement for the published 24 h circadian equations.
    MISSION_EPOCH: str = "2026-10-30T07:00:00Z"
    MISSION_DAY_HOURS: float = 24.65
    model_config = SettingsConfigDict(
        env_file=_BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origins(self) -> list[str]:
        """Return CORS_ORIGINS as a list of trimmed origins."""
        return [item.strip() for item in self.CORS_ORIGINS.split(",") if item.strip()]

    @property
    def allowed_hosts(self) -> list[str]:
        return [item.strip() for item in self.ALLOWED_HOSTS.split(",") if item.strip()]

    @field_validator("CORS_ORIGINS")
    @classmethod
    def validate_cors_origins(cls, value: str) -> str:
        origins = [origin.strip() for origin in value.split(",") if origin.strip()]
        if "*" in origins:
            raise ValueError("CORS_ORIGINS must list explicit origins; wildcard origins are not allowed")
        return ",".join(origins)

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        if self.ENV.lower() not in {"prod", "production"}:
            return self
        if self.DATABASE_URL.startswith("sqlite"):
            raise ValueError("DATABASE_URL must use PostgreSQL when ENV=production")
        if any(not origin.startswith("https://") for origin in self.cors_origins):
            raise ValueError("CORS_ORIGINS must use HTTPS origins when ENV=production")
        if any(host in {"*", "localhost", "127.0.0.1", "testserver"} for host in self.allowed_hosts):
            raise ValueError("ALLOWED_HOSTS must contain only deployment hosts when ENV=production")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance."""
    return Settings()
