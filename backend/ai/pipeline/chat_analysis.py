"""
Chat module — AI analysis service.

Reuses the existing RoBERTa sentiment / distilroberta emotion models and
LSTM risk scorer from the reels+captions pipeline. Adds sarcasm detection,
rolling pattern detection, and gradual-intervention triggering for chat.

Wire the model loaders below to wherever your pipeline already loads them
(avoid re-loading per request — load once at app startup / module import).
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session

from .models import Message, MessageAnalysis, ConversationRiskPattern

# ---- Import your already-loaded pipeline models here ----
# from app.ml.sentiment import sentiment_model
# from app.ml.emotion import emotion_model
# from app.ml.sarcasm import sarcasm_model
# from app.ml.risk_lstm import risk_model


@dataclass
class AnalysisResult:
    sentiment_label: str
    sentiment_score: float
    emotion_label: str
    emotion_score: float
    is_sarcastic: bool
    sarcasm_score: float
    risk_score: float
    explanation: str


def run_text_analysis(text: str) -> AnalysisResult:
    """
    Single entry point run on a message's text content.
    Replace the stubbed calls with your actual model inference.
    """
    if not text or not text.strip():
        return AnalysisResult("neutral", 0.0, "neutral", 0.0, False, 0.0, 0.0, "No text content")

    # --- Sentiment (RoBERTa) ---
    sentiment_label, sentiment_score = _predict_sentiment(text)

    # --- Emotion (distilroberta) ---
    emotion_label, emotion_score = _predict_emotion(text)

    # --- Sarcasm ---
    is_sarcastic, sarcasm_score = _predict_sarcasm(text)

    # If sarcastic and sentiment looked positive, flip weight toward negative —
    # sarcasm commonly masks negative sentiment as surface-positive text.
    adjusted_negative_weight = sentiment_score if sentiment_label == "negative" else 0.0
    if is_sarcastic and sentiment_label == "positive":
        adjusted_negative_weight = sarcasm_score * 0.7

    risk_score = _combine_risk(sentiment_label, sentiment_score, emotion_label, emotion_score, is_sarcastic, sarcasm_score)

    explanation = _build_explanation(sentiment_label, emotion_label, is_sarcastic, risk_score)

    return AnalysisResult(
        sentiment_label=sentiment_label,
        sentiment_score=sentiment_score,
        emotion_label=emotion_label,
        emotion_score=emotion_score,
        is_sarcastic=is_sarcastic,
        sarcasm_score=sarcasm_score,
        risk_score=risk_score,
        explanation=explanation,
    )


# ---------- Model call stubs (replace with real inference) ----------

def _predict_sentiment(text: str) -> tuple[str, float]:
    # result = sentiment_model(text)[0]
    # return result["label"].lower(), float(result["score"])
    raise NotImplementedError("Wire up your RoBERTa sentiment model here")


def _predict_emotion(text: str) -> tuple[str, float]:
    # result = emotion_model(text)[0]
    # return result["label"].lower(), float(result["score"])
    raise NotImplementedError("Wire up your distilroberta emotion model here")


def _predict_sarcasm(text: str) -> tuple[bool, float]:
    # result = sarcasm_model(text)[0]
    # return result["label"] == "sarcastic", float(result["score"])
    raise NotImplementedError("Wire up your sarcasm model here")


def _combine_risk(sentiment_label, sentiment_score, emotion_label, emotion_score, is_sarcastic, sarcasm_score) -> float:
    """Simple weighted combination — swap for your LSTM risk model's output if it takes these as features."""
    negative_emotions = {"sadness", "anger", "fear"}
    score = 0.0
    if sentiment_label == "negative":
        score += 0.5 * sentiment_score
    if emotion_label in negative_emotions:
        score += 0.4 * emotion_score
    if is_sarcastic:
        score += 0.2 * sarcasm_score
    return min(score, 1.0)


def _build_explanation(sentiment_label, emotion_label, is_sarcastic, risk_score) -> str:
    parts = [f"sentiment: {sentiment_label}", f"emotion: {emotion_label}"]
    if is_sarcastic:
        parts.append("sarcasm detected")
    parts.append(f"risk: {risk_score:.2f}")
    return "; ".join(parts)


# ---------- Persist analysis ----------

def analyze_and_store_message(db: Session, message: Message) -> MessageAnalysis:
    result = run_text_analysis(message.content or "")

    analysis = MessageAnalysis(
        message_id=message.id,
        sentiment_label=result.sentiment_label,
        sentiment_score=result.sentiment_score,
        emotion_label=result.emotion_label,
        emotion_score=result.emotion_score,
        is_sarcastic=result.is_sarcastic,
        sarcasm_score=result.sarcasm_score,
        risk_score=result.risk_score,
        explanation=result.explanation,
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    update_risk_pattern(db, message.conversation_id, message.sender_id, result.risk_score)
    return analysis


# ---------- Temporal / pattern detection ----------

RISK_THRESHOLD = 0.6          # per-message risk considered "negative" for the rolling window
INTERVENTION_RATIO = 0.5      # fraction of window that must be negative to flag a pattern
INTERVENTION_COOLDOWN_HOURS = 24  # don't re-trigger more than once a day


def update_risk_pattern(db: Session, conversation_id: int, user_id: int, latest_risk_score: float) -> ConversationRiskPattern:
    pattern = (
        db.query(ConversationRiskPattern)
        .filter_by(conversation_id=conversation_id, user_id=user_id)
        .first()
    )
    if not pattern:
        pattern = ConversationRiskPattern(conversation_id=conversation_id, user_id=user_id)
        db.add(pattern)

    # Pull the recent window of this user's messages in this conversation, most recent first.
    recent_scores = (
        db.query(MessageAnalysis.risk_score)
        .join(Message, Message.id == MessageAnalysis.message_id)
        .filter(Message.conversation_id == conversation_id, Message.sender_id == user_id)
        .order_by(Message.created_at.desc())
        .limit(pattern.window_size)
        .all()
    )
    scores = [s[0] for s in recent_scores if s[0] is not None]
    if scores:
        pattern.negative_ratio = sum(1 for s in scores if s >= RISK_THRESHOLD) / len(scores)
        # crude trend: compare first half vs second half average (oldest→newest reversed)
        half = max(len(scores) // 2, 1)
        newer, older = scores[:half], scores[half:] or scores[:half]
        pattern.trend_slope = (sum(newer) / len(newer)) - (sum(older) / len(older))

    pattern.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(pattern)
    return pattern


def should_trigger_intervention(pattern: ConversationRiskPattern) -> bool:
    """Gradual intervention: only fire on a sustained pattern, with a cooldown — never on one message."""
    if pattern.negative_ratio < INTERVENTION_RATIO:
        return False
    if pattern.last_intervention_at:
        cooldown_ends = pattern.last_intervention_at + timedelta(hours=INTERVENTION_COOLDOWN_HOURS)
        if datetime.utcnow() < cooldown_ends:
            return False
    return True


def mark_intervention_triggered(db: Session, pattern: ConversationRiskPattern) -> None:
    pattern.last_intervention_at = datetime.utcnow()
    pattern.intervention_count += 1
    db.commit()