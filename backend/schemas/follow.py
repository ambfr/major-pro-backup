from pydantic import BaseModel
from datetime import datetime


class FollowResponse(BaseModel):
    id: int
    follower_id: int
    following_id: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class FollowRequest(BaseModel):
    following_id: int


class FollowAction(BaseModel):
    follower_id: int