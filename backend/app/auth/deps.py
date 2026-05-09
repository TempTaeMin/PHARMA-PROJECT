"""인증 의존성 — Depends(get_current_user) 로 모든 사용자별 라우터에 주입."""
import os
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


def _admin_emails() -> set[str]:
    raw = os.getenv("ADMIN_EMAILS", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """admin 라우터에 Depends(require_admin) 으로 주입.

    env `ADMIN_EMAILS` (쉼표 구분) 와 user.email 을 비교. env 가 비어있으면
    모든 호출이 403 — 안전한 default (실수로 풀린 인스턴스에서 admin API 가 열리는 걸 방지).
    """
    admins = _admin_emails()
    if not admins or (user.email or "").lower() not in admins:
        raise HTTPException(status_code=403, detail="관리자만 접근 가능합니다.")
    return user


async def get_my_team_id(db: AsyncSession, user_id: int) -> Optional[int]:
    """현재 사용자의 **활성** 팀 id. 멀티팀 정책에서 일정/메모/공지의 default 컨텍스트.

    우선순위:
      1) users.active_team_id (사이드바 dropdown 으로 사용자가 선택)
      2) (폴백) 첫 TeamMember.team_id — active 가 아직 안 박힌 마이그 직후 등
      3) 팀 미소속이면 None
    """
    user = (await db.execute(
        select(User).where(User.id == user_id)
    )).scalar_one_or_none()
    if not user:
        return None

    if user.active_team_id is not None:
        # active_team 에 실제로 멤버인지 검증 — 떠난 팀이 stale 로 남는 경우 방지
        is_member = (await db.execute(
            select(TeamMember).where(
                TeamMember.team_id == user.active_team_id,
                TeamMember.user_id == user_id,
            ).limit(1)
        )).scalar_one_or_none()
        if is_member:
            return user.active_team_id

    # 폴백 — 가장 오래된 멤버십을 active 로 간주
    tm = (await db.execute(
        select(TeamMember).where(TeamMember.user_id == user_id)
        .order_by(TeamMember.id.asc()).limit(1)
    )).scalar_one_or_none()
    return tm.team_id if tm else None


async def get_my_team_ids(db: AsyncSession, user_id: int) -> list[int]:
    """현재 사용자의 모든 소속 팀 id list (멀티팀 지원)."""
    rows = (await db.execute(
        select(TeamMember.team_id).where(TeamMember.user_id == user_id)
        .order_by(TeamMember.id.asc())
    )).scalars().all()
    return list(rows)


async def get_team_member_ids(db: AsyncSession, team_id: int) -> list[int]:
    """팀의 모든 멤버 user_id 목록."""
    rows = (await db.execute(
        select(TeamMember.user_id).where(TeamMember.team_id == team_id)
    )).scalars().all()
    return list(rows)
