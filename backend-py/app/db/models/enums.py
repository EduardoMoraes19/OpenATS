"""Native Postgres enum types, equivalent to backend/src/db/schema/enums.ts.

Every enum here is a genuine `CREATE TYPE ... AS ENUM`, matching the TS
source exactly (value lists and enum names are copied verbatim).
`candidate_interviews.status` and `candidate_interviews.event_type` are
deliberately plain varchar in the TS schema, not enums - see interviews.py.
"""

from __future__ import annotations

import enum

from sqlalchemy import Enum as PgEnum


class EmploymentType(str, enum.Enum):
    full_time = "full_time"
    part_time = "part_time"
    contract = "contract"
    internship = "internship"
    freelance = "freelance"


class SalaryType(str, enum.Enum):
    range = "range"
    fixed = "fixed"


class PayFrequency(str, enum.Enum):
    hourly = "hourly"
    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"
    yearly = "yearly"


class JobStatus(str, enum.Enum):
    draft = "draft"
    inactive = "inactive"
    published = "published"
    closed = "closed"
    archived = "archived"


class StageType(str, enum.Enum):
    screening = "screening"
    interview = "interview"
    offer = "offer"


class OfferMode(str, enum.Enum):
    """Defined in the TS schema but not used by any column today (dead enum) - kept for parity."""

    auto_draft = "auto_draft"
    auto_send = "auto_send"


class OfferStatus(str, enum.Enum):
    draft = "draft"
    sent = "sent"
    viewed = "viewed"
    accepted = "accepted"
    declined = "declined"
    expired = "expired"


class CandidateActivityType(str, enum.Enum):
    offer_created = "offer_created"
    offer_updated = "offer_updated"
    offer_sent = "offer_sent"
    offer_viewed = "offer_viewed"
    offer_accepted = "offer_accepted"
    offer_declined = "offer_declined"
    candidate_hired = "candidate_hired"


class RejectionEmailStatus(str, enum.Enum):
    not_sent = "not_sent"
    draft = "draft"
    sent = "sent"


class InterviewOutcome(str, enum.Enum):
    pending = "pending"
    pass_ = "pass"
    fail = "fail"


class CandidateStatus(str, enum.Enum):
    active = "active"
    rejected = "rejected"
    offered = "offered"
    hired = "hired"
    withdrawn = "withdrawn"


class QuestionType(str, enum.Enum):
    short_answer = "short_answer"
    long_answer = "long_answer"
    checkbox = "checkbox"
    radio = "radio"
    multiple_choice = "multiple_choice"


class TemplateType(str, enum.Enum):
    email = "email"
    event = "event"


class AssessmentStatus(str, enum.Enum):
    pending = "pending"
    started = "started"
    completed = "completed"
    expired = "expired"


class CvAnalysisStatus(str, enum.Enum):
    pending = "pending"
    done = "done"
    failed = "failed"


class MeetingProvider(str, enum.Enum):
    google_meet = "google_meet"


def pg_enum(python_enum: type[enum.Enum], name: str) -> PgEnum:
    """Build a native Postgres ENUM column type bound to `python_enum`, using the
    exact Postgres type name from the TS schema (values_callable keeps the enum
    *value* as the DB literal, e.g. "pass" not "pass_")."""
    return PgEnum(
        python_enum,
        name=name,
        values_callable=lambda enum_cls: [member.value for member in enum_cls],
    )
