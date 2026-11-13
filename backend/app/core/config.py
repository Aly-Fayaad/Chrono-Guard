from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables or .env."""

    DATABASE_URL: str = "sqlite:///./chronoguard.db"
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000"
    ENV: str = "dev"
    ANALYSIS_ENGINE: str = "app.ml.crew_health_engine:CrewHealthEngine"
    # Operational mission clock (single source of truth for MET / D+ labels).
    # 24.65 h is the Martian sol. It is an operational convention, not a
    # replacement for the published 24 h circadian equations.
    MISSION_EPOCH: str = "2026-10-30T07:00:00Z"
    MISSION_DAY_HOURS: float = 24.65
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        """Return CORS_ORIGINS as a list of trimmed origins."""
        return [item.strip() for item in self.CORS_ORIGINS.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance."""
    return Settings()
