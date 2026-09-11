from __future__ import annotations

from app.shared.schema import ApiModel


class ConnectionStatusOut(ApiModel):
    provider: str
    connected: bool
    account_email: str | None


class AuthorizeUrlOut(ApiModel):
    url: str
