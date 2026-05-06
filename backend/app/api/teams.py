"""팀 관리 API — 팀 생성/멤버 초대(승인 흐름)/제거/탈퇴/이름 변경.

1.x 멀티팀 정책 (2026-05-06):
- 신규 가입자는 팀 미소속
- 한 사용자가 여러 팀의 owner 또는 member 가능
- "활성 팀" 개념 — `users.active_team_id` 가 일정/메모/공지의 기본 컨텍스트
- 사이드바 dropdown 에서 활성 팀 전환 (`POST /api/teams/me/switch/{team_id}`)
- `GET /api/teams/me/list` — 모든 소속 팀 (전환 dropdown 용)
- `GET /api/teams/me` — 활성 팀 상세 (멤버 포함)
- 초대는 invitation row 만 생성 → 받는 사용자가 수락해야 멤버 등록
- 수락 시 새 팀이 자동으로 active 가 됨
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
    """현재 **활성** 팀 + 본인 role. 미소속이면 None.
    active_team_id 가 박혀있으면 그 팀, 아니면 가장 오래된 멤버십."""
    active_team_id = await get_my_team_id(db, user_id)
    if not active_team_id:
        return None
    row = (await db.execute(
        select(Team, TeamMember.role)
        .join(TeamMember, Team.id == TeamMember.team_id)
        .where(TeamMember.user_id == user_id, TeamMember.team_id == active_team_id)
        .limit(1)
    )).first()
    if not row:
        return None
    return row[0], row[1]


async def _set_active_team(db: AsyncSession, user_id: int, team_id: Optional[int]) -> None:
    """활성 팀 변경. None 이면 unset (팀 미소속 상태로). 멤버 검증은 호출자 책임."""
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user:
        user.active_team_id = team_id


async def _resolve_new_active_after_leave(
    db: AsyncSession, user_id: int, leaving_team_id: int,
) -> Optional[int]:
    """팀을 떠날 때 다음 활성 팀 결정. 다른 멤버십이 있으면 가장 오래된 거, 없으면 None."""
    other = (await db.execute(
        select(TeamMember).where(
            TeamMember.user_id == user_id,
            TeamMember.team_id != leaving_team_id,
        ).order_by(TeamMember.id.asc()).limit(1)
    )).scalar_one_or_none()
    return other.team_id if other else None


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
    """멀티팀 정책 — 본인이 이미 다른 팀(들) 의 owner/member 여도 새 팀 생성 가능.
    새로 만든 팀이 자동으로 active_team 으로 설정됨."""
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="팀 이름을 입력해주세요.")

    team = Team(name=name, owner_user_id=user.id)
    db.add(team)
    await db.flush()
    db.add(TeamMember(team_id=team.id, user_id=user.id, role="owner"))
    await _set_active_team(db, user.id, team.id)
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


@router.get("/me/list", summary="내 모든 소속 팀 (멀티팀 dropdown)")
async def list_my_teams(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """사이드바 팀 전환 dropdown 용 — 모든 소속 팀 + 활성 팀 표시."""
    rows = (await db.execute(
        select(Team, TeamMember.role)
        .join(TeamMember, Team.id == TeamMember.team_id)
        .where(TeamMember.user_id == user.id)
        .order_by(TeamMember.id.asc())
    )).all()
    active_team_id = await get_my_team_id(db, user.id)
    return {
        "active_team_id": active_team_id,
        "teams": [
            {
                "id": t.id,
                "name": t.name,
                "owner_user_id": t.owner_user_id,
                "role": role,
                "is_active": t.id == active_team_id,
            }
            for t, role in rows
        ],
    }


@router.post("/me/switch/{team_id}", summary="활성 팀 전환")
async def switch_active_team(
    team_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """사이드바 팀 dropdown 에서 클릭 시 호출. 본인이 멤버인 팀만 활성화 가능."""
    is_member = (await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id, TeamMember.user_id == user.id,
        )
    )).scalar_one_or_none()
    if not is_member:
        raise HTTPException(status_code=403, detail="해당 팀의 멤버가 아닙니다.")
    await _set_active_team(db, user.id, team_id)
    await db.commit()
    return {"active_team_id": team_id}


@router.patch("/me", summary="팀 이름 변경 (리더)")
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
        raise HTTPException(status_code=403, detail="리더만 팀 이름을 변경할 수 있습니다.")
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="팀 이름을 입력해주세요.")
    team.name = name
    await db.commit()
    return {"id": team.id, "name": team.name}


@router.post("/me/invite", summary="멤버 초대 (리더)")
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
        raise HTTPException(status_code=403, detail="리더만 멤버를 초대할 수 있습니다.")

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
        raise HTTPException(status_code=400, detail="본인은 이미 리더입니다.")

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


@router.get("/me/sent-invitations", summary="팀이 보낸 pending 초대 (리더)")
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

    # 멀티팀 정책 — 다른 팀에 이미 있어도 OK. 단 같은 팀에 이미 멤버면 status 만 갱신.
    already_member = (await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == inv.team_id, TeamMember.user_id == user.id,
        )
    )).scalar_one_or_none()
    if already_member:
        inv.status = "accepted"
        inv.responded_at = datetime.utcnow()
        await db.commit()
        return {"status": "accepted", "team_id": inv.team_id}

    db.add(TeamMember(team_id=inv.team_id, user_id=user.id, role="member"))
    inv.status = "accepted"
    inv.responded_at = datetime.utcnow()
    # 새 팀을 활성 팀으로 자동 전환 — 가입 직후 메모/일정이 새 팀 컨텍스트에서 동작
    await _set_active_team(db, user.id, inv.team_id)
    await db.commit()

    # 리더에게 수락 알림
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


@router.delete("/me/invitations/{invitation_id}", summary="보낸 초대 취소 (리더)")
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
        raise HTTPException(status_code=403, detail="리더만 초대를 취소할 수 있습니다.")
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


@router.delete("/me/members/{user_id}", summary="멤버 제거 (리더)")
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
        raise HTTPException(status_code=403, detail="리더만 멤버를 제거할 수 있습니다.")
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

    # 제거된 멤버의 active_team 이 이 팀이었으면 다른 팀으로 자동 전환
    removed_user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if removed_user and removed_user.active_team_id == team.id:
        new_active = await _resolve_new_active_after_leave(db, user_id, team.id)
        removed_user.active_team_id = new_active

    await db.commit()
    return {"ok": True, "removed_user_id": user_id}


@router.post("/me/transfer/{user_id}", summary="리더 권한 양도 (활성 팀)")
async def transfer_ownership(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """현재 활성 팀의 리더가 다른 일반 멤버에게 owner 권한을 양도.
    본인 role: owner→member, 대상자 role: member→owner. Team.owner_user_id 도 갱신."""
    info = await _load_my_team(db, user.id)
    if not info:
        raise HTTPException(status_code=404, detail="속한 팀이 없습니다.")
    team, my_role = info
    if my_role != "owner":
        raise HTTPException(status_code=403, detail="리더만 권한을 양도할 수 있습니다.")
    if user_id == user.id:
        raise HTTPException(status_code=400, detail="본인에게는 양도할 수 없습니다.")

    target_tm = (await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team.id, TeamMember.user_id == user_id,
        )
    )).scalar_one_or_none()
    if not target_tm:
        raise HTTPException(status_code=400, detail="대상자가 같은 팀의 멤버가 아닙니다.")
    if target_tm.role == "owner":
        raise HTTPException(status_code=400, detail="이미 리더입니다.")

    my_tm = (await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team.id, TeamMember.user_id == user.id,
        )
    )).scalar_one_or_none()
    if not my_tm:
        # 방어적 — _load_my_team 가 my_role='owner' 였는데 row 없을 리 없음
        raise HTTPException(status_code=500, detail="본인 팀 멤버 row 가 없습니다.")

    my_tm.role = "member"
    target_tm.role = "owner"
    team.owner_user_id = user_id
    await db.commit()

    # 새 owner 에게 알림
    try:
        await notification_manager.send_to_user(
            str(user_id),
            {
                "type": "team_ownership_transferred",
                "data": {
                    "team_id": team.id,
                    "team_name": team.name,
                    "previous_owner_name": user.name or user.email,
                    "message": f"{user.name or user.email} 님이 '{team.name}' 팀의 리더 권한을 양도했습니다.",
                },
            },
        )
    except Exception as e:
        logger.warning(f"권한 양도 알림 발송 실패: {e}")

    return {"ok": True, "team_id": team.id, "new_owner_id": user_id}


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
            detail="리더는 다른 멤버에게 권한을 양도한 후에 탈퇴할 수 있어요. "
                   "팀 관리 화면 → 멤버 카드의 '리더로' 버튼으로 양도하세요.",
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

    # 떠나는 팀이 active 였으면 다른 팀(가장 오래된 멤버십) 으로 자동 전환. 없으면 None.
    new_active = await _resolve_new_active_after_leave(db, user.id, team.id)
    await _set_active_team(db, user.id, new_active)

    # 마지막 멤버였으면 팀도 삭제
    if member_count <= 1:
        await db.delete(team)

    await db.commit()
    return {"ok": True, "new_active_team_id": new_active}
