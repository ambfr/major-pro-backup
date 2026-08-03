"""
Quick peek at the most recent posts and their AI-pipeline fields.
Run from your project root (same place you run check_tables.py).

Usage:
    python peek_posts.py
"""
import asyncio
from sqlalchemy import select
from models.database import AsyncSessionLocal
from models.models import Post


async def main():
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Post).order_by(Post.id.desc()).limit(5)
        )
        posts = result.scalars().all()

        if not posts:
            print("No posts found — did the create-post request actually succeed?")
            return

        for p in posts:
            print("─" * 50)
            print(f"id:          {p.id}")
            print(f"content:     {p.content[:80]!r}")
            print(f"sentiment:   {p.sentiment} ({p.sentiment_score})")
            print(f"emotion:     {p.emotion} ({p.emotion_score})")
            print(f"sarcasm:     {p.sarcasm} ({p.sarcasm_score})")
            print(f"risk_score:  {p.risk_score}")
            print(f"feed_score:  {p.feed_score}")


if __name__ == "__main__":
    asyncio.run(main())