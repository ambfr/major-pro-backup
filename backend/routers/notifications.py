from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import get_db
from models.models import User, Notification
from routers.auth import get_current_user
from schemas.notification import NotificationOut

from services.notification_service import (
    get_notifications,
    mark_as_read,
    delete_notification,
)

router = APIRouter()


@router.get("", response_model=list[NotificationOut])
async def all_notifications(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_notifications(
        db=db,
        user_id=current_user.id,
    )


@router.put("/{notification_id}/read", response_model=NotificationOut)
async def read_notification(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    notification = await db.get(Notification, notification_id)
    if not notification or notification.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Notification not found")

    return await mark_as_read(
        db=db,
        notification_id=notification_id,
    )


@router.delete("/{notification_id}")
async def remove_notification(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    notification = await db.get(Notification, notification_id)
    if not notification or notification.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Notification not found")

    return await delete_notification(
        db=db,
        notification_id=notification_id,
    )