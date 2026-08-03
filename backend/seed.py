"""
Seed script — populates the database with demo users and posts
so you can see the app working immediately.

Run: python seed.py
"""
import asyncio
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from models.database import create_tables, AsyncSessionLocal
from models.models import User, Post, PostMedia, EmotionLog, AgentDecision
from services.topic_utils import extract_topics
from datetime import datetime, timedelta
import random

DEMO_USERS = [
    {"id": 1, "username": "alex_mind",      "email": "alex@mindgram.demo",   "display_name": "Alex",    "avatar_url": "https://api.dicebear.com/9.x/avataaars/svg?seed=alex"},
    {"id": 2, "username": "sunrise_maya",   "email": "maya@mindgram.demo",   "display_name": "Maya K.", "avatar_url": "https://api.dicebear.com/9.x/avataaars/svg?seed=maya"},
    {"id": 3, "username": "ravi_thoughts",  "email": "ravi@mindgram.demo",   "display_name": "Ravi S.", "avatar_url": "https://api.dicebear.com/9.x/avataaars/svg?seed=ravi"},
    {"id": 4, "username": "priya_runs",     "email": "priya@mindgram.demo",  "display_name": "Priya R.","avatar_url": "https://api.dicebear.com/9.x/avataaars/svg?seed=priya"},
    {"id": 5, "username": "dev_arjun",      "email": "arjun@mindgram.demo",  "display_name": "Arjun M.","avatar_url": "https://api.dicebear.com/9.x/avataaars/svg?seed=arjun"},
]

DEMO_POSTS = [
    {"user_id": 2, "content": "Woke up early to watch the sunrise 🌅 feeling grateful for these small moments #gratitude #sunrise #wellness",
     "sentiment": "positive", "sentiment_score": 0.78, "emotion": "joy", "emotion_score": 0.82,
     "sarcasm": False, "risk_score": 0.05, "feed_score": 0.88, "likes_count": 143, "comments_count": 12,
     "image_url": "https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=600&q=80"},
    {"user_id": 3, "content": "Everything feels so heavy lately. Can't seem to shake this fog. #mentalhealth #sadness",
     "sentiment": "negative", "sentiment_score": -0.71, "emotion": "sadness", "emotion_score": 0.76,
     "sarcasm": False, "risk_score": 0.72, "feed_score": 0.22, "likes_count": 67, "comments_count": 34,
     "image_url": ""},
    {"user_id": 4, "content": "Just finished a 10km run! 🏃 The endorphins are real. #fitness #running #wellness",
     "sentiment": "positive", "sentiment_score": 0.91, "emotion": "joy", "emotion_score": 0.88,
     "sarcasm": False, "risk_score": 0.02, "feed_score": 0.94, "likes_count": 221, "comments_count": 18,
     "image_url": "https://images.unsplash.com/photo-1506929562872-bb421503ef21?w=600&q=80"},
    {"user_id": 5, "content": "Another rejection email. Yeah, totally fine, I love this! #jobsearch #sarcasm",
     "sentiment": "negative", "sentiment_score": -0.43, "emotion": "anger", "emotion_score": 0.61,
     "sarcasm": True,  "risk_score": 0.48, "feed_score": 0.31, "likes_count": 89, "comments_count": 27,
     "image_url": ""},
]

EMOTIONS = ['joy', 'neutral', 'sadness', 'neutral', 'joy', 'fear', 'anger', 'neutral', 'joy', 'neutral']

async def seed():
    await create_tables()
    async with AsyncSessionLocal() as db:
        # Users
        for u in DEMO_USERS:
            existing = await db.get(User, u["id"])
            if not existing:
                db.add(User(**u))

        await db.flush()

        # Posts
        for i, p in enumerate(DEMO_POSTS):
            post = Post(
                user_id=p["user_id"],
                content=p["content"],
                image_url=p.get("image_url", ""),
                sentiment=p["sentiment"],
                sentiment_score=p["sentiment_score"],
                emotion=p["emotion"],
                emotion_score=p["emotion_score"],
                sarcasm=p["sarcasm"],
                sarcasm_score=0.8 if p["sarcasm"] else 0.04,
                risk_score=p["risk_score"],
                feed_score=p["feed_score"],
                likes_count=p["likes_count"],
                comments_count=p["comments_count"],
                topics=extract_topics(p["content"], p["emotion"]),
                created_at=datetime.utcnow() - timedelta(hours=i * 4),
            )
            if p.get("image_url"):
                post.media = [
                    PostMedia(
                        media_type="image",
                        url=p["image_url"],
                        position=0,
                    )
                ]
            db.add(post)

        # Emotion logs for user 1 (for dashboard charts)
        for i, emotion in enumerate(EMOTIONS):
            risk_map = {'joy': 0.05, 'neutral': 0.12, 'sadness': 0.65, 'fear': 0.58, 'anger': 0.52}
            sent_map = {'joy': 0.75, 'neutral': 0.02, 'sadness': -0.68, 'fear': -0.55, 'anger': -0.61}
            risk = risk_map.get(emotion, 0.1) + random.uniform(-0.05, 0.05)
            sent = sent_map.get(emotion, 0.0) + random.uniform(-0.05, 0.05)
            db.add(EmotionLog(
                user_id=1,
                timestamp=datetime.utcnow() - timedelta(hours=(len(EMOTIONS) - i) * 6),
                sentiment_score=round(max(-1, min(1, sent)), 3),
                emotion=emotion,
                emotion_score=round(random.uniform(0.5, 0.9), 3),
                risk_score=round(max(0, min(1, risk)), 3),
                source="post",
                agent_action="gentle_prompt" if risk > 0.5 else "monitor",
            ))

        # Agent decision for user 1
        db.add(AgentDecision(
            user_id=1, risk_level="moderate", decision="gentle_prompt",
            intervention="Gently prompt user with a wellness check-in.",
            rag_suggestion="Take a moment today to write 3 things you're grateful for.",
        ))

        await db.commit()
        print("✅ Seed data inserted successfully.")

if __name__ == "__main__":
    asyncio.run(seed())
