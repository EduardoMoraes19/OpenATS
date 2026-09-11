"""Meeting-provider registry, equivalent to backend/src/shared/integrations/registry.ts."""

from __future__ import annotations

from app.db.models.enums import MeetingProvider
from app.shared.integrations.google_meet_provider import google_meet_provider
from app.shared.integrations.types import MeetingProviderClient

_REGISTRY: dict[MeetingProvider, MeetingProviderClient] = {
    MeetingProvider.google_meet: google_meet_provider,
}


def get_provider_client(provider: MeetingProvider) -> MeetingProviderClient:
    return _REGISTRY[provider]
