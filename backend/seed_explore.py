"""
seed_explore.py
Seeds a small, deliberately varied dataset to sanity-check GET /api/feed/explore.

Covers every axis the endpoint's WHERE clause touches:
  - public vs private accounts        (User.is_private)
  - posts vs reels                    (Post.is_reel)
  - followed vs not-followed          (Follow, relative to TEST_USER)
  - inside vs outside the 14-day cutoff (Post.created_at)

Run:
    python seed_explore.py

Then hit /api/feed/explore as TEST_USER and confirm:
  - alice_public, carol_public, dave_public_old(*excluded, old*) posts/reels appear
  - erin_private's posts NEVER appear
  - bob_public appears even though TEST_USER doesn't follow him
  - frank_public (followed by TEST_USER) still appears — following isn't excluded
  - only content from the last 14 days shows (dave_public_old should be missing)
"""

import asyncio
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from models.database import AsyncSessionLocal
from models.models import User, Post, Follow

TEST_USER_USERNAME = "test_user"


async def get_or_create_user(db: AsyncSession, username: str, is_private: bool, display_name: str = None):
    from sqlalchemy import select

    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user:
        return user

    user = User(
        username=username,
        display_name=display_name or username.replace("_", " ").title(),
        email=f"{username}@example.com",
        hashed_password="seed_dummy_hash",  # not used to log in; replace if you need real auth
        is_private=is_private,
        is_verified=False,
        bio=f"Seed account ({'private' if is_private else 'public'})",
    )
    db.add(user)
    await db.flush()  # get user.id without committing yet
    return user


async def make_post(
    db: AsyncSession,
    author: User,
    content: str,
    is_reel: bool = False,
    days_ago: int = 1,
    feed_score: float = 0.5,
    likes_count: int = 10,
):
    post = Post(
        user_id=author.id,
        content=content,
        image_url="https://picsum.photos/seed/mindgram/600/600" if not is_reel else "",
        video_url="https://example.com/dummy-reel.mp4" if is_reel else "",
        is_reel=is_reel,
        created_at=datetime.utcnow() - timedelta(days=days_ago),
        feed_score=feed_score,
        likes_count=likes_count,
        comments_count=2,
        views_count=50 if is_reel else 0,
    )
    db.add(post)
    return post


async def follow(db: AsyncSession, follower: User, following: User):
    from sqlalchemy import select

    result = await db.execute(
        select(Follow).where(
            Follow.follower_id == follower.id,
            Follow.following_id == following.id,
        )
    )
    if result.scalar_one_or_none():
        return
    db.add(Follow(follower_id=follower.id, following_id=following.id, status="accepted"))


async def seed():
    async with AsyncSessionLocal() as db:
        # ── Test viewer (the account you'll call /explore as) ──
        test_user = await get_or_create_user(db, TEST_USER_USERNAME, is_private=False)

        # ── Accounts covering each case ──
        alice_public = await get_or_create_user(db, "alice_public", is_private=False)
        bob_public_not_followed = await get_or_create_user(db, "bob_public_not_followed", is_private=False)
        carol_public_reels = await get_or_create_user(db, "carol_public_reels", is_private=False)
        dave_public_old = await get_or_create_user(db, "dave_public_old", is_private=False)
        erin_private = await get_or_create_user(db, "erin_private", is_private=True)
        frank_public_followed = await get_or_create_user(db, "frank_public_followed", is_private=False)

        await db.flush()

        # ── Follow graph ──
        # test_user follows frank (public) — should STILL show in explore (no follow-based exclusion)
        # test_user does NOT follow alice/bob/carol/dave/erin
        await follow(db, test_user, frank_public_followed)

        # ── Posts / reels ──
        # Should appear: recent, public
        await make_post(db, alice_public, "Alice's public post", is_reel=False, days_ago=1, feed_score=0.9, likes_count=120)
        await make_post(db, bob_public_not_followed, "Bob's public post (not followed by test_user)", is_reel=False, days_ago=2, feed_score=0.8, likes_count=80)
        await make_post(db, carol_public_reels, "Carol's public reel", is_reel=True, days_ago=1, feed_score=0.95, likes_count=300)
        await make_post(db, frank_public_followed, "Frank's public post (followed, should still appear)", is_reel=False, days_ago=3, feed_score=0.7, likes_count=40)

        # Should NOT appear: private account, even though recent + high engagement
        await make_post(db, erin_private, "Erin's private post — must NOT show in explore", is_reel=False, days_ago=1, feed_score=0.99, likes_count=999)

        # Should NOT appear: public but outside the 14-day cutoff
        await make_post(db, dave_public_old, "Dave's old public post — outside cutoff", is_reel=False, days_ago=20, feed_score=0.9, likes_count=200)

        await db.commit()

        print("Seed complete.")
        print(f"Test as user: {TEST_USER_USERNAME} (id={test_user.id})")
        print("Expected in /api/feed/explore: alice_public, bob_public_not_followed, carol_public_reels, frank_public_followed")
        print("Expected MISSING: erin_private (private account), dave_public_old (past 14-day cutoff)")


if __name__ == "__main__":
    asyncio.run(seed())