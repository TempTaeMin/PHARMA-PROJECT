"""베타 테스터 피드백 API.

- POST /api/feedback         — 누구나 (로그인 사용자) 제출
- GET  /api/feedback         — admin 전용, 리스트 (필터 + 페이지네이션)
- GET  /api/feedback/summary — admin 전용, 카테고리별 + 미처리 카운트
- PATCH /api/feedback/{id}   — admin 전용, handled 토글
- DELETE /api/feedback/{id}  — admin 전용, 스팸 삭제

admin 가드는 `app.auth.deps.require_admin` 디펜던시로 통일.
"""
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user, require_admin
from app.models.connection import get_db
from app.models.database import Feedback, User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/feedback", tags=["피드백"])

VALID_CATEGORIES = {"bug", "suggestion", "other"}


class FeedbackCreate(BaseModel):
    category: str = Field(..., description="bug | suggestion | other")
    message: str = Field(..., min_length=1, max_length=2000)
    page_path: Optional[str] = Field(None, max_length=255)


def _serialize(fb: Feedback, *, user: Optional[User] = None) -> dict:
    return {
        "id": fb.id,
        "user_id": fb.user_id,
        "user_name": user.name if user else None,
        "user_email": user.email if user else None,
        "category": fb.category,
        "message": fb.message,
        "page_path": fb.page_path,
        "user_agent": fb.user_agent,
        "handled": fb.handled,
        "created_at": fb.created_at.isoformat() if fb.created_at else None,
    }


@router.post("/", summary="피드백 제출")
async def create_feedback(
    data: FeedbackCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if data.category not in VALID_CATEGORIES:
        raise HTTPException(400, f"category 는 {sorted(VALID_CATEGORIES)} 중 하나여야 해요.")

    fb = Feedback(
        user_id=user.id,
        category=data.category,
        message=data.message.strip(),
        page_path=(data.page_path or "").strip() or None,
        user_agent=(request.headers.get("user-agent") or "")[:500] or None,
        handled=False,
    )
    db.add(fb)
    await db.commit()
    await db.refresh(fb)
    logger.info(f"[Feedback] 신규 #{fb.id} category={fb.category} user={user.email}")
    return _serialize(fb, user=user)


@router.get("/summary", summary="피드백 요약 (admin)")
async def feedback_summary(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    total = (await db.execute(select(func.count()).select_from(Feedback))).scalar_one()
    unread = (await db.execute(
        select(func.count()).select_from(Feedback).where(Feedback.handled == False)  # noqa: E712
    )).scalar_one()
    by_category_rows = (await db.execute(
        select(Feedback.category, func.count())
        .where(Feedback.handled == False)  # noqa: E712
        .group_by(Feedback.category)
    )).all()
    by_category = {c: 0 for c in VALID_CATEGORIES}
    for cat, cnt in by_category_rows:
        if cat in by_category:
            by_category[cat] = cnt
    return {"total": total, "unread_count": unread, "by_category": by_category}


@router.get("/", summary="피드백 리스트 (admin)")
async def list_feedback(
    handled: Optional[bool] = Query(None, description="None=전체, true=처리됨, false=미처리"),
    category: Optional[str] = Query(None, description="bug | suggestion | other"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    q = select(Feedback, User).outerjoin(User, Feedback.user_id == User.id)
    if handled is not None:
        q = q.where(Feedback.handled == handled)
    if category:
        if category not in VALID_CATEGORIES:
            raise HTTPException(400, f"category 는 {sorted(VALID_CATEGORIES)} 중 하나여야 해요.")
        q = q.where(Feedback.category == category)
    q = q.order_by(Feedback.created_at.desc()).limit(limit).offset(offset)

    rows = (await db.execute(q)).all()
    return [_serialize(fb, user=u) for fb, u in rows]


@router.patch("/{feedback_id}", summary="피드백 처리 토글 (admin)")
async def update_feedback(
    feedback_id: int,
    data: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    fb = (await db.execute(
        select(Feedback).where(Feedback.id == feedback_id)
    )).scalar_one_or_none()
    if not fb:
        raise HTTPException(404, "피드백을 찾을 수 없어요.")

    if "handled" in data:
        fb.handled = bool(data["handled"])
    await db.commit()
    await db.refresh(fb)

    fb_user = None
    if fb.user_id:
        fb_user = (await db.execute(
            select(User).where(User.id == fb.user_id)
        )).scalar_one_or_none()
    return _serialize(fb, user=fb_user)


@router.delete("/{feedback_id}", summary="피드백 삭제 (admin)")
async def delete_feedback(
    feedback_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    fb = (await db.execute(
        select(Feedback).where(Feedback.id == feedback_id)
    )).scalar_one_or_none()
    if not fb:
        raise HTTPException(404, "피드백을 찾을 수 없어요.")
    await db.delete(fb)
    await db.commit()
    return {"deleted": feedback_id}
