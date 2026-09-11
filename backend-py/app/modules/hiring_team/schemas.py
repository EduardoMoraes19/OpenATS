from __future__ import annotations

from app.shared.schema import ApiModel, UtcDatetime


class HiringTeamMemberOut(ApiModel):
    id: int
    job_id: int
    user_id: int
    added_at: UtcDatetime
    first_name: str
    last_name: str
    email: str
    avatar_url: str | None


class AddHiringTeamMemberIn(ApiModel):
    user_id: int
