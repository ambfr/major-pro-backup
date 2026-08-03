"""
Stories Router
POST   /api/stories                    → create story with image/video upload
GET    /api/stories/{id}               → get single story
DELETE /api/stories/{id}               → delete story
POST   /api/stories/{id}/view          → record that current user viewed a story
GET    /api/stories/{id}/viewers       → 'who viewed my story' (author only)
GET    /api/stories/history/me         → 'stories I have viewed' (personal history)
GET    /api/stories/user/{user_id}     → active (non-expired) stories for a user
"""

from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional

from models.database import get_db
from models.models import Story, StoryView, User, EmotionLog, AgentDecision
from schemas.schemas import StoryOut, StoryViewerOut, ViewedStoryOut
from routers.auth import get_current_user, get_optional_user
from routers.posts import get_user_risk_history, get_emotion_history
from ai.pipeline.analyzer import analyze_text
from ai.agents.orchestrator import run_agents, EmotionSnapshot
from services.cloudinary_service import upload_image, upload_video, delete_asset

router = APIRouter()

STORY_LIFETIME_HOURS = 24


@router.post("", response_model=StoryOut, status_code=201)
async def create_story(
    text: str = Form(default=""),
    image: Optional[UploadFile] = File(default=None),
    video: Optional[UploadFile] = File(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if image and image.filename and video and video.filename:
        raise HTTPException(status_code=400, detail="Use either a photo or a video, not both")

    if not text and not (image and image.filename) and not (video and video.filename):
        raise HTTPException(status_code=400, detail="Story must have text, image, or video")

    image_url = ""
    video_url = ""
    image_public_id = ""
    video_public_id = ""

    if image and image.filename:
        result = await upload_image(image, folder="mindgram/stories")
        image_url = result["url"]
        image_public_id = result["public_id"]

    if video and video.filename:
        result = await upload_video(video, folder="mindgram/stories")
        video_url = result["url"]
        video_public_id = result["public_id"]

    # Run the same AI pipeline as posts, so at-risk story content is caught
    # too — text overlays are the only user-authored language on a story,
    # so that's what gets analyzed (image-only/video-only stories fall back
    # to a neutral placeholder, same convention as posts).
    text_to_analyze = text.strip() or (
        "shared a photo" if image_url else "shared a video" if video_url else "story"
    )
    risk_history = await get_user_risk_history(current_user.id, db)
    pipeline = analyze_text(text_to_analyze, risk_history)

    story = Story(
        user_id=current_user.id,
        image_url=image_url,
        video_url=video_url,
        image_public_id=image_public_id,
        video_public_id=video_public_id,
        text=text,
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(hours=STORY_LIFETIME_HOURS),
        sentiment=pipeline.sentiment,
        risk_score=pipeline.risk_score,
    )
    db.add(story)
    await db.flush()

    log = EmotionLog(
        user_id=current_user.id,
        sentiment_score=pipeline.sentiment_score,
        emotion=pipeline.emotion,
        emotion_score=pipeline.emotion_score,
        risk_score=pipeline.risk_score,
        source="story",
    )
    db.add(log)

    history = await get_emotion_history(current_user.id, db)
    current_snap = EmotionSnapshot(
        sentiment_score=pipeline.sentiment_score,
        emotion=pipeline.emotion,
        emotion_score=pipeline.emotion_score,
        risk_score=pipeline.risk_score,
        source="story",
    )
    agent_report = run_agents(current_snap, history)

    db.add(AgentDecision(
        user_id=current_user.id,
        risk_level=agent_report.risk_level,
        decision=agent_report.decision,
        intervention=agent_report.intervention,
        rag_suggestion=agent_report.rag_suggestion,
        metadata_json=agent_report.metadata,
    ))
    log.agent_action = agent_report.decision

    await db.commit()
    await db.refresh(story)
    story.author = current_user
    return story


@router.get("/{story_id}", response_model=StoryOut)
async def get_story(story_id: int, db: AsyncSession = Depends(get_db)):
    story = await db.get(Story, story_id)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    return story


@router.get("/user/{user_id}", response_model=list[StoryOut])
async def get_user_stories(
    user_id: int,
    current_user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """Active (non-expired) stories for a user, oldest first (chronological
    playback order, matching how Instagram plays a user's story ring).
    Attaches author + viewed_by_me (relative to the requesting user) so
    the frontend story ring can render seen/unseen state without a
    separate round trip."""
    result = await db.execute(
        select(Story)
        .where(Story.user_id == user_id, Story.expires_at > datetime.utcnow())
        .order_by(Story.created_at.asc())
    )
    stories = result.scalars().all()
    if not stories:
        return []

    author = await db.get(User, user_id)

    viewed_ids: set[int] = set()
    if current_user:
        story_ids = [s.id for s in stories]
        view_result = await db.execute(
            select(StoryView.story_id).where(
                StoryView.viewer_id == current_user.id,
                StoryView.story_id.in_(story_ids),
            )
        )
        viewed_ids = {row[0] for row in view_result.fetchall()}
        # The author always counts as having "seen" their own story
        if current_user.id == user_id:
            viewed_ids = {s.id for s in stories}

    for s in stories:
        s.author = author
        s.viewed_by_me = s.id in viewed_ids

    return stories


@router.delete("/{story_id}")
async def delete_story(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    story = await db.get(Story, story_id)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    if story.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your story")

    if story.image_public_id:
        delete_asset(story.image_public_id, resource_type="image")
    if story.video_public_id:
        delete_asset(story.video_public_id, resource_type="video")

    await db.delete(story)
    await db.commit()
    return {"status": "deleted"}


@router.post("/{story_id}/view")
async def record_story_view(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Records that current_user viewed this story. Upserts on (story_id,
    viewer_id) — rewatching updates viewed_at rather than creating a
    duplicate row, so views_count reflects unique viewers, matching
    Instagram's convention.
    """
    story = await db.get(Story, story_id)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    if current_user.id == story.user_id:
        return {"status": "ok", "counted": False, "reason": "author_self_view"}

    result = await db.execute(
        select(StoryView).where(
            StoryView.story_id == story_id,
            StoryView.viewer_id == current_user.id,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.viewed_at = datetime.utcnow()
        await db.commit()
        return {"status": "ok", "counted": False, "reason": "already_viewed"}

    db.add(StoryView(story_id=story_id, viewer_id=current_user.id))
    story.views += 1
    await db.commit()
    return {"status": "ok", "counted": True}


@router.get("/{story_id}/viewers", response_model=list[StoryViewerOut])
async def get_story_viewers(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """'Who viewed my story' — author-only, most recent view first."""
    story = await db.get(Story, story_id)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    if story.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the story author can view this")

    result = await db.execute(
        select(StoryView, User)
        .join(User, User.id == StoryView.viewer_id)
        .where(StoryView.story_id == story_id)
        .order_by(StoryView.viewed_at.desc())
    )
    rows = result.all()

    return [
        StoryViewerOut(
            viewer_id=user.id,
            username=user.username,
            display_name=user.display_name,
            avatar_url=user.avatar_url,
            viewed_at=view.viewed_at,
        )
        for view, user in rows
    ]


@router.get("/history/me", response_model=list[ViewedStoryOut])
async def get_my_viewing_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    'Stories I have viewed' — personal history for the authenticated user,
    most recent first. Includes stories that have since expired, since
    this is a history log, not an active-stories list.
    """
    result = await db.execute(
        select(StoryView, Story)
        .join(Story, Story.id == StoryView.story_id)
        .where(StoryView.viewer_id == current_user.id)
        .order_by(StoryView.viewed_at.desc())
    )
    rows = result.all()

    author_cache: dict[int, User] = {}
    history = []
    for view, story in rows:
        if story.user_id not in author_cache:
            author_cache[story.user_id] = await db.get(User, story.user_id)
        author = author_cache[story.user_id]
        history.append(ViewedStoryOut(
            story_id=story.id,
            author_id=story.user_id,
            author_username=author.username if author else "unknown",
            viewed_at=view.viewed_at,
        ))
    return history