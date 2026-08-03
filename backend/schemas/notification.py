from pydantic import BaseModel
from datetime import datetime

class NotificationOut(BaseModel):
    id: int
    user_id: int
    from_user_id: int | None = None
    type: str
    message: str
    post_id: int | None = None
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True