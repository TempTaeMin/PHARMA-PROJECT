"""관리자 모니터링 API.

사용자 목록 / 단일 사용자 raw 데이터 / 팀 / 전체 통계 / 활동 로그.
모두 admin 전용 — env `ADMIN_EMAILS` 가드 (`require_admin` 디펜던시).

베타 운영 중 "누가 쓰고 있는지" 와 "문제 발생 시 데이터 inspect" 두 가지 용도.
DB 스키마 변경 없이 기존 모델만으로 집계.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import require_admin
from app.models.connection import get_db
from app.models.database import (
    Doctor,
    Feedback,
    Hospital,
    MemoTemplate,
    Team,
    TeamInvitation,
    TeamMember,
    User,
    UserAcademicPin,
    UserDoctorGrade,
    UserDoctorMemo,
    VisitLog,
    VisitMemo,
    Report,
)

# 베타 배포일 — `since` 파라미터 미지정 시 default 시작 시점.
# 운영자가 "테스트 기간" 으로 보고 싶은 자연스러운 cutoff.
BETA_LAUNCH = datetime(2026, 5, 6, 0, 0, 0)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["관리자"])


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


@router.get("/stats", summary="전체 현황 (admin)")
async def admin_stats(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    now = datetime.utcnow()
    cutoff_24h = now - timedelta(hours=24)
    cutoff_7d = now - timedelta(days=7)
    cutoff_30d = now - timedelta(days=30)

    users_total = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    teams_total = (await db.execute(select(func.count()).select_from(Team))).scalar_one()
    visits_total = (await db.execute(select(func.count()).select_from(VisitLog))).scalar_one()

    signups_7d = (await db.execute(
        select(func.count()).select_from(User).where(User.created_at >= cutoff_7d)
    )).scalar_one()
    active_24h = (await db.execute(
        select(func.count()).select_from(User).where(User.last_login_at >= cutoff_24h)
    )).scalar_one()
    active_7d = (await db.execute(
        select(func.count()).select_from(User).where(User.last_login_at >= cutoff_7d)
    )).scalar_one()
    active_30d = (await db.execute(
        select(func.count()).select_from(User).where(User.last_login_at >= cutoff_30d)
    )).scalar_one()

    return {
        "users_total": users_total,
        "teams_total": teams_total,
        "visits_total": visits_total,
        "signups_7d": signups_7d,
        "active_24h": active_24h,
        "active_7d": active_7d,
        "active_30d": active_30d,
        "as_of": now.isoformat(),
    }


@router.get("/users", summary="사용자 목록 (admin)")
async def admin_users(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    # 각 사용자별 카운트는 correlated scalar subquery 로 — 단일 쿼리에 N+1 회피.
    team_count_sq = (
        select(func.count(TeamMember.id))
        .where(TeamMember.user_id == User.id)
        .correlate(User)
        .scalar_subquery()
    )
    doctor_count_sq = (
        select(func.count(UserDoctorGrade.id))
        .where(UserDoctorGrade.user_id == User.id)
        .correlate(User)
        .scalar_subquery()
    )
    visit_count_sq = (
        select(func.count(VisitLog.id))
        .where(VisitLog.user_id == User.id)
        .correlate(User)
        .scalar_subquery()
    )

    rows = (await db.execute(
        select(
            User,
            team_count_sq.label("team_count"),
            doctor_count_sq.label("doctor_count"),
            visit_count_sq.label("visit_count"),
        ).order_by(User.last_login_at.desc().nullslast(), User.id.desc())
    )).all()

    return [
        {
            "id": u.id,
            "email": u.email,
            "name": u.name,
            "picture": u.picture,
            "active_team_id": u.active_team_id,
            "created_at": _iso(u.created_at),
            "last_login_at": _iso(u.last_login_at),
            "team_count": team_count or 0,
            "doctor_count": doctor_count or 0,
            "visit_count": visit_count or 0,
        }
        for u, team_count, doctor_count, visit_count in rows
    ]


@router.get("/users/{user_id}", summary="사용자 상세 (admin)")
async def admin_user_detail(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    u = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not u:
        raise HTTPException(404, "사용자를 찾을 수 없습니다.")

    team_rows = (await db.execute(
        select(Team, TeamMember.role)
        .join(TeamMember, TeamMember.team_id == Team.id)
        .where(TeamMember.user_id == user_id)
        .order_by(TeamMember.id.asc())
    )).all()
    teams = [
        {
            "id": t.id,
            "name": t.name,
            "role": role,
            "is_active": (t.id == u.active_team_id),
            "created_at": _iso(t.created_at),
        }
        for t, role in team_rows
    ]

    doctor_count = (await db.execute(
        select(func.count(UserDoctorGrade.id)).where(UserDoctorGrade.user_id == user_id)
    )).scalar_one()
    visit_count = (await db.execute(
        select(func.count(VisitLog.id)).where(VisitLog.user_id == user_id)
    )).scalar_one()

    return {
        "id": u.id,
        "email": u.email,
        "name": u.name,
        "picture": u.picture,
        "google_sub": u.google_sub,
        "active_team_id": u.active_team_id,
        "created_at": _iso(u.created_at),
        "last_login_at": _iso(u.last_login_at),
        "teams": teams,
        "stats": {
            "team_count": len(teams),
            "doctor_count": doctor_count or 0,
            "visit_count": visit_count or 0,
        },
    }


@router.get("/users/{user_id}/visits", summary="사용자 일정 raw (admin)")
async def admin_user_visits(
    user_id: int,
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    rows = (await db.execute(
        select(VisitLog, Doctor)
        .outerjoin(Doctor, VisitLog.doctor_id == Doctor.id)
        .where(VisitLog.user_id == user_id)
        .order_by(VisitLog.visit_date.desc())
        .limit(limit)
    )).all()

    out = []
    for v, d in rows:
        out.append({
            "id": v.id,
            "visit_date": _iso(v.visit_date),
            "category": v.category,
            "status": v.status,
            "visibility": v.visibility,
            "title": v.title,
            "doctor_id": v.doctor_id,
            "doctor_name": (d.name if d else None) or v.doctor_name_snapshot,
            "doctor_dept": (d.department if d else None) or v.doctor_dept_snapshot,
            "hospital_name": v.hospital_name_snapshot,
            "product": v.product,
            "notes_preview": (v.notes or "")[:200] if v.notes else None,
            "post_notes_preview": (v.post_notes or "")[:200] if v.post_notes else None,
            "created_at": _iso(v.created_at),
        })
    return out


@router.get("/users/{user_id}/doctors", summary="사용자 등록 의사 raw (admin)")
async def admin_user_doctors(
    user_id: int,
    limit: int = Query(200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    rows = (await db.execute(
        select(UserDoctorGrade, Doctor, Hospital)
        .join(Doctor, Doctor.id == UserDoctorGrade.doctor_id)
        .outerjoin(Hospital, Hospital.id == Doctor.hospital_id)
        .where(UserDoctorGrade.user_id == user_id)
        .order_by(UserDoctorGrade.grade.asc(), Doctor.name.asc())
        .limit(limit)
    )).all()

    return [
        {
            "doctor_id": d.id,
            "name": d.name,
            "department": d.department,
            "position": d.position,
            "hospital_id": d.hospital_id,
            "hospital_name": h.name if h else None,
            "grade": g.grade,
            "is_active": d.is_active,
            "updated_at": _iso(g.updated_at),
        }
        for g, d, h in rows
    ]


# ─────────── 활동 로그 (테스트 기간 inspect) ───────────


def _parse_since(since: Optional[str]) -> datetime:
    """ISO 문자열 파싱. 빈값/실패 시 베타 배포일로 폴백."""
    if not since:
        return BETA_LAUNCH
    try:
        return datetime.fromisoformat(since.replace("Z", ""))
    except ValueError:
        return BETA_LAUNCH


async def _collect_activity_events(
    db: AsyncSession,
    since: datetime,
    user_id: Optional[int] = None,
) -> list[dict]:
    """기간 내 모든 사용자 활동을 표준 row 로 수집.

    각 소스(VisitLog/VisitMemo/Report/...) 의 created_at 또는 updated_at 컬럼을
    훑어 `{user_id, ts, kind, action, title, ref}` 단위로 평탄화. 시간순 정렬은
    호출자가 수행 (active-users / activity 두 엔드포인트가 같은 events 를 공유).

    user_id 가 주어지면 그 사용자 행만 (timeline 용).
    """
    events: list[dict] = []

    # ─── VisitLog: 생성 / 사전 메모 / 결과 메모 ───
    q = (
        select(VisitLog, Doctor)
        .outerjoin(Doctor, VisitLog.doctor_id == Doctor.id)
        .where(VisitLog.created_at >= since)
    )
    if user_id is not None:
        q = q.where(VisitLog.user_id == user_id)
    for v, d in (await db.execute(q)).all():
        doctor_name = (d.name if d else None) or v.doctor_name_snapshot
        title = v.title or doctor_name or "(제목 없음)"
        events.append({
            "user_id": v.user_id,
            "ts": v.created_at,
            "kind": "visit",
            "action": "create",
            "title": title,
            "ref": {"visit_id": v.id, "category": v.category, "doctor_name": doctor_name},
        })

    # 사전 메모 수정 (notes_updated_at)
    q = (
        select(VisitLog.user_id, VisitLog.id, VisitLog.title, VisitLog.notes_updated_at,
               VisitLog.doctor_name_snapshot, VisitLog.category, Doctor.name)
        .outerjoin(Doctor, VisitLog.doctor_id == Doctor.id)
        .where(VisitLog.notes_updated_at.is_not(None))
        .where(VisitLog.notes_updated_at >= since)
    )
    if user_id is not None:
        q = q.where(VisitLog.notes_author_id == user_id)
    for uid, vid, title, ts, snap_name, cat, d_name in (await db.execute(q)).all():
        events.append({
            "user_id": uid,
            "ts": ts,
            "kind": "visit_note",
            "action": "update",
            "title": title or d_name or snap_name or "(제목 없음)",
            "ref": {"visit_id": vid, "field": "notes", "category": cat},
        })

    # 결과 메모 수정 (post_notes_updated_at)
    q = (
        select(VisitLog.user_id, VisitLog.id, VisitLog.title, VisitLog.post_notes_updated_at,
               VisitLog.doctor_name_snapshot, VisitLog.category, Doctor.name)
        .outerjoin(Doctor, VisitLog.doctor_id == Doctor.id)
        .where(VisitLog.post_notes_updated_at.is_not(None))
        .where(VisitLog.post_notes_updated_at >= since)
    )
    if user_id is not None:
        q = q.where(VisitLog.post_notes_author_id == user_id)
    for uid, vid, title, ts, snap_name, cat, d_name in (await db.execute(q)).all():
        events.append({
            "user_id": uid,
            "ts": ts,
            "kind": "visit_note",
            "action": "update",
            "title": title or d_name or snap_name or "(제목 없음)",
            "ref": {"visit_id": vid, "field": "post_notes", "category": cat},
        })

    # ─── VisitMemo: 회의록 ───
    q = select(VisitMemo).where(VisitMemo.updated_at >= since)
    if user_id is not None:
        q = q.where(VisitMemo.user_id == user_id)
    for m in (await db.execute(q)).scalars().all():
        is_create = m.created_at and m.updated_at and (
            (m.updated_at - m.created_at).total_seconds() < 2
        )
        events.append({
            "user_id": m.user_id,
            "ts": m.updated_at or m.created_at,
            "kind": "memo",
            "action": "create" if is_create else "update",
            "title": m.title or m.doctor_name_snapshot or "(메모)",
            "ref": {"memo_id": m.id, "memo_type": m.memo_type, "visit_log_id": m.visit_log_id},
        })

    # ─── Report: 일일/주간 보고서 ───
    q = select(Report).where(Report.updated_at >= since)
    if user_id is not None:
        q = q.where(Report.user_id == user_id)
    for r in (await db.execute(q)).scalars().all():
        is_create = r.created_at and r.updated_at and (
            (r.updated_at - r.created_at).total_seconds() < 2
        )
        events.append({
            "user_id": r.user_id,
            "ts": r.updated_at or r.created_at,
            "kind": "report",
            "action": "create" if is_create else "update",
            "title": r.title or f"{r.report_type} {r.period_start}~{r.period_end}",
            "ref": {"report_id": r.id, "report_type": r.report_type},
        })

    # ─── UserDoctorGrade: 의사 등급 (created_at 없음 — updated_at 만) ───
    q = (
        select(UserDoctorGrade, Doctor.name)
        .outerjoin(Doctor, Doctor.id == UserDoctorGrade.doctor_id)
        .where(UserDoctorGrade.updated_at >= since)
    )
    if user_id is not None:
        q = q.where(UserDoctorGrade.user_id == user_id)
    for g, dname in (await db.execute(q)).all():
        events.append({
            "user_id": g.user_id,
            "ts": g.updated_at,
            "kind": "doctor_grade",
            "action": "update",
            "title": f"{dname or '(의사)'} → {g.grade}",
            "ref": {"doctor_id": g.doctor_id, "grade": g.grade},
        })

    # ─── UserDoctorMemo: 의사 개인 메모 ───
    q = (
        select(UserDoctorMemo, Doctor.name)
        .outerjoin(Doctor, Doctor.id == UserDoctorMemo.doctor_id)
        .where(UserDoctorMemo.updated_at >= since)
    )
    if user_id is not None:
        q = q.where(UserDoctorMemo.user_id == user_id)
    for m, dname in (await db.execute(q)).all():
        events.append({
            "user_id": m.user_id,
            "ts": m.updated_at,
            "kind": "doctor_memo",
            "action": "update",
            "title": f"{dname or '(의사)'} 메모",
            "ref": {"doctor_id": m.doctor_id},
        })

    # ─── UserAcademicPin: 학회 일정 핀 ───
    q = select(UserAcademicPin).where(UserAcademicPin.created_at >= since)
    if user_id is not None:
        q = q.where(UserAcademicPin.user_id == user_id)
    for p in (await db.execute(q)).scalars().all():
        events.append({
            "user_id": p.user_id,
            "ts": p.created_at,
            "kind": "academic_pin",
            "action": "create",
            "title": "학회 일정 핀",
            "ref": {"event_id": p.event_id},
        })

    # ─── MemoTemplate: 메모 템플릿 ───
    q = select(MemoTemplate).where(MemoTemplate.updated_at >= since)
    if user_id is not None:
        q = q.where(MemoTemplate.user_id == user_id)
    for t in (await db.execute(q)).scalars().all():
        is_create = t.created_at and t.updated_at and (
            (t.updated_at - t.created_at).total_seconds() < 2
        )
        events.append({
            "user_id": t.user_id,
            "ts": t.updated_at or t.created_at,
            "kind": "template",
            "action": "create" if is_create else "update",
            "title": t.name or "(템플릿)",
            "ref": {"template_id": t.id, "scope": t.scope},
        })

    # ─── Feedback: 베타 피드백 ───
    q = select(Feedback).where(Feedback.created_at >= since).where(Feedback.user_id.is_not(None))
    if user_id is not None:
        q = q.where(Feedback.user_id == user_id)
    for f in (await db.execute(q)).scalars().all():
        events.append({
            "user_id": f.user_id,
            "ts": f.created_at,
            "kind": "feedback",
            "action": "create",
            "title": f"피드백 ({f.category})",
            "ref": {"feedback_id": f.id, "category": f.category},
        })

    # ─── Team: 팀 생성 (owner) ───
    q = select(Team).where(Team.created_at >= since)
    if user_id is not None:
        q = q.where(Team.owner_user_id == user_id)
    for t in (await db.execute(q)).scalars().all():
        events.append({
            "user_id": t.owner_user_id,
            "ts": t.created_at,
            "kind": "team",
            "action": "create",
            "title": f"팀 생성 — {t.name}",
            "ref": {"team_id": t.id},
        })

    # ─── TeamInvitation: 초대 보냄 (inviter) ───
    q = select(TeamInvitation).where(TeamInvitation.created_at >= since)
    if user_id is not None:
        q = q.where(TeamInvitation.inviter_user_id == user_id)
    for inv in (await db.execute(q)).scalars().all():
        events.append({
            "user_id": inv.inviter_user_id,
            "ts": inv.created_at,
            "kind": "invitation",
            "action": "create",
            "title": "팀 초대 발송",
            "ref": {"team_id": inv.team_id, "invitee_user_id": inv.invitee_user_id, "status": inv.status},
        })

    return events


@router.get("/active-users", summary="기간 내 활동한 사용자 목록 (admin)")
async def admin_active_users(
    since: Optional[str] = Query(None, description="ISO datetime, default = 2026-05-06"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """테스트 기간 내 활동 1건 이상 사용자만 — by_kind 카운트 + last_activity_at."""
    since_dt = _parse_since(since)
    events = await _collect_activity_events(db, since_dt)

    # 사용자별 집계
    by_user: dict[int, dict] = {}
    for e in events:
        uid = e["user_id"]
        if uid is None:
            continue
        b = by_user.setdefault(uid, {"total": 0, "by_kind": {}, "last_ts": None})
        b["total"] += 1
        b["by_kind"][e["kind"]] = b["by_kind"].get(e["kind"], 0) + 1
        ts = e["ts"]
        if ts and (b["last_ts"] is None or ts > b["last_ts"]):
            b["last_ts"] = ts

    if not by_user:
        return []

    user_rows = (await db.execute(
        select(User).where(User.id.in_(by_user.keys()))
    )).scalars().all()
    user_map = {u.id: u for u in user_rows}

    out = []
    for uid, agg in by_user.items():
        u = user_map.get(uid)
        if not u:
            continue
        out.append({
            "id": u.id,
            "email": u.email,
            "name": u.name,
            "picture": u.picture,
            "last_activity_at": _iso(agg["last_ts"]),
            "total_activity_count": agg["total"],
            "by_kind": agg["by_kind"],
        })
    out.sort(key=lambda r: r["last_activity_at"] or "", reverse=True)
    return {"since": since_dt.isoformat(), "users": out}


@router.get("/users/{user_id}/activity", summary="사용자 활동 타임라인 (admin)")
async def admin_user_activity(
    user_id: int,
    since: Optional[str] = Query(None, description="ISO datetime, default = 2026-05-06"),
    limit: int = Query(200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """선택 사용자의 시간순 활동 (desc)."""
    since_dt = _parse_since(since)
    events = await _collect_activity_events(db, since_dt, user_id=user_id)
    events.sort(key=lambda e: e["ts"] or datetime.min, reverse=True)
    out = [
        {
            "ts": _iso(e["ts"]),
            "kind": e["kind"],
            "action": e["action"],
            "title": e["title"],
            "ref": e["ref"],
        }
        for e in events[:limit]
    ]
    return {"since": since_dt.isoformat(), "user_id": user_id, "events": out, "total": len(events)}


@router.get("/teams", summary="팀 목록 (admin)")
async def admin_teams(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    member_count_sq = (
        select(func.count(TeamMember.id))
        .where(TeamMember.team_id == Team.id)
        .correlate(Team)
        .scalar_subquery()
    )

    rows = (await db.execute(
        select(Team, User, member_count_sq.label("member_count"))
        .outerjoin(User, User.id == Team.owner_user_id)
        .order_by(Team.created_at.desc())
    )).all()

    return [
        {
            "id": t.id,
            "name": t.name,
            "owner_user_id": t.owner_user_id,
            "owner_email": owner.email if owner else None,
            "owner_name": owner.name if owner else None,
            "member_count": member_count or 0,
            "created_at": _iso(t.created_at),
        }
        for t, owner, member_count in rows
    ]
