"""Service-account Google Calendar sync, equivalent to
backend/src/shared/services/google-calendar.service.ts.

Distinct from the per-user OAuth Google Meet provider
(shared/integrations/google_meet_provider.py): this uses one shared service
account to create/update/delete interview events on a single company
calendar, independent of which interviewer is assigned.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import Resource, build

from app.logging import get_logger
from app.settings import settings

logger = get_logger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

_calendar_client: Resource | None = None


def _get_calendar_client() -> Resource:
    global _calendar_client
    if _calendar_client is not None:
        return _calendar_client

    if not settings.google_service_account_json:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON is required for calendar sync")

    info = json.loads(settings.google_service_account_json)
    credentials = service_account.Credentials.from_service_account_info(info, scopes=_SCOPES)
    _calendar_client = build("calendar", "v3", credentials=credentials)
    return _calendar_client


def _calendar_id() -> str:
    return settings.google_calendar_id


class CalendarEventInput:
    def __init__(
        self,
        *,
        candidate_name: str,
        job_title: str,
        stage_name: str | None,
        notes: str | None,
        meeting_url: str | None,
        scheduled_at: datetime,
        duration_minutes: int,
        attendee_emails: list[str] | None = None,
    ) -> None:
        self.candidate_name = candidate_name
        self.job_title = job_title
        self.stage_name = stage_name
        self.notes = notes
        self.meeting_url = meeting_url
        self.scheduled_at = scheduled_at
        self.duration_minutes = duration_minutes
        self.attendee_emails = attendee_emails or []


def _build_description(event_input: CalendarEventInput) -> str:
    lines = []
    if event_input.stage_name:
        lines.append(f"Stage: {event_input.stage_name}")
    if event_input.notes:
        lines.append(f"Notes: {event_input.notes}")
    if event_input.meeting_url:
        lines.append(f"Meeting: {event_input.meeting_url}")
    if event_input.attendee_emails and not settings.google_calendar_allow_attendees_enabled:
        lines.append(f"Attendees: {', '.join(event_input.attendee_emails)}")
    return "\n".join(lines)


def create_calendar_event(event_input: CalendarEventInput) -> str:
    client = _get_calendar_client()
    end_time = event_input.scheduled_at + timedelta(minutes=event_input.duration_minutes)

    body: dict[str, Any] = {
        "summary": f"Interview: {event_input.candidate_name} — {event_input.job_title}",
        "description": _build_description(event_input),
        "location": event_input.meeting_url or "",
        "start": {"dateTime": event_input.scheduled_at.isoformat(), "timeZone": "UTC"},
        "end": {"dateTime": end_time.isoformat(), "timeZone": "UTC"},
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "email", "minutes": 1440},
                {"method": "popup", "minutes": 30},
            ],
        },
    }
    if settings.google_calendar_allow_attendees_enabled and event_input.attendee_emails:
        body["attendees"] = [{"email": email} for email in event_input.attendee_emails]

    created = client.events().insert(calendarId=_calendar_id(), body=body).execute()
    event_id = created.get("id")
    if not event_id:
        raise RuntimeError("Google Calendar did not return an event id")
    return event_id


def update_calendar_event(google_event_id: str, event_input: CalendarEventInput) -> None:
    client = _get_calendar_client()
    end_time = event_input.scheduled_at + timedelta(minutes=event_input.duration_minutes)

    body: dict = {
        "summary": f"Interview: {event_input.candidate_name} — {event_input.job_title}",
        "start": {"dateTime": event_input.scheduled_at.isoformat(), "timeZone": "UTC"},
        "end": {"dateTime": end_time.isoformat(), "timeZone": "UTC"},
    }
    if settings.google_calendar_allow_attendees_enabled and event_input.attendee_emails:
        body["attendees"] = [{"email": email} for email in event_input.attendee_emails]

    client.events().patch(calendarId=_calendar_id(), eventId=google_event_id, body=body).execute()


def delete_calendar_event(google_event_id: str) -> None:
    client = _get_calendar_client()
    client.events().delete(
        calendarId=_calendar_id(), eventId=google_event_id, sendUpdates="all"
    ).execute()
