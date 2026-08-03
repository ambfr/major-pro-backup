"""
feed_ranker.py
MindGram feed ranking: interest + relationship + recency.

Matches models.py exactly:
    User, Follow(follower_id, following_id), Post(emotion, sentiment_score, created_at, ...),
    Like(user_id, post_id), Comment(user_id, post_id), UserInterest(user_id, emotion, score)
"""

import math
from datetime import datetime, timedelta
from typing import List, Dict
from sqlalchemy.orm import Session
from sqlalchemy import func

from models import User, Post, Follow, Like, Comment, UserInterest

# ---- tunable weights ----
W_INTEREST = 0.40
W_RELATIONSHIP = 0.35
W_RECENCY = 0.25
RECENCY_TAU_HOURS = 24.0  # decay constant; smaller = faster drop-off
INTEREST_DECAY = 0.98     # applied to old weights every time a new interaction comes in


# ---------------------------------------------------------------------------
# 1. INTEREST SCORE — built from the emotion of posts a user engages with
# ---------------------------------------------------------------------------
def get_user_interest_weights(db: Session, user_id: int) -> Dict[str, float]:
    """Returns {emotion: score} for a user, from the UserInterest table."""
    rows = db.query(UserInterest).filter(UserInterest.user_id == user_id).all()
    return {r.emotion: r.score for r in rows}


def update_user_interest(db: Session, user_id: int, emotion: str, boost: float = 1.0):
    """
    Call this whenever a user likes / comments on / saves a post.
    Decays existing weights slightly, then boosts the emotion of the post
    just interacted with, so recent interests dominate over stale ones.
    """
    if not emotion:
        return

    existing_rows = db.query(UserInterest).filter(UserInterest.user_id == user_id).all()
    for row in existing_rows:
        row.score *= INTEREST_DECAY

    target = next((r for r in existing_rows if r.emotion == emotion), None)
    if target:
        target.score += boost
    else:
        db.add(UserInterest(user_id=user_id, emotion=emotion, score=boost))

    db.commit()


def interest_score(user_weights: Dict[str, float], post_emotion: str) -> float:
    if not user_weights or not post_emotion:
        return 0.0
    raw = user_weights.get(post_emotion, 0.0)
    max_weight = max(user_weights.values())
    return min(raw / max_weight, 1.0) if max_weight > 0 else 0.0


# ---------------------------------------------------------------------------
# 2. RELATIONSHIP SCORE
# ---------------------------------------------------------------------------
def relationship_score(db: Session, viewer_id: int, poster_id: int) -> float:
    if viewer_id == poster_id:
        return 1.0

    follows_them = db.query(Follow).filter_by(
        follower_id=viewer_id, following_id=poster_id
    ).first() is not None
    followed_by_them = db.query(Follow).filter_by(
        follower_id=poster_id, following_id=viewer_id
    ).first() is not None

    if follows_them and followed_by_them:
        base = 1.0
    elif follows_them:
        base = 0.7
    else:
        interacted = (
            db.query(Like).join(Post, Like.post_id == Post.id)
            .filter(Like.user_id == viewer_id, Post.user_id == poster_id)
            .first()
            or db.query(Comment).join(Post, Comment.post_id == Post.id)
            .filter(Comment.user_id == viewer_id, Post.user_id == poster_id)
            .first()
        )
        base = 0.3 if interacted else 0.0

    # bonus for recent interaction frequency (likes, last 30 days)
    since = datetime.utcnow() - timedelta(days=30)
    recent_likes = (
        db.query(func.count(Like.id))
        .join(Post, Like.post_id == Post.id)
        .filter(Like.user_id == viewer_id, Post.user_id == poster_id, Like.created_at >= since)
        .scalar() or 0
    )
    bonus = min(recent_likes * 0.05, 0.3)

    return min(base + bonus, 1.0)


# ---------------------------------------------------------------------------
# 3. RECENCY SCORE
# ---------------------------------------------------------------------------
def recency_score(created_at: datetime) -> float:
    hours = max((datetime.utcnow() - created_at).total_seconds() / 3600.0, 0.0)
    return math.exp(-hours / RECENCY_TAU_HOURS)


# ---------------------------------------------------------------------------
# MAIN RANKER
# ---------------------------------------------------------------------------
def rank_feed(db: Session, viewer_id: int, candidate_posts: List[Post]) -> List[dict]:
    """
    candidate_posts: Post ORM objects (e.g. posts from followed users + discovery pool).
    Returns list of dicts sorted by final_score desc, each wrapping the original post.
    """
    user_weights = get_user_interest_weights(db, viewer_id)

    scored = []
    for post in candidate_posts:
        i_score = interest_score(user_weights, post.emotion)
        r_score = relationship_score(db, viewer_id, post.user_id)
        t_score = recency_score(post.created_at)

        final = (W_INTEREST * i_score) + (W_RELATIONSHIP * r_score) + (W_RECENCY * t_score)

        scored.append({
            "post": post,
            "final_score": round(final, 4),
            "interest_score": round(i_score, 4),
            "relationship_score": round(r_score, 4),
            "recency_score": round(t_score, 4),
        })

    scored.sort(key=lambda x: x["final_score"], reverse=True)
    return scored