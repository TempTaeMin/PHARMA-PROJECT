"""대시보드 API — 내 교수 스케줄 + 방문현황 요약"""
import json
from calendar import monthrange

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_
from sqlalchemy.orm import selectinload
from datetime import datetime, timedelta
from app.auth.deps import get_current_user
from app.models.connection import get_db
from app.utils.timeutil import iso_utc
from app.models.database import (
    Doctor, Hospital, ScheduleChange, User, UserDoctorGrade,
    VisitLog, VisitMemo,
)


async def _visit_user_filter(db: AsyncSession, user_id: int):
    """본인 일정 + 본인이 수신자로 지정된 visibility='team' 일정 합집합 조건.

    선택 공유 모델에서는 visit_log_recipients 테이블 참조로 본인 포함 여부를 판정.
    팀 미소속이어도 다른 팀의 누군가가 본인을 수신자로 지정했다면 노출되지만 — 1.0
    OAuth 가입 흐름상 모든 사용자는 1인 팀을 가지므로 사실상 같은 팀 안에서만 가능.
    """
    return or_(
        VisitLog.user_id == user_id,
        and_(
            VisitLog.visibility == "team",
            VisitLog.recipients.any(User.id == user_id),
        ),
    )

router = APIRouter(prefix="/api/dashboard", tags=["대시보드"])


@router.get("/", summary="대시보드 요약 데이터")
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")
    today_dow = today.weekday()

    # 내 교수 = 현재 사용자가 등급 A/B/C 매긴 의사
    grade_rows = (await db.execute(
        select(UserDoctorGrade).where(
            UserDoctorGrade.user_id == user.id,
            UserDoctorGrade.grade.in_(["A", "B", "C"]),
        )
    )).scalars().all()
    grade_by_doctor = {g.doctor_id: g.grade for g in grade_rows}
    if not grade_by_doctor:
        return {
            "today": today_str,
            "today_dow": today_dow,
            "doctors": [],
            "recent_visits": [],
            "recent_changes": [],
        }
    query = (
        select(Doctor)
        .options(
            selectinload(Doctor.schedules),
            selectinload(Doctor.date_schedules),
            selectinload(Doctor.hospital),
            selectinload(Doctor.visit_logs),
        )
        .where(Doctor.is_active == True, Doctor.id.in_(grade_by_doctor.keys()))
    )
    result = await db.execute(query)
    doctors = result.scalars().all()

    doctor_list = []
    for d in doctors:
        active_schedules = [
            {
                "day_of_week": s.day_of_week,
                "time_slot": s.time_slot,
                "start_time": s.start_time,
                "end_time": s.end_time,
                "location": s.location or "",
            }
            for s in d.schedules
            if s.is_active
        ]
        date_scheds = [
            {
                "schedule_date": ds.schedule_date,
                "time_slot": ds.time_slot,
                "start_time": ds.start_time,
                "end_time": ds.end_time,
                "location": ds.location or "",
                "status": ds.status or "진료",
            }
            for ds in d.date_schedules
            if ds.schedule_date >= today_str
        ]
        date_scheds.sort(key=lambda x: (x["schedule_date"], x["time_slot"]))

        # 최근 방문일
        visit_dates = [v.visit_date for v in d.visit_logs if v.visit_date]
        last_visit = max(visit_dates).isoformat() if visit_dates else None

        doctor_list.append({
            "id": d.id,
            "name": d.name,
            "department": d.department,
            "position": d.position,
            "specialty": d.specialty,
            "hospital_name": d.hospital.name if d.hospital else None,
            "visit_grade": grade_by_doctor.get(d.id),
            "notes": d.notes,
            "schedules": active_schedules,
            "date_schedules": date_scheds,
            "last_visit_date": last_visit,
        })

    # 최근 방문 기록 (30일) — 본인 일정 + 팀 공유 일정 합집합
    doctor_ids = [d.id for d in doctors]
    visit_list = []
    if doctor_ids:
        from app.api.visits import author_name_map
        user_filter = await _visit_user_filter(db, user.id)
        visit_query = (
            select(VisitLog, User.name)
            .outerjoin(User, VisitLog.user_id == User.id)
            .where(
                user_filter,
                VisitLog.doctor_id.in_(doctor_ids),
                VisitLog.visit_date >= today - timedelta(days=30),
            )
            .order_by(VisitLog.visit_date.desc())
            .limit(20)
        )
        visit_rows = (await db.execute(visit_query)).all()
        name_map = {d.id: d.name for d in doctors}
        hosp_map = {d.id: (d.hospital.name if d.hospital else "") for d in doctors}
        author_ids: list[int] = []
        for v, _ in visit_rows:
            if v.notes_author_id:
                author_ids.append(v.notes_author_id)
            if v.post_notes_author_id:
                author_ids.append(v.post_notes_author_id)
        author_map = await author_name_map(db, author_ids)

        # 댓글 메타: 각 visit 별 댓글 수 + 최근 작성자 1~2명 이름
        recent_visit_ids = [v.id for v, _ in visit_rows]
        memo_meta: dict[int, dict] = {}
        if recent_visit_ids:
            meta_rows = (await db.execute(
                select(VisitMemo.visit_log_id, VisitMemo.user_id, User.name)
                .outerjoin(User, VisitMemo.user_id == User.id)
                .where(VisitMemo.visit_log_id.in_(recent_visit_ids))
                .order_by(VisitMemo.visit_log_id.asc(), VisitMemo.created_at.desc())
            )).all()
            for vid, uid, uname in meta_rows:
                meta = memo_meta.setdefault(vid, {"count": 0, "authors": []})
                meta["count"] += 1
                # 최근순 정렬 — 본인 제외한 다른 작성자 최대 2명만 표시
                if uid != user.id and uname and len(meta["authors"]) < 2 and uname not in meta["authors"]:
                    meta["authors"].append(uname)

        visit_list = [
            {
                "id": v.id,
                "doctor_id": v.doctor_id,
                "doctor_name": name_map.get(v.doctor_id, ""),
                "hospital_name": hosp_map.get(v.doctor_id, ""),
                "visit_date": v.visit_date.isoformat() if v.visit_date else None,
                "status": v.status,
                "product": v.product,
                "visibility": v.visibility or "private",
                "owner_user_id": v.user_id,
                "owner_name": owner_name,
                "is_mine": v.user_id == user.id,
                "comment_count": max(0, memo_meta.get(v.id, {"count": 0})["count"] - 1),
                "comment_authors": memo_meta.get(v.id, {"authors": []})["authors"],
                "notes_author_id": v.notes_author_id,
                "notes_author_name": author_map.get(v.notes_author_id) if v.notes_author_id else None,
                "notes_updated_at": iso_utc(v.notes_updated_at),
                "post_notes_author_id": v.post_notes_author_id,
                "post_notes_author_name": author_map.get(v.post_notes_author_id) if v.post_notes_author_id else None,
                "post_notes_updated_at": iso_utc(v.post_notes_updated_at),
            }
            for v, owner_name in visit_rows
        ]

    # 최근 일정 변경 (7일)
    changes = []
    if doctor_ids:
        change_query = (
            select(ScheduleChange)
            .where(
                ScheduleChange.doctor_id.in_(doctor_ids),
                ScheduleChange.detected_at >= today - timedelta(days=7),
            )
            .order_by(ScheduleChange.detected_at.desc())
            .limit(10)
        )
        change_result = await db.execute(change_query)
        name_map = {d.id: d.name for d in doctors}
        days = ["월", "화", "수", "목", "금", "토", "일"]
        slots = {"morning": "오전", "afternoon": "오후", "evening": "야간"}
        changes = [
            {
                "id": c.id,
                "doctor_name": name_map.get(c.doctor_id, ""),
                "change_type": c.change_type,
                "day": days[c.original_day] if c.original_day is not None and c.original_day < 7 else "",
                "time_slot": slots.get(c.original_time_slot, c.original_time_slot or ""),
                "detected_at": iso_utc(c.detected_at),
            }
            for c in change_result.scalars().all()
        ]

    return {
        "today": today_str,
        "today_dow": today_dow,
        "doctors": doctor_list,
        "recent_visits": visit_list,
        "recent_changes": changes,
    }


@router.get("/my-visits", summary="내 교수 월간 방문 기록")
async def my_visits(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """내 교수(현재 사용자가 등급 A/B/C 매긴 의사) 의 한 달치 VisitLog 를 반환.

    - 완료 기록(성공/부재/거절) + 계획(예정) 모두 포함
    - 월간 캘린더 플래너에서 한 번에 로드해 클라이언트에서 날짜별로 분류
    """
    last_day = monthrange(year, month)[1]
    start = datetime(year, month, 1, 0, 0, 0)
    end = datetime(year, month, last_day, 23, 59, 59)
    start_str = f"{year:04d}-{month:02d}-01"
    end_str = f"{year:04d}-{month:02d}-{last_day:02d}"

    graded_sub = select(UserDoctorGrade.doctor_id).where(
        UserDoctorGrade.user_id == user.id,
        UserDoctorGrade.grade.in_(["A", "B", "C"]),
    )
    grade_rows = (await db.execute(
        select(UserDoctorGrade).where(UserDoctorGrade.user_id == user.id)
    )).scalars().all()
    grade_by_doctor = {g.doctor_id: g.grade for g in grade_rows}

    # 공지 케이스: 게시 기간(announce_start/end) 이 이 달과 겹치는 행, 옛 행은 visit_date 폴백
    announcement_period_overlap = and_(
        VisitLog.category == "announcement",
        or_(
            and_(
                VisitLog.announce_start_date.isnot(None),
                VisitLog.announce_start_date <= end_str,
                VisitLog.announce_end_date >= start_str,
            ),
            and_(
                VisitLog.announce_start_date.is_(None),
                VisitLog.visit_date >= start,
                VisitLog.visit_date <= end,
            ),
        ),
    )
    # 비-공지 케이스: visit_date 가 이 달 + 등급/personal/공유 매칭
    non_announcement_match = and_(
        VisitLog.category != "announcement",
        VisitLog.visit_date >= start,
        VisitLog.visit_date <= end,
        or_(
            VisitLog.user_id != user.id,  # 공유받은 일정 (등급 무관)
            Doctor.id.in_(graded_sub),
            VisitLog.category == "personal",
        ),
    )

    user_filter = await _visit_user_filter(db, user.id)
    query = (
        select(VisitLog, Doctor, Hospital, User.name)
        .outerjoin(Doctor, VisitLog.doctor_id == Doctor.id)
        .outerjoin(Hospital, Doctor.hospital_id == Hospital.id)
        .outerjoin(User, VisitLog.user_id == User.id)
        .where(
            user_filter,
            or_(non_announcement_match, announcement_period_overlap),
        )
        .order_by(VisitLog.visit_date.asc())
    )
    rows = (await db.execute(query)).all()

    def _parse_ai(raw):
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return None

    from app.api.visits import author_name_map

    # 댓글(VisitMemo) 일괄 로딩 — visit 별 정렬된 리스트로 그룹핑
    visit_ids = [v.id for v, *_ in rows]
    memos_by_visit: dict[int, list[tuple[VisitMemo, str | None]]] = {}
    if visit_ids:
        memo_query = (
            select(VisitMemo, User.name)
            .outerjoin(User, VisitMemo.user_id == User.id)
            .where(VisitMemo.visit_log_id.in_(visit_ids))
            .order_by(VisitMemo.visit_log_id.asc(), VisitMemo.created_at.asc())
        )
        for m, author_name in (await db.execute(memo_query)).all():
            memos_by_visit.setdefault(m.visit_log_id, []).append((m, author_name))

    author_ids: list[int] = []
    for v, *_ in rows:
        if v.notes_author_id:
            author_ids.append(v.notes_author_id)
        if v.post_notes_author_id:
            author_ids.append(v.post_notes_author_id)
    author_map = await author_name_map(db, author_ids)

    def _build_memos(visit_id: int, is_visit_mine: bool) -> list[dict]:
        """visit 의 댓글 리스트 — 본인 raw 만 노출, 나머지는 strip."""
        items = memos_by_visit.get(visit_id, [])
        out = []
        for idx, (m, author_name) in enumerate(items):
            mine = m.user_id == user.id
            out.append({
                "id": m.id,
                "user_id": m.user_id,
                "author_name": author_name,
                "title": m.title,
                "raw_memo": m.raw_memo if mine else None,
                "ai_summary": _parse_ai(m.ai_summary),
                "is_root": idx == 0,
                "is_mine": mine,
                "created_at": iso_utc(m.created_at),
                "updated_at": iso_utc(m.updated_at),
            })
        return out

    result = []
    for v, d, h, owner_name in rows:
        is_mine = v.user_id == user.id
        memos = _build_memos(v.id, is_mine)
        # 호환 필드: 1.x 까지 유지. ai_summary/memo_id 는 root, post_notes 는 본인 raw 우선.
        root_memo = memos[0] if memos else None
        my_memo = next((m for m in memos if m["is_mine"]), None)
        # raw 결과 메모는 본인 VisitMemo.raw_memo 만 신뢰. visit_logs.post_notes 는
        # dual-write 시기에 다른 사람 raw 가 누출됐을 수 있으니 폴백 금지.
        compat_post_notes = my_memo["raw_memo"] if my_memo else None
        result.append({
            "id": v.id,
            "doctor_id": v.doctor_id,
            "doctor_name": d.name if d else None,
            "hospital_name": h.name if h else None,
            "department": d.department if d else None,
            "visit_grade": grade_by_doctor.get(d.id) if d else None,
            "category": v.category,
            "title": v.title,
            "visit_date": v.visit_date.isoformat() if v.visit_date else None,
            "status": v.status,
            "product": v.product,
            "notes": v.notes,
            "post_notes": compat_post_notes,
            "next_action": v.next_action,
            "ai_summary": root_memo["ai_summary"] if root_memo else None,
            "memo_id": (my_memo["id"] if my_memo else (root_memo["id"] if root_memo else None)),
            "memos": memos,
            "comment_count": max(0, len(memos) - 1),
            "visibility": v.visibility or "private",
            "recipient_user_ids": v.recipient_user_ids if is_mine else [],
            "owner_user_id": v.user_id,
            "owner_name": owner_name,
            "is_mine": is_mine,
            "notes_author_id": v.notes_author_id,
            "notes_author_name": author_map.get(v.notes_author_id) if v.notes_author_id else None,
            "notes_updated_at": iso_utc(v.notes_updated_at),
            "post_notes_author_id": v.post_notes_author_id,
            "post_notes_author_name": author_map.get(v.post_notes_author_id) if v.post_notes_author_id else None,
            "post_notes_updated_at": iso_utc(v.post_notes_updated_at),
            "announce_start_date": v.announce_start_date,
            "announce_end_date": v.announce_end_date,
        })
    return result
