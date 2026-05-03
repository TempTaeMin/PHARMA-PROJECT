"""팀 관리 API — 팀 생성/멤버 초대(승인 흐름)/제거/탈퇴/이름 변경.

1.0 정책:
- 신규 가입자는 팀 미소속 (혼자 사용 가능)
- 팀 생성은 명시 액션. 생성자가 owner
- 한 사람당 한 팀
- 초대는 invitation row 만 생성 → 받는 사용자가 수락해야 멤버 등록
"""
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user, get_my_team_id
from app.models.connection import get_db
from app.models.database import (
    Team, TeamInvitation, TeamMember, User, VisitLog, visit_log_recipients,
)
from app.notifications.manager import notification_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/teams", tags=["팀"])


class TeamCreate(BaseModel):
    name: str


class TeamRename(BaseModel):
    name: str


class TeamInvite(BaseModel):
    email: str


def _serialize_member(user: User, role: str) -> dict:
    return {
        "user_id": user.id,
        "email": user.email,
        "name": user.name,
        "picture": user.picture,
        "role": role,
    }


async def _isolate_visits_for_user(db: AsyncSession, user_id: int) -> None:
    """팀 탈퇴/제거 시 호출. 본인이 owner 인 'team' 일정은 'private' 으로 강등하고,
    본인이 다른 사람 일정의 recipient 으로 들어가 있던 모든 행 제거."""
    await db.execute(
        VisitLog.__table__.update()
        .where(VisitLog.user_id == user_id, VisitLog.visibility == "team")
        .values(visibility="private")
    )
    await db.execute(
        visit_log_recipients.delete().where(
            visit_log_recipients.c.recipient_user_id == user_id
        )
    )


async def _load_my_team(db: AsyncSession, user_id: int) -> Optional[tuple[Team, str]]:
    """본인 팀 + 본인 role. 미소속이면 None."""
    row = (await db.execute(
        select(Team, TeamMember.role)
        .join(TeamMember, Team.id == TeamMember.team_id)
        .where(TeamMember.user_id == user_id)
        .limit(1)
    )).first()
    if not row:
        return None
    return row[0], row[1]


@router.get("/me", summary="내 팀 정보")
async def get_my_team(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    info = await _load_my_team(db, user.id)
    if not info:
        return {"team": None, "role": None, "members": []}

    team, my_role = info
    members_rows = (await db.execute(
        select(User, TeamMember.role)
        .join(TeamMember, TeamMember.user_id == User.id)
        .where(TeamMember.team_id == team.id)
        .order_by(TeamMember.role.desc(), User.name)
    )).all()
    members = [_serialize_member(u, role) for u, role in members_rows]
    return {
        "team": {
            "id": team.id,
            "name": team.name,
            "owner_user_id": team.owner_user_id,
            "created_at": team.created_at.isoformat() if team.created_at else None,
        },
        "role": my_role,
        "members": members,
    }


@router.post("", summary="팀 생성")
async def create_team(
    payload: TeamCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="팀 이름을 입력해주세요.")

    existing = await get_my_team_id(db, user.id)
    if existing:
        # 본인이 1인 팀(혼자만 멤버 + 본인이 owner)이면 자동 정리 후 새 팀 생성
        # — OAuth 초기 자동 생성 1인 팀의 잔재를 매끄럽게 처리
        member_count = (await db.execute(
            select(func.count()).select_from(TeamMember).where(TeamMember.team_id == existing)
        )).scalar() or 0
        existing_team = (await db.execute(
            select(Team).where(Team.id == existing)
        )).scalar_one_or_none()
        if member_count == 1 and existing_team and existing_team.owner_user_id == user.id:
            my_tm = (await db.execute(
                select(TeamMember).where(
                    TeamMember.team_id == existing, TeamMember.user_id == user.id,
                )
            )).scalar_one_or_none()
            if my_tm:
                await db.delete(my_tm)
            if existing_team:
                await db.delete(existing_team)
            await db.flush()
        else:
            raise HTTPException(
                status_code=400,
                detail="이미 다른 팀에 속해있습니다. 기존 팀에서 탈퇴 후 다시 시도하세요.",
            )

    team = Team(name=name, owner_user_id=user.id)
    db.add(team)
    await db.flush()
    db.add(TeamMember(team_id=team.id, user_id=user.id, role="owner"))
    await db.commit()
    await db.refresh(team)
    return {
        "team": {
            "id": team.id,
            "name": team.name,
            "owner_user_id": team.owner_user_id,
            "created_at": team.created_at.isoformat() if team.created_at else None,
        },
        "role": "owner",
    }


@router.patch("/me", summary="팀 이름 변경 (팀장)")
async def rename_my_team(
    payload: TeamRename,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    info = await _load_my_team(db, user.id)
    if not info:
        raise HTTPException(status_code=404, detail="속한 팀이 없습니다.")
    team, my_role = info
    if my_role != "owner":
        raise HTTPException(status_code=403, detail="팀장만 팀 이름을 변경할 수 있습니다.")
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="팀 이름을 입력해주세요.")
    team.name = name
    await db.commit()
    return {"id": team.id, "name": team.name}


@router.post("/me/invite", summary="멤버 초대 (팀장)")
async def invite_member(
    payload: TeamInvite,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """팀원 초대 — invitation row 만 생성하고 알림 발송. 받는 사용자가 수락해야
    실제 멤버로 등록됨."""
    info = await _load_my_team(db, user.id)
    if not info:
        raise HTTPException(status_code=404, detail="속한 팀이 없습니다. 먼저 팀을 만드세요.")
    team, my_role = info
    if my_role != "owner":
        raise HTTPException(status_code=403, detail="팀장만 멤버를 초대할 수 있습니다.")

    email = (payload.email or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="이메일을 입력해주세요.")

    target = (await db.execute(
        select(User).where(func.lower(User.email) == email)
    )).scalar_one_or_none()
    if not target:
        raise HTTPException(
            status_code=400,
            detail="해당 이메일로 가입한 사용자가 없습니다. 초대할 사람이 먼저 한 번 로그인해야 합니다.",
        )
    if target.id == user.id:
        raise HTTPException(status_code=400, detail="본인은 이미 팀장입니다.")

    # 이미 같은 팀 멤버?
    already_member = (await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team.id, TeamMember.user_id == target.id,
        )
    )).scalar_one_or_none()
    if already_member:
        raise HTTPException(status_code=400, detail="이미 팀 멤버입니다.")

    # 같은 팀에 pending 초대가 이미 있는지
    pending = (await db.execute(
        select(TeamInvitation).where(
            TeamInvitation.team_id == team.id,
            TeamInvitation.invitee_user_id == target.id,
            TeamInvitation.status == "pending",
        )
    )).scalar_one_or_none()
    if pending:
        raise HTTPException(status_code=400, detail="이미 초대장을 보냈습니다. 상대가 수락하기를 기다려주세요.")

    # 다른 팀에 이미 멤버라면 거부 — 단 1인 팀(혼자 owner)은 수락 시점에 자동 정리되므로
    # 초대 자체는 허용 (수락 시 처리)
    invitation = TeamInvitation(
        team_id=team.id,
        inviter_user_id=user.id,
        invitee_user_id=target.id,
        status="pending",
    )
    db.add(invitation)
    await db.commit()
    await db.refresh(invitation)

    # 알림 — 받는 사용자에게 WebSocket 으로 push (인메모리 history 에도 저장)
    try:
        await notification_manager.send_to_user(
            str(target.id),
            {
                "type": "team_invitation",
                "data": {
                    "invitation_id": invitation.id,
                    "team_id": team.id,
                    "team_name": team.name,
                    "inviter_name": user.name or user.email,
                    "inviter_email": user.email,
                    "message": f"{user.name or user.email} 님이 '{team.name}' 팀에 초대했습니다.",
                },
            },
        )
    except Exception as e:
        logger.warning(f"초대 알림 발송 실패 (DB 초대는 정상 생성): {e}")

    return {
        "invitation_id": invitation.id,
        "invitee_email": target.email,
        "invitee_name": target.name,
        "status": "pending",
        "message": f"{target.name or target.email} 님에게 초대장을 보냈습니다. 수락하면 팀 멤버로 등록됩니다.",
    }


@router.get("/me/invitations", summary="내가 받은 초대 (pending)")
async def list_my_invitations(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rows = (await db.execute(
        select(TeamInvitation, Team, User)
        .join(Team, TeamInvitation.team_id == Team.id)
        .join(User, TeamInvitation.inviter_user_id == User.id)
        .where(
            TeamInvitation.invitee_user_id == user.id,
            TeamInvitation.status == "pending",
        )
        .order_by(TeamInvitation.created_at.desc())
    )).all()
    return [
        {
            "id": inv.id,
            "team_id": team.id,
            "team_name": team.name,
            "inviter_name": inviter.name,
            "inviter_email": inviter.email,
            "created_at": inv.created_at.isoformat() if inv.created_at else None,
        }
        for inv, team, inviter in rows
    ]


@router.get("/me/sent-invitations", summary="팀이 보낸 pending 초대 (팀장)")
async def list_sent_invitations(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    info = await _load_my_team(db, user.id)
    if not info:
        return []
    team, my_role = info
    if my_role != "owner":
        return []
    rows = (await db.execute(
        select(TeamInvitation, User)
        .join(User, TeamInvitation.invitee_user_id == User.id)
        .where(
            TeamInvitation.team_id == team.id,
            TeamInvitation.status == "pending",
        )
        .order_by(TeamInvitation.created_at.desc())
    )).all()
    return [
        {
            "id": inv.id,
            "invitee_user_id": invitee.id,
            "invitee_email": invitee.email,
            "invitee_name": invitee.name,
            "created_at": inv.created_at.isoformat() if inv.created_at else None,
        }
        for inv, invitee in rows
    ]


@router.post("/invitations/{invitation_id}/accept", summary="초대 수락")
async def accept_invitation(
    invitation_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    inv = (await db.execute(
        select(TeamInvitation).where(TeamInvitation.id == invitation_id)
    )).scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="초대장을 찾을 수 없습니다.")
    if inv.invitee_user_id != user.id:
        raise HTTPException(status_code=403, detail="이 초대는 본인에게 온 것이 아닙니다.")
    if inv.status != "pending":
        raise HTTPException(status_code=400, detail=f"이미 처리된 초대입니다 (status={inv.status}).")

    # 본인이 다른 팀에 속해있다면 — 1인 팀이면 자동 정리, 아니면 거부
    existing_team_id = await get_my_team_id(db, user.id)
    if existing_team_id == inv.team_id:
        inv.status = "accepted"
        inv.responded_at = datetime.utcnow()
        await db.commit()
        return {"status": "accepted", "team_id": inv.team_id}
    if existing_team_id:
        member_count = (await db.execute(
            select(func.count()).select_from(TeamMember).where(TeamMember.team_id == existing_team_id)
        )).scalar() or 0
        existing_team = (await db.execute(
            select(Team).where(Team.id == existing_team_id)
        )).scalar_one_or_none()
        is_solo_owner = (
            member_count == 1
            and existing_team is not None
            and existing_team.owner_user_id == user.id
        )
        if not is_solo_owner:
            raise HTTPException(
                status_code=400,
                detail="이미 다른 팀에 속해있습니다. 기존 팀에서 탈퇴 후 다시 시도하세요.",
            )
        # 1인 팀 정리
        my_tm = (await db.execute(
            select(TeamMember).where(
                TeamMember.team_id == existing_team_id, TeamMember.user_id == user.id,
            )
        )).scalar_one_or_none()
        if my_tm:
            await db.delete(my_tm)
        if existing_team:
            await db.delete(existing_team)
        await db.flush()

    db.add(TeamMember(team_id=inv.team_id, user_id=user.id, role="member"))
    inv.status = "accepted"
    inv.responded_at = datetime.utcnow()
    await db.commit()

    # 팀장에게 수락 알림
    try:
        team = (await db.execute(select(Team).where(Team.id == inv.team_id))).scalar_one_or_none()
        await notification_manager.send_to_user(
            str(inv.inviter_user_id),
            {
                "type": "team_invitation_accepted",
                "data": {
                    "team_id": inv.team_id,
                    "team_name": team.name if team else "",
                    "user_name": user.name or user.email,
                    "message": f"{user.name or user.email} 님이 팀 초대를 수락했습니다.",
                },
            },
        )
    except Exception as e:
        logger.warning(f"수락 알림 발송 실패: {e}")
    return {"status": "accepted", "team_id": inv.team_id}


@router.post("/invitations/{invitation_id}/decline", summary="초대 거절")
async def decline_invitation(
    invitation_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    inv = (await db.execute(
        select(TeamInvitation).where(TeamInvitation.id == invitation_id)
    )).scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="초대장을 찾을 수 없습니다.")
    if inv.invitee_user_id != user.id:
        raise HTTPException(status_code=403, detail="이 초대는 본인에게 온 것이 아닙니다.")
    if inv.status != "pending":
        raise HTTPException(status_code=400, detail=f"이미 처리된 초대입니다 (status={inv.status}).")

    inv.status = "declined"
    inv.responded_at = datetime.utcnow()
    await db.commit()
    return {"status": "declined"}


@router.delete("/me/invitations/{invitation_id}", summary="보낸 초대 취소 (팀장)")
async def cancel_invitation(
    invitation_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    info = await _load_my_team(db, user.id)
    if not info:
        raise HTTPException(status_code=404, detail="속한 팀이 없습니다.")
    team, my_role = info
    if my_role != "owner":
        raise HTTPException(status_code=403, detail="팀장만 초대를 취소할 수 있습니다.")
    inv = (await db.execute(
        select(TeamInvitation).where(
            TeamInvitation.id == invitation_id,
            TeamInvitation.team_id == team.id,
        )
    )).scalar_one_or_none()
    if not inv or inv.status != "pending":
        raise HTTPException(status_code=404, detail="취소 가능한 초대를 찾을 수 없습니다.")
    inv.status = "cancelled"
    inv.responded_at = datetime.utcnow()
    await db.commit()
    return {"status": "cancelled", "id": invitation_id}


@router.delete("/me/members/{user_id}", summary="멤버 제거 (팀장)")
async def remove_member(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    info = await _load_my_team(db, user.id)
    if not info:
        raise HTTPException(status_code=404, detail="속한 팀이 없습니다.")
    team, my_role = info
    if my_role != "owner":
        raise HTTPException(status_code=403, detail="팀장만 멤버를 제거할 수 있습니다.")
    if user_id == user.id:
        raise HTTPException(status_code=400, detail="본인은 이 메뉴로 제거할 수 없습니다. 팀 탈퇴를 사용하세요.")

    tm = (await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team.id, TeamMember.user_id == user_id
        )
    )).scalar_one_or_none()
    if not tm:
        raise HTTPException(status_code=404, detail="해당 멤버가 팀에 없습니다.")
    await _isolate_visits_for_user(db, user_id)
    await db.delete(tm)
    await db.commit()
    return {"ok": True, "removed_user_id": user_id}


@router.post("/me/leave", summary="팀 탈퇴")
async def leave_team(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    info = await _load_my_team(db, user.id)
    if not info:
        raise HTTPException(status_code=404, detail="속한 팀이 없습니다.")
    team, my_role = info

    # 팀원 수 확인
    member_count = (await db.execute(
        select(func.count()).select_from(TeamMember).where(TeamMember.team_id == team.id)
    )).scalar() or 0

    if my_role == "owner" and member_count > 1:
        raise HTTPException(
            status_code=400,
            detail="팀장은 다른 멤버에게 권한을 위임한 후에 탈퇴할 수 있습니다 (1.x 지원 예정). "
                   "현재는 모든 멤버를 먼저 제거하거나, 팀 자체를 삭제하세요.",
        )

    # 본인 멤버십 삭제
    my_tm = (await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team.id, TeamMember.user_id == user.id
        )
    )).scalar_one_or_none()
    if my_tm:
        await _isolate_visits_for_user(db, user.id)
        await db.delete(my_tm)

    # 마지막 멤버였으면 팀도 삭제
    if member_count <= 1:
        await db.delete(team)

    await db.commit()
    return {"ok": True}
