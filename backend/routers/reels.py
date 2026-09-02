# backend/routers/reels.py
#
# ASSUMPTIONS — adjust to match your project:
#   - `get_db` dependency yields a SQLAlchemy Session (from database.py)
#   - `get_current_user` dependency returns the authenticated User (from your auth module)
#   - Existing models: Post, PostMedia, User, Like, Comment, Follow
#   - Post has is_reel (Boolean), audio_id (FK) columns added per models_reels.py notes
#   - Your AI pipeline exposes a function like `run_ai_pipeline(text) -> dict`
#     returning {"sentiment":..., "emotion":..., "risk_score":...}; reuse whatever
#     you already call in your post-creation flow.

import re
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from database import get_db
from models.user import User
from models.post import Post, PostMedia

from models_reels import Audio, ReelView, SavedReel, NotInterested, Report, ShareEvent
from schemas_reels import (
    ReelOut, FeedResponse, CommentCreate, CommentOut, ViewEventIn,
    ShareIn, NotInterestedIn, ReportIn, AudioOut,
)
from recommendation_service import rank_reels_for_user, build_user_signals
from models.reels import Audio, ReelView, SavedReel, NotInterested, Report, ShareEvent
from schemas.reels import ReelOut, FeedResponse
from services.reel_recommendation import rank_reels_for_user, build_user_signals
router = APIRouter(prefix="/api/reels", tags=["reels"])

HASHTAG_RE = re.compile(r"#(\w+)")
MENTION_RE = re.compile(r"@(\w+)")


def _extract_tags(caption: Optional[str]):
    if not caption:
        return [], []
    return HASHTAG_RE.findall(caption), MENTION_RE.findall(caption)


def _serialize(reel: Post, current_user: User, db: Session) -> ReelOut:
    hashtags, mentions = _extract_tags(reel.caption)
    is_liked = db.query(Like).filter_by(post_id=reel.id, user_id=current_user.id).first() is not None
    is_saved = db.query(SavedReel).filter_by(reel_id=reel.id, user_id=current_user.id).first() is not None
    is_following = db.query(Follow).filter_by(
        follower_id=current_user.id, followed_id=reel.user_id
    ).first() is not None

    return ReelOut(
        id=reel.id,
        caption=reel.caption,
        hashtags=hashtags,
        mentions=mentions,
        video_url=reel.video_url,
        thumbnail_url=getattr(reel, "thumbnail_url", None),
        duration_seconds=getattr(reel, "duration_seconds", None),
        created_at=reel.created_at,
        creator={
            "id": reel.creator.id,
            "username": reel.creator.username,
            "profile_picture_url": reel.creator.profile_picture_url,
            "is_following": is_following,
        },
        audio=AudioOut.from_orm(reel.audio) if getattr(reel, "audio", None) else None,
        like_count=reel.like_count if hasattr(reel, "like_count") else db.query(Like).filter_by(post_id=reel.id).count(),
        comment_count=reel.comment_count if hasattr(reel, "comment_count") else db.query(Comment).filter_by(post_id=reel.id).count(),
        share_count=db.query(ShareEvent).filter_by(reel_id=reel.id).count(),
        save_count=db.query(SavedReel).filter_by(reel_id=reel.id).count(),
        view_count=db.query(ReelView).filter_by(reel_id=reel.id).count(),
        is_liked=is_liked,
        is_saved=is_saved,
        sentiment=getattr(reel, "sentiment", None),
        emotion=getattr(reel, "emotion", None),
        risk_score=getattr(reel, "risk_score", None),
        rank_score=getattr(reel, "rank_score", None),
        rank_reason=getattr(reel, "rank_reason", None),
    )


@router.get("/feed", response_model=FeedResponse)
def get_reel_feed(
    limit: int = Query(10, le=30),
    exclude_ids: Optional[str] = Query(None, description="comma-separated reel IDs already seen this session"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    not_interested_ids = {
        r.reel_id for r in db.query(NotInterested).filter_by(user_id=current_user.id).all()
    }
    seen_ids = set()
    if exclude_ids:
        seen_ids = {int(x) for x in exclude_ids.split(",") if x.strip().isdigit()}

    excluded = not_interested_ids | seen_ids

    candidates = (
        db.query(Post)
        .filter(Post.is_reel == True)  # noqa: E712
        .filter(~Post.id.in_(excluded) if excluded else True)
        .order_by(desc(Post.created_at))
        .limit(200)  # pull a candidate pool, then re-rank
        .all()
    )

    following_ids = {f.followed_id for f in db.query(Follow).filter_by(follower_id=current_user.id).all()}
    user_signals = build_user_signals(db, current_user.id)

    ranked = rank_reels_for_user(candidates, following_ids, user_signals)[:limit]

    return FeedResponse(
        reels=[_serialize(r, current_user, db) for r in ranked],
        next_cursor=str(ranked[-1].id) if ranked else None,
    )


@router.get("/search", response_model=FeedResponse)
def search_reels(
    q: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    like_pattern = f"%{q}%"
    query = (
        db.query(Post)
        .join(User, Post.user_id == User.id)
        .outerjoin(Audio, Post.audio_id == Audio.id)
        .filter(Post.is_reel == True)  # noqa: E712
        .filter(
            (Post.caption.ilike(like_pattern))
            | (User.username.ilike(like_pattern))
            | (Audio.title.ilike(like_pattern))
        )
        .order_by(desc(Post.created_at))
        .limit(30)
        .all()
    )
    return FeedResponse(reels=[_serialize(r, current_user, db) for r in query], next_cursor=None)


@router.get("/audio/{audio_id}/reels", response_model=FeedResponse)
def reels_using_audio(audio_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    reels = db.query(Post).filter(Post.audio_id == audio_id, Post.is_reel == True).order_by(desc(Post.created_at)).limit(30).all()  # noqa: E712
    return FeedResponse(reels=[_serialize(r, current_user, db) for r in reels], next_cursor=None)


@router.post("/{reel_id}/like")
def toggle_like(reel_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    reel = db.query(Post).filter_by(id=reel_id, is_reel=True).first()
    if not reel:
        raise HTTPException(404, "Reel not found")

    existing = db.query(Like).filter_by(post_id=reel_id, user_id=current_user.id).first()
    if existing:
        db.delete(existing)
        db.commit()
        return {"liked": False}
    db.add(Like(post_id=reel_id, user_id=current_user.id))
    db.commit()
    return {"liked": True}


@router.post("/{reel_id}/comments", response_model=CommentOut)
def add_comment(reel_id: int, payload: CommentCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    reel = db.query(Post).filter_by(id=reel_id, is_reel=True).first()
    if not reel:
        raise HTTPException(404, "Reel not found")
    comment = Comment(
        post_id=reel_id,
        user_id=current_user.id,
        text=payload.text,
        parent_comment_id=payload.parent_comment_id,
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return CommentOut(
        id=comment.id,
        user={"id": current_user.id, "username": current_user.username, "profile_picture_url": current_user.profile_picture_url},
        text=comment.text,
        created_at=comment.created_at,
        reply_count=0,
    )


@router.get("/{reel_id}/comments", response_model=list[CommentOut])
def list_comments(reel_id: int, db: Session = Depends(get_db)):
    top_level = db.query(Comment).filter_by(post_id=reel_id, parent_comment_id=None).order_by(Comment.created_at.asc()).all()
    out = []
    for c in top_level:
        reply_count = db.query(Comment).filter_by(parent_comment_id=c.id).count()
        out.append(CommentOut(
            id=c.id,
            user={"id": c.user.id, "username": c.user.username, "profile_picture_url": c.user.profile_picture_url},
            text=c.text,
            created_at=c.created_at,
            reply_count=reply_count,
        ))
    return out


@router.post("/{reel_id}/save")
def toggle_save(reel_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    existing = db.query(SavedReel).filter_by(reel_id=reel_id, user_id=current_user.id).first()
    if existing:
        db.delete(existing)
        db.commit()
        return {"saved": False}
    db.add(SavedReel(reel_id=reel_id, user_id=current_user.id))
    db.commit()
    return {"saved": True}


@router.get("/saved", response_model=FeedResponse)
def list_saved(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    saved = db.query(SavedReel).filter_by(user_id=current_user.id).order_by(desc(SavedReel.created_at)).all()
    reels = [db.query(Post).get(s.reel_id) for s in saved]
    return FeedResponse(reels=[_serialize(r, current_user, db) for r in reels if r], next_cursor=None)


@router.post("/{reel_id}/share")
def share_reel(reel_id: int, payload: ShareIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db.add(ShareEvent(reel_id=reel_id, user_id=current_user.id, shared_to_user_id=payload.shared_to_user_id, method=payload.method))
    db.commit()
    return {"shared": True}


@router.post("/{reel_id}/view")
def log_view(reel_id: int, payload: ViewEventIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db.add(ReelView(
        reel_id=reel_id, user_id=current_user.id,
        watch_seconds=payload.watch_seconds, reel_duration=payload.reel_duration,
        completed=payload.completed,
    ))
    db.commit()
    return {"logged": True}


@router.post("/{reel_id}/not-interested")
def mark_not_interested(reel_id: int, payload: NotInterestedIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    exists = db.query(NotInterested).filter_by(reel_id=reel_id, user_id=current_user.id).first()
    if not exists:
        db.add(NotInterested(reel_id=reel_id, user_id=current_user.id, reason=payload.reason))
        db.commit()
    return {"hidden": True}


@router.post("/{reel_id}/report")
def report_reel(reel_id: int, payload: ReportIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db.add(Report(reporter_id=current_user.id, reel_id=reel_id, reason=payload.reason, details=payload.details))
    db.commit()
    return {"reported": True}


@router.post("/follow/{creator_id}")
def toggle_follow(creator_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if creator_id == current_user.id:
        raise HTTPException(400, "Cannot follow yourself")
    existing = db.query(Follow).filter_by(follower_id=current_user.id, followed_id=creator_id).first()
    if existing:
        db.delete(existing)
        db.commit()
        return {"following": False}
    db.add(Follow(follower_id=current_user.id, followed_id=creator_id))
    db.commit()
    return {"following": True}


# --- Register in main.py: ---
# from routers import reels
# app.include_router(reels.router)