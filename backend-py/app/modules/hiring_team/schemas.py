from __future__ import annotations

from datetime import datetime

from app.shared.schema import ApiModel


class HiringTeamMemberOut(ApiModel):
    id: int
    job_id: int
    user_id: int
    added_at: datetime
    first_name: str
    last_name: str
    email: str
    avatar_url: str | None


class AddHiringTeamMemberIn(ApiModel):
    user_id: int
