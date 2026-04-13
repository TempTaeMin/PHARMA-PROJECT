"""대시보드 API — 내 교수 스케줄 + 방문현황 요약"""
from calendar import monthrange

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from datetime import datetime, timedelta
from app.models.connection import get_db
from app.models.database import Doctor, Hospital, VisitLog, ScheduleChange

router = APIRouter(prefix="/api/dashboard", tags=["대시보드"])


@router.get("/", summary="대시보드 요약 데이터")
async def get_dashboard(db: AsyncSession = Depends(get_db)):
    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")
    today_dow = today.weekday()

    # 내 교수 (visit_grade A/B/C) + 스케줄 + 병원
    query = (
        select(Doctor)
        .options(
            selectinload(Doctor.schedules),
            selectinload(Doctor.date_schedules),
            selectinload(Doctor.hospital),
            selectinload(Doctor.visit_logs),
        )
        .where(Doctor.is_active == True, Doctor.visit_grade.in_(["A", "B", "C"]))
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
            "visit_grade": d.visit_grade,
            "notes": d.notes,
            "schedules": active_schedules,
            "date_schedules": date_scheds,
            "last_visit_date": last_visit,
        })

    # 최근 방문 기록 (30일)
    doctor_ids = [d.id for d in doctors]
    visit_list = []
    if doctor_ids:
        visit_query = (
            select(VisitLog)
            .where(
                VisitLog.doctor_id.in_(doctor_ids),
                VisitLog.visit_date >= today - timedelta(days=30),
            )
            .order_by(VisitLog.visit_date.desc())
            .limit(20)
        )
        visit_result = await db.execute(visit_query)
        name_map = {d.id: d.name for d in doctors}
        hosp_map = {d.id: (d.hospital.name if d.hospital else "") for d in doctors}
        visit_list = [
            {
                "id": v.id,
                "doctor_id": v.doctor_id,
                "doctor_name": name_map.get(v.doctor_id, ""),
                "hospital_name": hosp_map.get(v.doctor_id, ""),
                "visit_date": v.visit_date.isoformat() if v.visit_date else None,
                "status": v.status,
                "product": v.product,
            }
            for v in visit_result.scalars().all()
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
                "detected_at": c.detected_at.isoformat() if c.detected_at else None,
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
):
    """내 교수(visit_grade A/B/C) 의 한 달치 VisitLog 를 반환.

    - 완료 기록(성공/부재/거절) + 계획(예정) 모두 포함
    - 월간 캘린더 플래너에서 한 번에 로드해 클라이언트에서 날짜별로 분류
    """
    last_day = monthrange(year, month)[1]
    start = datetime(year, month, 1, 0, 0, 0)
    end = datetime(year, month, last_day, 23, 59, 59)

    query = (
        select(VisitLog, Doctor, Hospital)
        .join(Doctor, VisitLog.doctor_id == Doctor.id)
        .outerjoin(Hospital, Doctor.hospital_id == Hospital.id)
        .where(
            Doctor.visit_grade.in_(["A", "B", "C"]),
            VisitLog.visit_date >= start,
            VisitLog.visit_date <= end,
        )
        .order_by(VisitLog.visit_date.asc())
    )
    rows = (await db.execute(query)).all()

    return [
        {
            "id": v.id,
            "doctor_id": v.doctor_id,
            "doctor_name": d.name,
            "hospital_name": h.name if h else None,
            "department": d.department,
            "visit_grade": d.visit_grade,
            "visit_date": v.visit_date.isoformat() if v.visit_date else None,
            "status": v.status,
            "product": v.product,
            "notes": v.notes,
            "next_action": v.next_action,
        }
        for v, d, h in rows
    ]
