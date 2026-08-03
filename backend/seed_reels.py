import asyncio

from models.database import AsyncSessionLocal
from models.models import Post


async def add_reels():

    async with AsyncSessionLocal() as db:

        reels = [

            Post(
                user_id=1,
                content="Morning coffee aesthetic ☕✨",
                video_url="https://www.w3schools.com/html/mov_bbb.mp4",
                is_reel=True
            ),

            Post(
                user_id=1,
                content="Travel diaries 🌍✈️",
                video_url="https://media.w3.org/2010/05/sintel/trailer.mp4",
                is_reel=True
            ),

            Post(
                user_id=1,
                content="Fashion inspiration 👗✨",
                video_url="https://www.w3schools.com/html/movie.mp4",
                is_reel=True
            ),

            Post(
                user_id=1,
                content="Weekend vibes 🌴",
                video_url="https://media.w3.org/2010/05/bunny/trailer.mp4",
                is_reel=True
            ),

            Post(
                user_id=1,
                content="City nights 🌃",
                video_url="https://www.w3schools.com/html/mov_bbb.mp4",
                is_reel=True
            ),

            Post(
                user_id=1,
                content="Nature escape 🌿",
                video_url="https://media.w3.org/2010/05/sintel/trailer.mp4",
                is_reel=True
            ),

            Post(
                user_id=1,
                content="Dance practice 💃🔥",
                video_url="https://www.w3schools.com/html/movie.mp4",
                is_reel=True
            ),

            Post(
                user_id=1,
                content="Lifestyle vlog 🎥",
                video_url="https://media.w3.org/2010/05/bunny/trailer.mp4",
                is_reel=True
            ),

            Post(
                user_id=1,
                content="Food exploration 🍜",
                video_url="https://www.w3schools.com/html/mov_bbb.mp4",
                is_reel=True
            ),

            Post(
                user_id=1,
                content="Creative moments ✨",
                video_url="https://media.w3.org/2010/05/sintel/trailer.mp4",
                is_reel=True
            )

        ]

        db.add_all(reels)

        await db.commit()

        print("10 demo reels added successfully!")


asyncio.run(add_reels())