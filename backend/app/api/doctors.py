"""의료진/교수 관리 API"""
import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.auth.deps import get_current_user, get_my_team_id
from app.models.connection import get_db
from app.models.database import (
    Doctor, Hospital, DoctorSchedule, DoctorDateSchedule, User,
    UserDoctorGrade, UserDoctorMemo, VisitLog,
)
from app.schemas.schemas import (
    DoctorBase, DoctorResponse, DoctorWithSchedule,
    DoctorUpdate, DoctorScheduleCreate, DoctorDateScheduleCreate,
    VisitLogCreate, VisitLogResponse,
)

router = APIRouter(prefix="/api/doctors", tags=["의료진 관리"])


# ─────────── 사용자별 등급/메모 헬퍼 ───────────

async def _load_user_doctor_grades(
    db: AsyncSession, user_id: int, doctor_ids: Optional[list[int]] = None
) -> dict[int, str]:
    q = select(UserDoctorGrade).where(UserDoctorGrade.user_id == user_id)
    if doctor_ids:
        q = q.where(UserDoctorGrade.doctor_id.in_(doctor_ids))
    rows = (await db.execute(q)).scalars().all()
    return {r.doctor_id: r.grade for r in rows}


async def _load_user_doctor_memos(
    db: AsyncSession, user_id: int, doctor_ids: Optional[list[int]] = None
) -> dict[int, str]:
    q = select(UserDoctorMemo).where(UserDoctorMemo.user_id == user_id)
    if doctor_ids:
        q = q.where(UserDoctorMemo.doctor_id.in_(doctor_ids))
    rows = (await db.execute(q)).scalars().all()
    return {r.doctor_id: (r.memo or "") for r in rows}


async def _upsert_user_grade(
    db: AsyncSession, user_id: int, doctor_id: int, grade: Optional[str]
):
    """grade 가 None/빈 문자면 row 삭제 (등급 해제). 값 있으면 upsert."""
    existing = (await db.execute(
        select(UserDoctorGrade).where(
            UserDoctorGrade.user_id == user_id,
            UserDoctorGrade.doctor_id == doctor_id,
        )
    )).scalar_one_or_none()
    if not grade:
        if existing:
            await db.delete(existing)
        return
    if existing:
        existing.grade = grade
    else:
        db.add(UserDoctorGrade(user_id=user_id, doctor_id=doctor_id, grade=grade))


async def _upsert_user_memo(
    db: AsyncSession, user_id: int, doctor_id: int, memo: Optional[str]
):
    """memo 가 None/빈 문자면 row 삭제. 있으면 upsert."""
    existing = (await db.execute(
        select(UserDoctorMemo).where(
            UserDoctorMemo.user_id == user_id,
            UserDoctorMemo.doctor_id == doctor_id,
        )
    )).scalar_one_or_none()
    if not memo:
        if existing:
            await db.delete(existing)
        return
    if existing:
        existing.memo = memo
    else:
        db.add(UserDoctorMemo(user_id=user_id, doctor_id=doctor_id, memo=memo))


# 슬롯 → 기본 시간 매핑 (사용자 입력 누락 시 폴백)
_SLOT_DEFAULT_TIMES = {
    "morning": ("09:00", "12:00"),
    "afternoon": ("13:00", "17:00"),
    "evening": ("18:00", "21:00"),
}


def _doctor_to_response_dict(
    doctor: Doctor,
    *,
    hospital_name: str | None = None,
    user_grade: Optional[str] = None,
    user_memo: Optional[str] = None,
) -> dict:
    """Doctor → DoctorResponse dict + hospital_name + linked record 정보 합성.

    visit_grade / memo 는 사용자별 분리 (UserDoctorGrade / UserDoctorMemo) 로
    이동했으므로, 호출자가 user_grade / user_memo 를 미리 조회해 주입한다.
    Doctor 테이블의 visit_grade / memo 컬럼은 폐기 예정 (1.x DROP).
    """
    base = DoctorResponse.model_validate(doctor).model_dump()
    base["visit_grade"] = user_grade
    base["memo"] = user_memo
    base["hospital_name"] = hospital_name if hospital_name is not None else (
        doctor.hospital.name if doctor.hospital else None
    )
    base["hospital_source"] = doctor.hospital.source if doctor.hospital else None

    # 최근 방문일 — visit_logs 가 selectinload 으로 로딩된 경우만 계산 (N+1 회피)
    try:
        visit_dates = [v.visit_date for v in doctor.visit_logs if v.visit_date]
        base["last_visit_date"] = max(visit_dates).isoformat() if visit_dates else None
    except Exception:
        base["last_visit_date"] = None

    # linked_doctor 가 있고 이미 로딩됐으면 정보 합성
    linked = None
    try:
        linked = doctor.linked_doctor  # relationship lazy access
    except Exception:
        linked = None
    if linked is not None:
        base["linked_doctor_name"] = linked.name
        base["linked_doctor_department"] = linked.department
        try:
            base["linked_hospital_name"] = linked.hospital.name if linked.hospital else None
        except Exception:
            base["linked_hospital_name"] = None
        base["linked_doctor_is_active"] = bool(linked.is_active)
    else:
        base["linked_doctor_name"] = None
        base["linked_doctor_department"] = None
        base["linked_hospital_name"] = None
        base["linked_doctor_is_active"] = None
    return base


@router.get("/", summary="의료진 목록")
async def list_doctors(
    hospital_id: int = None,
    department: str = None,
    visit_grade: str = None,
    my_only: bool = False,
    status: str = "active",  # "active" (기본) | "inactive" | "all"
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """등록된 의료진 목록을 조회합니다.

    - my_only=true: 내 교수만 (UserDoctorGrade A/B, 현재 사용자 한정)
    - visit_grade=A|B|C: 해당 등급으로 매긴 의사만 (현재 사용자 한정)
    - status='active': 활성 의사만 (기본). status='inactive': 비활성만. 'all': 모두.
    """
    query = select(Doctor).options(
        selectinload(Doctor.hospital),
        selectinload(Doctor.linked_doctor).selectinload(Doctor.hospital),
        selectinload(Doctor.visit_logs),
    )
    if status == "active":
        query = query.where(Doctor.is_active == True)
    elif status == "inactive":
        query = query.where(Doctor.is_active == False)
    if my_only:
        sub = select(UserDoctorGrade.doctor_id).where(
            UserDoctorGrade.user_id == user.id,
            UserDoctorGrade.grade.in_(["A", "B"]),
        )
        query = query.where(Doctor.id.in_(sub))
    if visit_grade:
        sub = select(UserDoctorGrade.doctor_id).where(
            UserDoctorGrade.user_id == user.id,
            UserDoctorGrade.grade == visit_grade,
        )
        query = query.where(Doctor.id.in_(sub))
    if hospital_id:
        query = query.where(Doctor.hospital_id == hospital_id)
    if department:
        query = query.where(Doctor.department == department)

    result = await db.execute(query)
    doctors = result.scalars().all()
    doctor_ids = [d.id for d in doctors]
    grade_map = await _load_user_doctor_grades(db, user.id, doctor_ids)
    memo_map = await _load_user_doctor_memos(db, user.id, doctor_ids)
    return [
        _doctor_to_response_dict(
            d,
            user_grade=grade_map.get(d.id),
            user_memo=memo_map.get(d.id),
        )
        for d in doctors
    ]


@router.get("/{doctor_id}", summary="의료진 상세 (일정 포함)")
async def get_doctor(
    doctor_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """의료진 상세 정보와 진료일정을 조회합니다."""
    query = (
        select(Doctor)
        .options(
            selectinload(Doctor.schedules),
            selectinload(Doctor.date_schedules),
            selectinload(Doctor.hospital),
            selectinload(Doctor.linked_doctor).selectinload(Doctor.hospital),
            selectinload(Doctor.visit_logs),
        )
        .where(Doctor.id == doctor_id)
    )
    result = await db.execute(query)
    doctor = result.scalar_one_or_none()
    if not doctor:
        raise HTTPException(status_code=404, detail="의료진을 찾을 수 없습니다.")

    # 날짜별 스케줄: 오늘 이후만
    today_str = datetime.now().strftime("%Y-%m-%d")
    date_scheds = [
        {"id": ds.id, "schedule_date": ds.schedule_date, "time_slot": ds.time_slot,
         "start_time": ds.start_time, "end_time": ds.end_time,
         "location": ds.location, "status": ds.status}
        for ds in doctor.date_schedules
        if ds.schedule_date >= today_str
    ]
    date_scheds.sort(key=lambda x: (x["schedule_date"], x["time_slot"]))

    grade_map = await _load_user_doctor_grades(db, user.id, [doctor.id])
    memo_map = await _load_user_doctor_memos(db, user.id, [doctor.id])
    response = _doctor_to_response_dict(
        doctor,
        user_grade=grade_map.get(doctor.id),
        user_memo=memo_map.get(doctor.id),
    )
    response["schedules"] = [s.__dict__ for s in doctor.schedules if s.is_active]
    response["date_schedules"] = date_scheds
    return response


@router.post("/", summary="의료진 등록")
async def create_doctor(
    data: DoctorBase,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """담당 의료진을 등록합니다 (글로벌 마스터). source 미지정 시 'manual',
    external_id 미지정 시 MANUAL-{8자리} 자동 발급.

    payload 의 visit_grade / memo 가 있으면 등록자(user) 의 사용자별 데이터로
    분리 저장."""
    payload = data.model_dump(exclude_unset=True)
    user_grade = payload.pop("visit_grade", None)
    user_memo = payload.pop("memo", None)
    if not payload.get("source"):
        payload["source"] = "manual"
    if payload["source"] == "manual" and not payload.get("external_id"):
        payload["external_id"] = f"MANUAL-{uuid.uuid4().hex[:8].upper()}"
    doctor = Doctor(**payload)
    db.add(doctor)
    await db.commit()
    await db.refresh(doctor)
    if user_grade:
        await _upsert_user_grade(db, user.id, doctor.id, user_grade)
    if user_memo:
        await _upsert_user_memo(db, user.id, doctor.id, user_memo)
    if user_grade or user_memo:
        await db.commit()
    return _doctor_to_response_dict(
        doctor, user_grade=user_grade, user_memo=user_memo,
    )


@router.patch("/{doctor_id}", summary="의료진 정보 수정")
async def update_doctor(
    doctor_id: int,
    data: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """의료진 정보를 수정합니다.

    - visit_grade / memo: 사용자별 (UserDoctorGrade / UserDoctorMemo upsert)
    - is_active / department / position / deactivated_reason / linked_doctor_id:
      글로벌 마스터 변경 (모든 사용자에게 영향)

    is_active=False 로 전환 시 deactivated_at 자동 설정. True 복귀 시 자동 클리어.
    """
    query = select(Doctor).where(Doctor.id == doctor_id)
    result = await db.execute(query)
    doctor = result.scalar_one_or_none()
    if not doctor:
        raise HTTPException(status_code=404, detail="의료진을 찾을 수 없습니다.")

    # 사용자별 컬럼: UserDoctorGrade / UserDoctorMemo 로 분리
    if "visit_grade" in data:
        await _upsert_user_grade(db, user.id, doctor_id, data.pop("visit_grade"))
    if "memo" in data:
        await _upsert_user_memo(db, user.id, doctor_id, data.pop("memo"))

    allowed_fields = {
        "is_active", "department", "position",
        "deactivated_reason", "linked_doctor_id",
    }
    was_active = doctor.is_active
    old_link_id = doctor.linked_doctor_id
    new_link_id_in_payload = "linked_doctor_id" in data

    for key, value in data.items():
        if key in allowed_fields:
            setattr(doctor, key, value)

    # is_active 전환에 따라 deactivated_* 자동 관리
    if was_active and doctor.is_active is False:
        doctor.deactivated_at = datetime.utcnow()
        if not doctor.deactivated_reason:
            doctor.deactivated_reason = "manual"
    elif doctor.is_active is True:
        doctor.deactivated_at = None
        doctor.deactivated_reason = None

    # linked_doctor_id 양방향 처리:
    # - 새 상대 record 도 자기를 가리키게 set (이미 가리키고 있으면 그대로)
    # - 옛 상대 record 가 자기를 가리키고 있었으면 unset
    if new_link_id_in_payload:
        new_link_id = doctor.linked_doctor_id
        if old_link_id and old_link_id != new_link_id:
            old_target = (await db.execute(
                select(Doctor).where(Doctor.id == old_link_id)
            )).scalar_one_or_none()
            if old_target and old_target.linked_doctor_id == doctor.id:
                old_target.linked_doctor_id = None
        if new_link_id and new_link_id != doctor.id:
            new_target = (await db.execute(
                select(Doctor).where(Doctor.id == new_link_id)
            )).scalar_one_or_none()
            if new_target and new_target.linked_doctor_id != doctor.id:
                new_target.linked_doctor_id = doctor.id

    await db.commit()
    await db.refresh(doctor)
    grade_map = await _load_user_doctor_grades(db, user.id, [doctor_id])
    memo_map = await _load_user_doctor_memos(db, user.id, [doctor_id])
    return _doctor_to_response_dict(
        doctor,
        user_grade=grade_map.get(doctor_id),
        user_memo=memo_map.get(doctor_id),
    )


# ─── 수동 진료 일정 입력 ───
@router.post("/{doctor_id}/schedules", summary="진료시간(주간) 수동 입력 — 기존 수동 일정 대체")
async def replace_manual_schedules(
    doctor_id: int,
    items: list[DoctorScheduleCreate],
    db: AsyncSession = Depends(get_db),
):
    """수동 입력 주간 진료시간. 기존 source='manual' 행은 모두 교체.
    크롤러가 등록한 행(source='crawler')은 건드리지 않는다.
    """
    doctor = (await db.execute(select(Doctor).where(Doctor.id == doctor_id))).scalar_one_or_none()
    if not doctor:
        raise HTTPException(404, "의료진을 찾을 수 없습니다.")

    # 기존 수동 행 삭제
    existing = (await db.execute(
        select(DoctorSchedule).where(
            DoctorSchedule.doctor_id == doctor_id,
            DoctorSchedule.source == "manual",
        )
    )).scalars().all()
    for row in existing:
        await db.delete(row)

    saved: list[DoctorSchedule] = []
    for it in items:
        start = it.start_time
        end = it.end_time
        if not start or not end:
            d_start, d_end = _SLOT_DEFAULT_TIMES.get(it.time_slot, ("", ""))
            start = start or d_start
            end = end or d_end
        row = DoctorSchedule(
            doctor_id=doctor_id,
            day_of_week=it.day_of_week,
            time_slot=it.time_slot,
            start_time=start,
            end_time=end,
            location=it.location or "",
            source="manual",
            crawled_at=datetime.utcnow(),
        )
        db.add(row)
        saved.append(row)

    await db.commit()
    return {"replaced": len(existing), "saved": len(saved)}


@router.post("/{doctor_id}/date-schedules", summary="날짜별 진료시간 수동 입력 — 같은 날짜 수동 행 대체")
async def add_manual_date_schedules(
    doctor_id: int,
    items: list[DoctorDateScheduleCreate],
    db: AsyncSession = Depends(get_db),
):
    """특정 날짜의 진료시간을 수동 추가. 같은 날짜의 source='manual' 기존 행은 교체."""
    doctor = (await db.execute(select(Doctor).where(Doctor.id == doctor_id))).scalar_one_or_none()
    if not doctor:
        raise HTTPException(404, "의료진을 찾을 수 없습니다.")

    target_dates = {it.schedule_date for it in items}

    # 같은 날짜의 기존 manual 행 삭제
    existing = (await db.execute(
        select(DoctorDateSchedule).where(
            DoctorDateSchedule.doctor_id == doctor_id,
            DoctorDateSchedule.source == "manual",
            DoctorDateSchedule.schedule_date.in_(target_dates),
        )
    )).scalars().all()
    for row in existing:
        await db.delete(row)

    saved: list[DoctorDateSchedule] = []
    for it in items:
        start = it.start_time
        end = it.end_time
        if not start or not end:
            d_start, d_end = _SLOT_DEFAULT_TIMES.get(it.time_slot, ("", ""))
            start = start or d_start
            end = end or d_end
        row = DoctorDateSchedule(
            doctor_id=doctor_id,
            schedule_date=it.schedule_date,
            time_slot=it.time_slot,
            start_time=start,
            end_time=end,
            location=it.location or "",
            status=it.status or "진료",
            source="manual",
            crawled_at=datetime.utcnow(),
        )
        db.add(row)
        saved.append(row)

    await db.commit()
    return {"replaced": len(existing), "saved": len(saved)}


@router.delete("/{doctor_id}/schedules/{schedule_id}", summary="수동 진료시간 행 삭제")
async def delete_manual_schedule(
    doctor_id: int,
    schedule_id: int,
    db: AsyncSession = Depends(get_db),
):
    """수동(source='manual') 진료시간 행만 삭제 가능. 크롤러 행은 보호."""
    row = (await db.execute(
        select(DoctorSchedule).where(
            DoctorSchedule.id == schedule_id,
            DoctorSchedule.doctor_id == doctor_id,
        )
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "진료시간을 찾을 수 없습니다.")
    if row.source != "manual":
        raise HTTPException(400, "크롤러로 수집된 진료시간은 삭제할 수 없습니다.")
    await db.delete(row)
    await db.commit()
    return {"deleted": schedule_id}


# --- 방문 기록 ---
@router.post("/{doctor_id}/visits", summary="방문 기록 등록")
async def create_visit_log(
    doctor_id: int,
    data: VisitLogCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """방문 기록을 등록합니다. doctor/hospital snapshot 도 함께 저장.
    visibility: 'private'(기본) | 'team'. 'team' 시 recipient_user_ids 필수."""
    from app.api.visits import _broadcast_visit_shared, _validate_recipients, _apply_recipients

    doctor = (await db.execute(
        select(Doctor).options(selectinload(Doctor.hospital)).where(Doctor.id == doctor_id)
    )).scalar_one_or_none()
    if not doctor:
        raise HTTPException(404, "의료진을 찾을 수 없습니다.")

    payload = data.model_dump(exclude={"doctor_id"})
    visibility = payload.pop("visibility", None) or "private"
    payload.pop("recipient_user_ids", None)  # 별도 처리
    if visibility not in ("private", "team"):
        raise HTTPException(400, "visibility 는 'private' 또는 'team' 이어야 합니다.")
    recipient_ids: list[int] = []
    if visibility == "team":
        recipient_ids = await _validate_recipients(db, user, data.recipient_user_ids)

    visit = VisitLog(
        user_id=user.id,
        doctor_id=doctor_id,
        **payload,
        visibility=visibility,
        doctor_name_snapshot=doctor.name,
        doctor_dept_snapshot=doctor.department,
        hospital_name_snapshot=doctor.hospital.name if doctor.hospital else None,
    )
    db.add(visit)
    await db.flush()
    if recipient_ids:
        await _apply_recipients(db, visit, recipient_ids)
    await db.commit()
    await db.refresh(visit)
    if visibility == "team":
        try:
            await _broadcast_visit_shared(db, visit, user, action="created", recipient_ids=recipient_ids)
        except Exception:
            pass
    return VisitLogResponse.model_validate(visit)


@router.get("/{doctor_id}/visits", summary="방문 기록 조회")
async def list_visit_logs(
    doctor_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """특정 의료진의 방문 기록을 조회합니다 (현재 사용자 한정)."""
    query = (
        select(VisitLog)
        .where(VisitLog.doctor_id == doctor_id, VisitLog.user_id == user.id)
        .order_by(VisitLog.visit_date.desc())
    )
    result = await db.execute(query)
    return [VisitLogResponse.model_validate(v) for v in result.scalars().all()]


@router.patch("/{doctor_id}/visits/{visit_id}", summary="방문 기록 수정")
async def update_visit_log(
    doctor_id: int,
    visit_id: int,
    data: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """방문 기록 수정. owner 는 전체 필드, recipient 는 결과 입력 필드만 수정 가능."""
    from app.api.visits import (
        _broadcast_visit_shared, _broadcast_visit_removed, _broadcast_visit_diff,
        _validate_recipients, _apply_recipients,
    )
    from app.api.dashboard import _visit_user_filter

    user_filter = await _visit_user_filter(db, user.id)
    visit = (await db.execute(
        select(VisitLog).where(
            VisitLog.id == visit_id,
            VisitLog.doctor_id == doctor_id,
            user_filter,
        )
    )).scalar_one_or_none()
    if not visit:
        raise HTTPException(404, "방문 기록을 찾을 수 없습니다.")

    is_owner = visit.user_id == user.id

    # recipient 는 결과 입력 필드만 수정 가능 — visibility/recipient_user_ids/날짜/제목/사전메모 차단
    if not is_owner:
        recipient_allowed = {"status", "post_notes", "next_action", "product"}
        for key, value in data.items():
            if key not in recipient_allowed:
                continue
            setattr(visit, key, value)
        await db.commit()
        await db.refresh(visit)
        return VisitLogResponse.model_validate(visit)

    # owner 경로 — 기존 로직
    prev_visibility = visit.visibility or "private"
    prev_recipient_ids = [u.id for u in (visit.recipients or [])]
    allowed = {"status", "product", "notes", "post_notes", "next_action", "visit_date", "visibility"}
    if "visibility" in data:
        v = data["visibility"]
        if v not in ("private", "team"):
            raise HTTPException(400, "visibility 는 'private' 또는 'team' 이어야 합니다.")
        if v == "team":
            my_team_id = await get_my_team_id(db, user.id)
            if not my_team_id:
                raise HTTPException(400, "팀에 속해있지 않아 팀 공유로 변경할 수 없습니다.")
    for key, value in data.items():
        if key not in allowed:
            continue
        if key == "visit_date" and isinstance(value, str):
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        setattr(visit, key, value)

    new_visibility = visit.visibility or "private"
    new_recipient_ids = list(prev_recipient_ids)
    recipients_provided = "recipient_user_ids" in data

    if new_visibility == "team":
        if recipients_provided:
            new_recipient_ids = await _validate_recipients(db, user, data.get("recipient_user_ids"))
            await _apply_recipients(db, visit, new_recipient_ids)
        elif prev_visibility != "team":
            raise HTTPException(400, "팀 공유로 변경할 때는 recipient_user_ids 가 필요합니다.")
    elif prev_visibility == "team":
        await _apply_recipients(db, visit, [])
        new_recipient_ids = []

    await db.commit()
    await db.refresh(visit)

    try:
        if prev_visibility != "team" and new_visibility == "team":
            await _broadcast_visit_shared(db, visit, user, action="updated_to_team", recipient_ids=new_recipient_ids)
        elif prev_visibility == "team" and new_visibility != "team":
            await _broadcast_visit_removed(db, visit, user, prev_recipient_ids)
        elif prev_visibility == "team" and new_visibility == "team":
            await _broadcast_visit_diff(db, visit, user, prev_recipient_ids, new_recipient_ids)
    except Exception:
        pass
    return VisitLogResponse.model_validate(visit)


@router.delete("/{doctor_id}/visits/{visit_id}", summary="예정 방문 취소")
async def delete_visit_log(
    doctor_id: int,
    visit_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """예정된 방문만 삭제 가능. 이미 실행된 기록은 보호."""
    from app.api.visits import _broadcast_visit_removed

    visit = (await db.execute(
        select(VisitLog).where(
            VisitLog.id == visit_id,
            VisitLog.doctor_id == doctor_id,
            VisitLog.user_id == user.id,
        )
    )).scalar_one_or_none()
    if not visit:
        raise HTTPException(404, "방문 기록을 찾을 수 없습니다.")
    if visit.status != "예정":
        raise HTTPException(400, "실행된 방문 기록은 삭제할 수 없습니다.")

    is_team = (visit.visibility or "private") == "team"
    old_ids = [u.id for u in (visit.recipients or [])] if is_team else []

    await db.delete(visit)
    await db.commit()
    if is_team and old_ids:
        try:
            await _broadcast_visit_removed(db, visit, user, old_ids)
        except Exception:
            pass
    return {"deleted": visit_id}
