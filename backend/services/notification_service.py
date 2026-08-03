from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.models import Notification


async def create_notification(
    db: AsyncSession,
    user_id: int,
    from_user_id: int,
    notification_type: str,
    message: str,
    post_id: int | None = None,
):

    notification = Notification(
        user_id=user_id,
        from_user_id=from_user_id,
        type=notification_type,
        message=message,
        post_id=post_id,
    )

    db.add(notification)
    await db.commit()
    await db.refresh(notification)

    return notification


async def get_notifications(
    db: AsyncSession,
    user_id: int,
):

    result = await db.execute(
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
    )

    return result.scalars().all()


async def mark_as_read(
    db: AsyncSession,
    notification_id: int,
):

    notification = await db.get(Notification, notification_id)

    if notification:
        notification.is_read = True
        await db.commit()
        await db.refresh(notification)

    return notification


async def delete_notification(
    db: AsyncSession,
    notification_id: int,
):

    notification = await db.get(Notification, notification_id)

    if notification:
        await db.delete(notification)
        await db.commit()

    return {"success": True}