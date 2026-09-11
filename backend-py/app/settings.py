"""Environment settings, equivalent to backend/src/config/env.ts.

Field names are identical to backend/.env.example on purpose: existing .env
files and deploy scripts must keep working unmodified. Core settings (DB,
Redis, auth, encryption, storage, email, AI, port) are validated eagerly at
process start, matching env.ts's validateEnv(). Peripheral settings (Google
Calendar/OAuth, rate limits) are optional here too, mirroring the TS code's
"read ad hoc, default/throw at point of use" split.
"""

from __future__ import annotations

import base64
import sys

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Core / DB / cache
    database_url: str = Field(alias="DATABASE_URL")
    redis_url: str = Field(default="redis://localhost:6379", alias="REDIS_URL")
    port: int = Field(default=8080, alias="PORT", gt=0)

    # Auth (self-hosted JWT, modeled on labs-contaja's admin auth)
    secret_key: str = Field(alias="SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(default=30, alias="ACCESS_TOKEN_EXPIRE_MINUTES", gt=0)

    # Encryption (integration credentials + OAuth state tokens)
    encryption_key: str = Field(alias="ENCRYPTION_KEY")

    # CORS / frontend
    frontend_url: str = Field(alias="FRONTEND_URL")

    # Cloudflare R2 / S3-compatible storage
    r2_endpoint: str = Field(alias="R2_ENDPOINT")
    r2_access_key_id: str = Field(alias="R2_ACCESS_KEY_ID")
    r2_secret_access_key: str = Field(alias="R2_SECRET_ACCESS_KEY")
    r2_bucket_name: str = Field(alias="R2_BUCKET_NAME")
    r2_public_url: str = Field(alias="R2_PUBLIC_URL")
    r2_public_endpoint: str | None = Field(default=None, alias="R2_PUBLIC_ENDPOINT")
    signed_url_ttl_seconds: int = Field(default=900, alias="SIGNED_URL_TTL_SECONDS", gt=0)

    # Email (Resend)
    resend_api_key: str = Field(alias="RESEND_API_KEY")
    resend_from_email: str = Field(alias="RESEND_FROM_EMAIL")

    # AI (Gemini)
    gemini_api_key: str = Field(alias="GEMINI_API_KEY")

    # Rate limiting (peripheral, has defaults like the TS code)
    rate_limit_api: int = Field(default=1000, alias="RATE_LIMIT_API")
    rate_limit_expensive: int = Field(default=60, alias="RATE_LIMIT_EXPENSIVE")

    # Google Calendar (service account) - peripheral, read ad hoc in TS
    google_service_account_json: str | None = Field(
        default=None, alias="GOOGLE_SERVICE_ACCOUNT_JSON"
    )
    google_calendar_id: str = Field(default="primary", alias="GOOGLE_CALENDAR_ID")
    google_calendar_allow_attendees: str | None = Field(
        default=None, alias="GOOGLE_CALENDAR_ALLOW_ATTENDEES"
    )

    # Google OAuth (per-user Meet integration) - peripheral, read ad hoc in TS
    google_oauth_client_id: str | None = Field(default=None, alias="GOOGLE_OAUTH_CLIENT_ID")
    google_oauth_client_secret: str | None = Field(
        default=None, alias="GOOGLE_OAUTH_CLIENT_SECRET"
    )
    google_oauth_redirect_uri: str | None = Field(default=None, alias="GOOGLE_OAUTH_REDIRECT_URI")

    @field_validator("encryption_key")
    @classmethod
    def _validate_encryption_key(cls, value: str) -> str:
        try:
            decoded = base64.b64decode(value, validate=True)
        except Exception as exc:  # noqa: BLE001 - re-raised with a clearer message below
            raise ValueError("ENCRYPTION_KEY must be valid base64") from exc
        if len(decoded) != 32:
            raise ValueError("ENCRYPTION_KEY must decode to exactly 32 bytes")
        return value

    @property
    def google_calendar_allow_attendees_enabled(self) -> bool:
        """Exact `=== "true"` semantics from google-calendar.service.ts - not a generic bool parse."""
        return self.google_calendar_allow_attendees == "true"


def load_settings() -> Settings:
    """Load and validate settings, exiting the process on failure (mirrors env.ts)."""
    try:
        return Settings()
    except Exception as exc:  # noqa: BLE001
        print("Missing or invalid environment variables. See backend-py/.env.example.", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        sys.exit(1)


settings = load_settings()
