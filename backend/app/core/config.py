from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve backend/.env relative to this file so the API behaves the same when
# started from backend/ or from the repository root.
_BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _host_from_url(value: str | None) -> str | None:
    """Return the hostname of a URL (without port), or None when unparseable."""
    if not value:
        return None
    candidate = value.strip()
    if not candidate:
        return None
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    try:
        return urlparse(candidate).hostname or None
    except ValueError:
        return None


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables or .env."""

    DATABASE_URL: str = "sqlite:///./chronoguard.db"
    # Comma-separated browser origins allowed to call the API. Origins never
    # include a trailing slash (browsers send `Origin: https://host`).
    CORS_ORIGINS: str = (
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,"
        "http://localhost:4173,https://chrono-guard-hazel.vercel.app"
    )
    # Optional regex for preview / ephemeral frontend domains, for example:
    #   CORS_ORIGIN_REGEX=https://chrono-guard-.*\.vercel\.app
    CORS_ORIGIN_REGEX: str | None = None
    ENV: str = "dev"
    # Comma-separated public API hosts. `*.fastapicloud.dev` covers the default
    # FastAPI Cloud domain; add a custom API domain when you attach one.
    ALLOWED_HOSTS: str = "localhost,127.0.0.1,testserver,*.fastapicloud.dev"
    # FastAPI Cloud injects FASTAPI_PUBLIC_URL at runtime. Reading it here lets
    # the deployed host be trusted without duplicating it in ALLOWED_HOSTS.
    FASTAPI_PUBLIC_URL: str | None = None
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
    def is_production(self) -> bool:
        return self.ENV.lower() in {"prod", "production"}

    @property
    def cors_origins(self) -> list[str]:
        """Return usable CORS origins (trimmed, no trailing slash).

        In production any non-HTTPS origin is ignored: browsers block mixed
        content, and a stray `http://localhost` entry would otherwise silently
        fail origin matching.
        """
        origins: list[str] = []
        for item in self.CORS_ORIGINS.split(","):
            origin = item.strip().rstrip("/")
            if not origin:
                continue
            if self.is_production and not origin.startswith("https://"):
                continue
            origins.append(origin)
        return origins

    @property
    def cors_origin_regex(self) -> str | None:
        value = (self.CORS_ORIGIN_REGEX or "").strip()
        return value or None

    @property
    def allowed_hosts(self) -> list[str]:
        """Return the Host header values TrustedHostMiddleware accepts.

        Local hosts are intentionally kept in production: platform health
        checks often call the container directly with ``Host: localhost`` or a
        private IP, and a 400 there can fail the whole deployment. The API does
        not build absolute URLs from the Host header, so the residual risk is
        low. Pass an explicit ``ALLOWED_HOSTS`` to tighten this.
        """
        hosts = [item.strip() for item in self.ALLOWED_HOSTS.split(",") if item.strip()]
        hosts = [host for host in hosts if host != "*"]
        public_host = _host_from_url(self.FASTAPI_PUBLIC_URL)
        if public_host and public_host not in hosts:
            hosts.append(public_host)
        return hosts

    @field_validator("CORS_ORIGINS")
    @classmethod
    def validate_cors_origins(cls, value: str) -> str:
        origins = [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]
        if "*" in origins:
            raise ValueError("CORS_ORIGINS must list explicit origins; wildcard origins are not allowed")
        return ",".join(origins)

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        if not self.is_production:
            return self
        if self.DATABASE_URL.startswith("sqlite"):
            raise ValueError(
                "DATABASE_URL must use PostgreSQL when ENV=production. Set it in the "
                "host's environment variables (FastAPI Cloud dashboard / CLI)."
            )
        if not self.cors_origins:
            raise ValueError(
                "CORS_ORIGINS must contain at least one https:// origin when "
                "ENV=production, for example https://your-app.vercel.app"
            )
        if not self.allowed_hosts:
            raise ValueError(
                "ALLOWED_HOSTS must contain your deployment host when ENV=production, "
                "for example myapp.fastapicloud.dev (or *.fastapicloud.dev)"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance."""
    return Settings()
