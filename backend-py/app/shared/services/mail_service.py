"""Resend-backed email sending, equivalent to
backend/src/shared/services/mail.service.ts.

No retry/queueing here, same as the TS code: sends are synchronous from the
caller's point of view, and callers that want fire-and-forget behavior wrap
the call themselves (e.g. `asyncio.create_task(...)` with its own
try/except), matching how the TS controllers `.catch()` + log instead of
blocking the response.

Every public function here is `async` even though the underlying `resend`
client is a blocking, synchronous HTTP client: unlike Node (where `await
fetch(...)` never blocks the event loop), calling a synchronous network
client directly from an `async def` route handler in Python blocks the
*entire* asyncio event loop for the duration of the call - every other
in-flight request stalls until Resend's API responds. `asyncio.to_thread`
runs the blocking call on a worker thread instead, matching Node's actual
non-blocking behavior rather than a naive line-by-line port of it.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

import resend

from app.logging import get_logger
from app.settings import settings

logger = get_logger(__name__)

resend.api_key = settings.resend_api_key

_FROM_EMAIL = settings.resend_from_email


def _format_datetime(value: datetime) -> tuple[str, str]:
    """en-US date/time formatting including timezone name, matching
    toLocaleDateString/toLocaleTimeString in the TS templates."""
    return value.strftime("%A, %B %-d, %Y"), value.strftime("%I:%M %p %Z").strip()


def _email_card(*, title: str, body_html: str) -> str:
    return f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 600px; margin: 0 auto;">
      <div style="background: #0a0a0a; color: #ffffff; padding: 32px; border-radius: 16px 16px 0 0;">
        <h1 style="margin: 0; font-size: 20px;">{title}</h1>
      </div>
      <div style="background: #ffffff; border: 1px solid #e5e5e5; border-top: none; padding: 32px; border-radius: 0 0 16px 16px;">
        {body_html}
        <p style="color: #737373; font-size: 12px; margin-top: 32px; text-align: center;">Powered by featTalent</p>
      </div>
    </div>
    """


def _email_button(*, label: str, url: str) -> str:
    return (
        f'<a href="{url}" style="display: inline-block; background: #0a0a0a; color: #ffffff; '
        f'text-decoration: none; padding: 12px 24px; border-radius: 8px; font-weight: 600; '
        f'margin: 16px 0;">{label}</a>'
    )


def _email_detail_row(label: str, value: str) -> str:
    return (
        f'<tr><td style="padding: 8px 0; color: #737373; font-size: 14px;">{label}</td>'
        f'<td style="padding: 8px 0; font-weight: 600; font-size: 14px;">{value}</td></tr>'
    )


def _send_email_blocking(*, to: str, subject: str, html: str) -> None:
    try:
        resend.Emails.send(
            {
                "from": f"featTalent <{_FROM_EMAIL}>",
                "to": [to],
                "subject": subject,
                "html": html,
            }
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("failed to send email to %s: %s", to, exc)
        raise


async def send_email(*, to: str, subject: str, html: str) -> None:
    await asyncio.to_thread(_send_email_blocking, to=to, subject=subject, html=html)


async def send_offer_email(*, to: str, candidate_name: str, job_title: str, review_url: str) -> None:
    body = f"""
    <p>Hi {candidate_name},</p>
    <p>We're excited to share an offer for the <strong>{job_title}</strong> position.</p>
    {_email_button(label="Review Your Offer", url=review_url)}
    """
    await send_email(to=to, subject=f"Your offer for {job_title}", html=_email_card(title="You have a new offer", body_html=body))


async def send_rejection_email(*, to: str, candidate_name: str, job_title: str, body_html: str) -> None:
    await send_email(
        to=to,
        subject=f"Update on your application for {job_title}",
        html=_email_card(title="Application Update", body_html=body_html),
    )


async def send_assessment_invite_email(*, to: str, subject: str, body_html: str) -> None:
    await send_email(to=to, subject=subject, html=body_html)


async def send_assessment_completion_email(
    *, to: str, candidate_name: str, auto_submit_reason: str | None = None
) -> None:
    if auto_submit_reason:
        body = f"""
        <p>Hi {candidate_name},</p>
        <p>Your assessment was automatically submitted: {auto_submit_reason}.</p>
        """
        subject = "Your assessment was auto-submitted"
    else:
        body = f"""
        <p>Hi {candidate_name},</p>
        <p>Thanks for completing your assessment. Our team will review your results soon.</p>
        """
        subject = "Assessment completed"
    await send_email(to=to, subject=subject, html=_email_card(title="Assessment Completed", body_html=body))


async def send_interview_invite_email(
    *, to: str, candidate_name: str, job_title: str, scheduled_at: datetime, meeting_url: str | None
) -> None:
    date_str, time_str = _format_datetime(scheduled_at)
    meeting_html = f'<p><a href="{meeting_url}">{meeting_url}</a></p>' if meeting_url else ""
    body = f"""
    <p>Hi {candidate_name},</p>
    <p>Your interview for <strong>{job_title}</strong> is scheduled.</p>
    <table>{_email_detail_row("Date", date_str)}{_email_detail_row("Time", time_str)}</table>
    {meeting_html}
    """
    await send_email(to=to, subject=f"Interview scheduled: {job_title}", html=_email_card(title="Interview Scheduled", body_html=body))


async def send_interview_slot_email(
    *, to: str, candidate_name: str, job_title: str, select_url: str
) -> None:
    body = f"""
    <p>Hi {candidate_name},</p>
    <p>Please pick a time that works for your interview for <strong>{job_title}</strong>.</p>
    {_email_button(label="Choose a Time", url=select_url)}
    """
    await send_email(to=to, subject=f"Pick your interview time: {job_title}", html=_email_card(title="Choose Your Interview Time", body_html=body))


async def send_interview_confirmation_email(
    *, to: str, candidate_name: str, job_title: str, scheduled_at: datetime, meeting_url: str | None
) -> None:
    date_str, time_str = _format_datetime(scheduled_at)
    meeting_html = f'<p><a href="{meeting_url}">{meeting_url}</a></p>' if meeting_url else ""
    body = f"""
    <p>Hi {candidate_name},</p>
    <p>Your interview for <strong>{job_title}</strong> is confirmed.</p>
    <table>{_email_detail_row("Date", date_str)}{_email_detail_row("Time", time_str)}</table>
    {meeting_html}
    """
    await send_email(to=to, subject=f"Interview confirmed: {job_title}", html=_email_card(title="Interview Confirmed", body_html=body))


async def send_interview_cancellation_email(*, to: str, candidate_name: str, job_title: str) -> None:
    body = f"""
    <p>Hi {candidate_name},</p>
    <p>Your interview for <strong>{job_title}</strong> has been cancelled. We'll reach out if we need to reschedule.</p>
    """
    await send_email(to=to, subject=f"Interview cancelled: {job_title}", html=_email_card(title="Interview Cancelled", body_html=body))
