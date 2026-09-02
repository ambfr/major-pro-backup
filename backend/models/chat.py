"""
Chat module — SQLAlchemy models
Conversation / Message / Reaction / AI analysis tables.
"""
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, ForeignKey,
    Enum, Float, JSON, Table
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.database import Base  # adjust import to your project's Base


# ---------- Enums ----------

class MessageType(str, enum.Enum):
    text = "text"
    image = "image"
    video = "video"
    voice = "voice"
    post_share = "post_share"
    reel_share = "reel_share"
    gif = "gif"


class ConversationRequestStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    declined = "declined"
    blocked = "blocked"


# ---------- Association table for group participants ----------

conversation_participants = Table(
    "conversation_participants",
    Base.metadata,
    Column("conversation_id", Integer, ForeignKey("conversations.id"), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("joined_at", DateTime(timezone=True), server_default=func.now()),
    Column("is_admin", Boolean, default=False),
    Column("muted", Boolean, default=False),
)


# ---------- Core tables ----------

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    is_group = Column(Boolean, default=False)
    title = Column(String, nullable=True)  # group name, null for 1:1
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    request_status = Column(Enum(ConversationRequestStatus), default=ConversationRequestStatus.pending)

    participants = relationship("User", secondary=conversation_participants, backref="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    type = Column(Enum(MessageType), default=MessageType.text)
    content = Column(Text, nullable=True)          # text body, or caption for media
    media_url = Column(String, nullable=True)       # Cloudinary URL for image/video/voice
    shared_post_id = Column(Integer, ForeignKey("posts.id"), nullable=True)
    shared_reel_id = Column(Integer, ForeignKey("reels.id"), nullable=True)

    reply_to_id = Column(Integer, ForeignKey("messages.id"), nullable=True)
    forwarded_from_id = Column(Integer, ForeignKey("messages.id"), nullable=True)

    is_deleted_for_sender = Column(Boolean, default=False)
    is_unsent = Column(Boolean, default=False)
    is_read = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    conversation = relationship("Conversation", back_populates="messages")
    reply_to = relationship("Message", remote_side=[id])
    reactions = relationship("MessageReaction", back_populates="message", cascade="all, delete-orphan")
    analysis = relationship("MessageAnalysis", back_populates="message", uselist=False, cascade="all, delete-orphan")


class MessageReaction(Base):
    __tablename__ = "message_reactions"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    emoji = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    message = relationship("Message", back_populates="reactions")


# ---------- AI analysis tables ----------

class MessageAnalysis(Base):
    """Per-message AI analysis result — sentiment, emotion, sarcasm."""
    __tablename__ = "message_analysis"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id"), nullable=False, unique=True)

    sentiment_label = Column(String, nullable=True)     # positive / negative / neutral
    sentiment_score = Column(Float, nullable=True)       # confidence 0-1

    emotion_label = Column(String, nullable=True)        # sadness / anger / fear / joy / ...
    emotion_score = Column(Float, nullable=True)

    is_sarcastic = Column(Boolean, default=False)
    sarcasm_score = Column(Float, nullable=True)

    risk_score = Column(Float, nullable=True)             # from existing LSTM risk model
    explanation = Column(Text, nullable=True)             # short rationale, for explainability

    analyzed_at = Column(DateTime(timezone=True), server_default=func.now())

    message = relationship("Message", back_populates="analysis")


class ConversationRiskPattern(Base):
    """
    Rolling pattern-detection state per (conversation, user).
    Updated after each new message's analysis; drives gradual intervention
    instead of reacting to any single message.
    """
    __tablename__ = "conversation_risk_patterns"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    window_size = Column(Integer, default=10)             # last N messages considered
    negative_ratio = Column(Float, default=0.0)           # share of negative/high-risk msgs in window
    trend_slope = Column(Float, default=0.0)               # rising/falling negativity over time
    consecutive_negative_days = Column(Integer, default=0)

    last_intervention_at = Column(DateTime(timezone=True), nullable=True)
    intervention_count = Column(Integer, default=0)

    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    extra_data = Column(JSON, nullable=True)  # raw rolling scores, timestamps, etc.