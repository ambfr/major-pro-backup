"""
Follow Router
POST    /api/follow/{user_id}
DELETE  /api/follow/{user_id}
POST    /api/follow/accept/{follower_id}
DELETE  /api/follow/reject/{follower_id}
GET     /api/follow/followers/{user_id}
GET     /api/follow/following/{user_id}
GET     /api/follow/status/{user_id}
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import get_db
from models.models import User
from routers.auth import get_current_user

from services.follow_service import (
    follow_user,
    unfollow_user,
    accept_follow_request,
    reject_follow_request,
    get_followers,
    get_following,
    get_follow_status,
)

from services.notification_service import create_notification

router = APIRouter()


# --------------------------------------------------
# Follow User
# --------------------------------------------------

@router.post("/{user_id}")
async def follow(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):

    result = await follow_user(
        db=db,
        follower_id=current_user.id,
        following_id=user_id,
    )

    if not result["success"]:
        raise HTTPException(
            status_code=400,
            detail=result["message"],
        )

    # Notification
    message = (
        f"{current_user.username} sent you a follow request"
        if result["status"] == "requested"
        else f"{current_user.username} started following you"
    )

    await create_notification(
        db=db,
        user_id=user_id,
        from_user_id=current_user.id,
        notification_type="follow",
        message=message,
    )

    return result


# --------------------------------------------------
# Unfollow User
# --------------------------------------------------

@router.delete("/{user_id}")
async def unfollow(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):

    result = await unfollow_user(
        db=db,
        follower_id=current_user.id,
        following_id=user_id,
    )

    if not result["success"]:
        raise HTTPException(
            status_code=400,
            detail=result["message"],
        )

    return result


# --------------------------------------------------
# Accept Follow Request
# --------------------------------------------------

@router.post("/accept/{follower_id}")
async def accept_request(
    follower_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):

    result = await accept_follow_request(
        db=db,
        follower_id=follower_id,
        following_id=current_user.id,
    )

    if not result["success"]:
        raise HTTPException(
            status_code=400,
            detail=result["message"],
        )

    await create_notification(
        db=db,
        user_id=follower_id,
        from_user_id=current_user.id,
        notification_type="follow_accept",
        message=f"{current_user.username} accepted your follow request",
    )

    return result


# --------------------------------------------------
# Reject Follow Request
# --------------------------------------------------

@router.delete("/reject/{follower_id}")
async def reject_request(
    follower_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):

    result = await reject_follow_request(
        db=db,
        follower_id=follower_id,
        following_id=current_user.id,
    )

    if not result["success"]:
        raise HTTPException(
            status_code=400,
            detail=result["message"],
        )

    await create_notification(
        db=db,
        user_id=follower_id,
        from_user_id=current_user.id,
        notification_type="follow_reject",
        message=f"{current_user.username} rejected your follow request",
    )

    return result


# --------------------------------------------------
# Get Followers
# --------------------------------------------------

@router.get("/followers/{user_id}")
async def followers(
    user_id: int,
    db: AsyncSession = Depends(get_db),
):

    return await get_followers(
        db=db,
        user_id=user_id,
    )


# --------------------------------------------------
# Get Following
# --------------------------------------------------

@router.get("/following/{user_id}")
async def following(
    user_id: int,
    db: AsyncSession = Depends(get_db),
):

    return await get_following(
        db=db,
        user_id=user_id,
    )


# --------------------------------------------------
# Follow Status
# --------------------------------------------------

@router.get("/status/{user_id}")
async def follow_status(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):

    return await get_follow_status(
        db=db,
        follower_id=current_user.id,
        following_id=user_id,
    )