"""
Chat module — Pydantic schemas
"""
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from enum import Enum


class MessageType(str, Enum):
    text = "text"
    image = "image"
    video = "video"
    voice = "voice"
    post_share = "post_share"
    reel_share = "reel_share"
    gif = "gif"


# ---------- Requests ----------

class MessageCreate(BaseModel):
    conversation_id: int
    type: MessageType = MessageType.text
    content: Optional[str] = None
    media_url: Optional[str] = None
    shared_post_id: Optional[int] = None
    shared_reel_id: Optional[int] = None
    reply_to_id: Optional[int] = None


class ReactionCreate(BaseModel):
    emoji: str


class ConversationCreate(BaseModel):
    participant_ids: List[int]
    is_group: bool = False
    title: Optional[str] = None


# ---------- Responses ----------

class AnalysisOut(BaseModel):
    sentiment_label: Optional[str]
    sentiment_score: Optional[float]
    emotion_label: Optional[str]
    emotion_score: Optional[float]
    is_sarcastic: bool
    sarcasm_score: Optional[float]
    risk_score: Optional[float]
    explanation: Optional[str]

    class Config:
        from_attributes = True


class MessageOut(BaseModel):
    id: int
    conversation_id: int
    sender_id: int
    type: MessageType
    content: Optional[str]
    media_url: Optional[str]
    reply_to_id: Optional[int]
    is_unsent: bool
    is_read: bool
    created_at: datetime
    analysis: Optional[AnalysisOut] = None  # only exposed to owner/moderation context

    class Config:
        from_attributes = True


class ConversationOut(BaseModel):
    id: int
    is_group: bool
    title: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class RiskPatternOut(BaseModel):
    negative_ratio: float
    trend_slope: float
    consecutive_negative_days: int
    intervention_count: int
    should_intervene: bool