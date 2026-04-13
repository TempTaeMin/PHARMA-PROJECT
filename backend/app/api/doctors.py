"""의료진/교수 관리 API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.models.connection import get_db
from app.models.database import Doctor, Hospital, DoctorSchedule, DoctorDateSchedule, VisitLog
from app.schemas.schemas import (
    DoctorBase, DoctorResponse, DoctorWithSchedule,
    VisitLogCreate, VisitLogResponse,
)

router = APIRouter(prefix="/api/doctors", tags=["의료진 관리"])


@router.get("/", summary="의료진 목록")
async def list_doctors(
    hospital_id: int = None,
    department: str = None,
    visit_grade: str = None,
    my_only: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """등록된 의료진 목록을 조회합니다.
    my_only=true: 내 교수만 (visit_grade A/B)"""
    query = select(Doctor).options(selectinload(Doctor.hospital)).where(Doctor.is_active == True)
    if my_only:
        query = query.where(Doctor.visit_grade.in_(["A", "B"]))
    if hospital_id:
        query = query.where(Doctor.hospital_id == hospital_id)
    if department:
        query = query.where(Doctor.department == department)
    if visit_grade:
        query = query.where(Doctor.visit_grade == visit_grade)

    result = await db.execute(query)
    doctors = result.scalars().all()
    return [
        {
            **DoctorResponse.model_validate(d).model_dump(),
            "hospital_name": d.hospital.name if d.hospital else None,
        }
        for d in doctors
    ]


@router.get("/{doctor_id}", summary="의료진 상세 (일정 포함)")
async def get_doctor(doctor_id: int, db: AsyncSession = Depends(get_db)):
    """의료진 상세 정보와 진료일정을 조회합니다."""
    query = (
        select(Doctor)
        .options(
            selectinload(Doctor.schedules),
            selectinload(Doctor.date_schedules),
            selectinload(Doctor.hospital),
        )
        .where(Doctor.id == doctor_id)
    )
    result = await db.execute(query)
    doctor = result.scalar_one_or_none()
    if not doctor:
        raise HTTPException(status_code=404, detail="의료진을 찾을 수 없습니다.")

    # 날짜별 스케줄: 오늘 이후만
    from datetime import datetime
    today_str = datetime.now().strftime("%Y-%m-%d")
    date_scheds = [
        {"id": ds.id, "schedule_date": ds.schedule_date, "time_slot": ds.time_slot,
         "start_time": ds.start_time, "end_time": ds.end_time,
         "location": ds.location, "status": ds.status}
        for ds in doctor.date_schedules
        if ds.schedule_date >= today_str
    ]
    date_scheds.sort(key=lambda x: (x["schedule_date"], x["time_slot"]))

    return {
        **DoctorResponse.model_validate(doctor).model_dump(),
        "schedules": [s.__dict__ for s in doctor.schedules if s.is_active],
        "date_schedules": date_scheds,
        "hospital_name": doctor.hospital.name if doctor.hospital else None,
    }


@router.post("/", summary="의료진 등록", response_model=DoctorResponse)
async def create_doctor(data: DoctorBase, db: AsyncSession = Depends(get_db)):
    """담당 의료진을 등록합니다."""
    doctor = Doctor(**data.model_dump())
    db.add(doctor)
    await db.commit()
    await db.refresh(doctor)
    return doctor


@router.patch("/{doctor_id}", summary="의료진 정보 수정")
async def update_doctor(
    doctor_id: int, data: dict, db: AsyncSession = Depends(get_db)
):
    """의료진 정보를 수정합니다 (방문등급, 메모 등)."""
    query = select(Doctor).where(Doctor.id == doctor_id)
    result = await db.execute(query)
    doctor = result.scalar_one_or_none()
    if not doctor:
        raise HTTPException(status_code=404, detail="의료진을 찾을 수 없습니다.")

    allowed_fields = {"visit_grade", "memo", "is_active", "department", "position"}
    for key, value in data.items():
        if key in allowed_fields:
            setattr(doctor, key, value)

    await db.commit()
    await db.refresh(doctor)
    return DoctorResponse.model_validate(doctor)


# --- 방문 기록 ---
@router.post("/{doctor_id}/visits", summary="방문 기록 등록")
async def create_visit_log(
    doctor_id: int, data: VisitLogCreate, db: AsyncSession = Depends(get_db)
):
    """방문 기록을 등록합니다."""
    visit = VisitLog(doctor_id=doctor_id, **data.model_dump(exclude={"doctor_id"}))
    db.add(visit)
    await db.commit()
    await db.refresh(visit)
    return VisitLogResponse.model_validate(visit)


@router.get("/{doctor_id}/visits", summary="방문 기록 조회")
async def list_visit_logs(doctor_id: int, db: AsyncSession = Depends(get_db)):
    """특정 의료진의 방문 기록을 조회합니다."""
    query = (
        select(VisitLog)
        .where(VisitLog.doctor_id == doctor_id)
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
):
    """방문 기록 수정. 예정(계획) → 실행 결과 전환에도 사용."""
    visit = (await db.execute(
        select(VisitLog).where(VisitLog.id == visit_id, VisitLog.doctor_id == doctor_id)
    )).scalar_one_or_none()
    if not visit:
        raise HTTPException(404, "방문 기록을 찾을 수 없습니다.")

    allowed = {"status", "product", "notes", "next_action", "visit_date"}
    for key, value in data.items():
        if key not in allowed:
            continue
        if key == "visit_date" and isinstance(value, str):
            from datetime import datetime as _dt
            value = _dt.fromisoformat(value.replace("Z", "+00:00"))
        setattr(visit, key, value)

    await db.commit()
    await db.refresh(visit)
    return VisitLogResponse.model_validate(visit)


@router.delete("/{doctor_id}/visits/{visit_id}", summary="예정 방문 취소")
async def delete_visit_log(
    doctor_id: int,
    visit_id: int,
    db: AsyncSession = Depends(get_db),
):
    """예정된 방문만 삭제 가능. 이미 실행된 기록은 보호."""
    visit = (await db.execute(
        select(VisitLog).where(VisitLog.id == visit_id, VisitLog.doctor_id == doctor_id)
    )).scalar_one_or_none()
    if not visit:
        raise HTTPException(404, "방문 기록을 찾을 수 없습니다.")
    if visit.status != "예정":
        raise HTTPException(400, "실행된 방문 기록은 삭제할 수 없습니다.")

    await db.delete(visit)
    await db.commit()
    return {"deleted": visit_id}
