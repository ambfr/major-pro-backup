"""
Background job: deletes stories whose expires_at has passed.
Removes Cloudinary assets first, then the DB row.
StoryView rows are cascade-deleted via the relationship in models.py.
"""
import logging
from datetime import datetime

from sqlalchemy import select
from models.database import AsyncSessionLocal
from models.models import Story
from services.cloudinary_service import delete_asset

logger = logging.getLogger(__name__)


async def purge_expired_stories():
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Story).where(Story.expires_at <= datetime.utcnow())
        )
        expired = result.scalars().all()

        if not expired:
            return

        for story in expired:
            try:
                if story.image_public_id:
                    delete_asset(story.image_public_id, resource_type="image")
                if story.video_public_id:
                    delete_asset(story.video_public_id, resource_type="video")
            except Exception as e:
                logger.warning(f"Cloudinary cleanup failed for story {story.id}: {e}")

            await db.delete(story)

        await db.commit()
        logger.info(f"Purged {len(expired)} expired stories")