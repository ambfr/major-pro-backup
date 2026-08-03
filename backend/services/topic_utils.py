"""
Topic extraction and trending helpers for feed ranking.
"""

import re
from collections import defaultdict
from datetime import datetime

_HASHTAG_RE = re.compile(r"#(\w{2,40})", re.UNICODE)


def extract_topics(content: str, emotion: str = "", location: str = "") -> list[str]:
    """
    Pull hashtags from caption plus soft topic tags from emotion/location.
    Returns a deduplicated list (max 10).
    """
    topics: list[str] = []
    seen: set[str] = set()

    for tag in _HASHTAG_RE.findall(content or ""):
        key = tag.lower()
        if key not in seen:
            seen.add(key)
            topics.append(key)

    if emotion and emotion != "neutral":
        key = f"emotion:{emotion.lower()}"
        if key not in seen:
            seen.add(key)
            topics.append(key)

    if location and location.strip():
        key = f"loc:{location.strip().lower().replace(' ', '_')[:40]}"
        if key not in seen:
            seen.add(key)
            topics.append(key)

    return topics[:10]


def topic_overlap_score(post_topics: list[str], reference: dict[str, float]) -> float:
    """Max normalized score across overlapping topics."""
    if not post_topics or not reference:
        return 0.0
    matches = [reference[t] for t in post_topics if t in reference]
    return max(matches) if matches else 0.0


def aggregate_trending_scores(
    rows: list[tuple[list[str], int, int, int, datetime]],
    now: datetime | None = None,
) -> dict[str, float]:
    """
    Compute platform-wide trending topic scores from recent posts.
    Each row: (topics, likes, comments, shares, created_at).
  """
    now = now or datetime.utcnow()
    topic_velocity: dict[str, float] = defaultdict(float)

    for topics, likes, comments, shares, created_at in rows:
        if not topics:
            continue
        age_hours = max((now - created_at).total_seconds() / 3600.0, 0.5)
        engagement = likes + comments * 2 + shares * 3
        velocity = engagement / age_hours
        for topic in topics:
            topic_velocity[topic] += velocity

    if not topic_velocity:
        return {}

    peak = max(topic_velocity.values())
    return {topic: round(score / peak, 4) for topic, score in topic_velocity.items()}
