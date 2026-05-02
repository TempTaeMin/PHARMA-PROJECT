"""Google OAuth 라우트 + /auth/me + /auth/logout."""
import logging
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.auth.oauth import oauth
from app.models.connection import get_db
from app.models.database import Team, TeamMember, User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["인증"])


def _frontend_url() -> str:
    return os.getenv("FRONTEND_URL", "http://localhost:5173")


def _serialize_user(user: User, team_id: Optional[int] = None) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "picture": user.picture,
        "team_id": team_id,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


async def _ensure_team(db: AsyncSession, user: User) -> int:
    """가입자에게 1인 팀이 없으면 생성. 팀 id 반환."""
    existing = (await db.execute(
        select(TeamMember).where(TeamMember.user_id == user.id).limit(1)
    )).scalar_one_or_none()
    if existing:
        return existing.team_id
    team_name = (user.name or user.email.split("@")[0]) + "의 팀"
    team = Team(name=team_name, owner_user_id=user.id)
    db.add(team)
    await db.flush()  # team.id 얻기
    db.add(TeamMember(team_id=team.id, user_id=user.id, role="owner"))
    await db.commit()
    return team.id


@router.get("/google/login", summary="Google 로그인 시작")
async def google_login(request: Request):
    redirect_uri = os.getenv(
        "GOOGLE_REDIRECT_URI",
        str(request.url_for("google_callback")),
    )
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/google/callback", name="google_callback", summary="Google OAuth 콜백")
async def google_callback(request: Request, db: AsyncSession = Depends(get_db)):
    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception as e:
        logger.exception("OAuth callback 실패")
        raise HTTPException(status_code=400, detail=f"OAuth 실패: {e}") from e

    userinfo = token.get("userinfo") or {}
    google_sub = userinfo.get("sub")
    email = userinfo.get("email")
    if not google_sub or not email:
        raise HTTPException(status_code=400, detail="Google 사용자 정보를 가져올 수 없습니다.")

    name = userinfo.get("name") or email.split("@")[0]
    picture = userinfo.get("picture")

    user = (await db.execute(
        select(User).where(User.google_sub == google_sub)
    )).scalar_one_or_none()
    if user:
        user.email = email
        user.name = name
        user.picture = picture
        user.last_login_at = datetime.utcnow()
    else:
        user = User(
            google_sub=google_sub,
            email=email,
            name=name,
            picture=picture,
            last_login_at=datetime.utcnow(),
        )
        db.add(user)
    await db.commit()
    await db.refresh(user)

    await _ensure_team(db, user)

    request.session["user_id"] = user.id
    return RedirectResponse(url=_frontend_url())


@router.get("/me", summary="현재 로그인 사용자")
async def me(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tm = (await db.execute(
        select(TeamMember).where(TeamMember.user_id == user.id).limit(1)
    )).scalar_one_or_none()
    return _serialize_user(user, team_id=tm.team_id if tm else None)


@router.post("/logout", summary="로그아웃")
async def logout(request: Request):
    request.session.clear()
    return {"ok": True}
