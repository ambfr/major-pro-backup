# backend/schemas/reels.py
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class AudioOut(BaseModel):
    id: int
    title: str
    artist: Optional[str] = None
    audio_url: str
    duration_seconds: Optional[float] = None
    reel_count: Optional[int] = 0  # how many reels use this audio

    class Config:
        from_attributes = True


class ReelCreatorOut(BaseModel):
    id: int
    username: str
    profile_picture_url: Optional[str] = None
    is_following: Optional[bool] = False

    class Config:
        from_attributes = True


class ReelOut(BaseModel):
    id: int
    caption: Optional[str] = None
    hashtags: List[str] = []
    mentions: List[str] = []
    video_url: str
    thumbnail_url: Optional[str] = None
    duration_seconds: Optional[float] = None
    created_at: datetime

    creator: ReelCreatorOut
    audio: Optional[AudioOut] = None

    like_count: int = 0
    comment_count: int = 0
    share_count: int = 0
    save_count: int = 0
    view_count: int = 0

    is_liked: bool = False
    is_saved: bool = False

    # AI layer (from your existing pipeline)
    sentiment: Optional[str] = None
    emotion: Optional[str] = None
    risk_score: Optional[float] = None

    # Recommendation explainability
    rank_score: Optional[float] = None
    rank_reason: Optional[str] = None  # e.g. "Because you follow @x and often watch similar audio"

    class Config:
        from_attributes = True


class FeedResponse(BaseModel):
    reels: List[ReelOut]
    next_cursor: Optional[str] = None


class CommentCreate(BaseModel):
    text: str
    parent_comment_id: Optional[int] = None  # for replies


class CommentOut(BaseModel):
    id: int
    user: ReelCreatorOut
    text: str
    created_at: datetime
    reply_count: int = 0

    class Config:
        from_attributes = True


class ViewEventIn(BaseModel):
    watch_seconds: float
    reel_duration: Optional[float] = None
    completed: bool = False


class ShareIn(BaseModel):
    shared_to_user_id: Optional[int] = None
    method: str = "link"  # "dm" | "link" | "external"


class NotInterestedIn(BaseModel):
    reason: Optional[str] = None


class ReportIn(BaseModel):
    reason: str
    details: Optional[str] = None