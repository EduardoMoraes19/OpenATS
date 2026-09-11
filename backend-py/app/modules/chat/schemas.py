from __future__ import annotations

from datetime import datetime

from app.shared.schema import ApiModel


class ChatMessageOut(ApiModel):
    id: int
    sender_id: int
    message: str | None
    reply_to_id: int | None
    sent_at: datetime
    is_system_message: bool
    is_deleted: bool
    # Nullable: an outer join to users, so a message from a since-deleted
    # sender still shows (with these unset) instead of vanishing.
    sender_name: str | None
    sender_last_name: str | None
    sender_avatar: str | None
