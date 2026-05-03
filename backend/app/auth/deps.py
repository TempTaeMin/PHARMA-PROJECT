"""인증 의존성 — Depends(get_current_user) 로 모든 사용자별 라우터에 주입."""
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.connection import get_db
from app.models.database import TeamMember, User


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="로그인이 필요합니다.")
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        request.session.clear()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="사용자를 찾을 수 없습니다.")
    return user


async def get_my_team_id(db: AsyncSession, user_id: int) -> Optional[int]:
    """현재 사용자의 소속 팀 id. 팀 미소속이면 None."""
    tm = (await db.execute(
        select(TeamMember).where(TeamMember.user_id == user_id).limit(1)
    )).scalar_one_or_none()
    return tm.team_id if tm else None


async def get_team_member_ids(db: AsyncSession, team_id: int) -> list[int]:
    """팀의 모든 멤버 user_id 목록."""
    rows = (await db.execute(
        select(TeamMember.user_id).where(TeamMember.team_id == team_id)
    )).scalars().all()
    return list(rows)
