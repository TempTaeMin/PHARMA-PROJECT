"""크롤링 관련 API 엔드포인트"""
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.crawlers.factory import get_crawler, list_supported_hospitals
from app.models.connection import get_db
from app.models.database import Hospital, Doctor, DoctorSchedule, CrawlLog
from app.services.crawl_service import crawl_my_doctors

router = APIRouter(prefix="/api/crawl", tags=["크롤링"])


@router.get("/hospitals", summary="지원 병원 목록")
async def get_supported_hospitals():
    return {"hospitals": list_supported_hospitals()}


@router.get("/departments/{hospital_code}", summary="진료과 목록")
async def get_departments(hospital_code: str):
    try:
        crawler = get_crawler(hospital_code)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    departments = await crawler.get_departments()
    return {"hospital_code": hospital_code, "departments": departments}


@router.get("/browse/{hospital_code}", summary="교수 탐색 (DB 조회)")
async def browse_doctors(
    hospital_code: str,
    search: str = Query("", description="이름/진료과 검색"),
    department: str = Query("", description="진료과 필터"),
    db: AsyncSession = Depends(get_db),
):
    """DB에 저장된 교수 목록을 조회합니다. 이름/진료과 검색 지원."""
    # 병원 찾기
    result = await db.execute(select(Hospital).where(Hospital.code == hospital_code))
    hospital = result.scalar_one_or_none()
    if not hospital:
        raise HTTPException(status_code=404, detail=f"병원 코드 {hospital_code} 없음")

    query = select(Doctor).where(
        Doctor.hospital_id == hospital.id,
        Doctor.is_active == True,
    )
    if search:
        query = query.where(
            (Doctor.name.contains(search)) | (Doctor.department.contains(search))
        )
    if department:
        query = query.where(Doctor.department == department)

    query = query.order_by(Doctor.department, Doctor.name)
    result = await db.execute(query)
    doctors = result.scalars().all()

    # 마지막 크롤링 시간
    log_result = await db.execute(
        select(CrawlLog)
        .where(CrawlLog.hospital_code == hospital_code, CrawlLog.status == "success")
        .order_by(CrawlLog.started_at.desc())
        .limit(1)
    )
    last_log = log_result.scalar_one_or_none()

    return {
        "hospital_code": hospital_code,
        "hospital_name": hospital.name,
        "doctors_count": len(doctors),
        "last_crawled": last_log.started_at.isoformat() if last_log else None,
        "doctors": [
            {
                "id": d.id,
                "name": d.name,
                "department": d.department,
                "position": d.position or "",
                "specialty": d.specialty or "",
                "external_id": d.external_id or "",
                "profile_url": d.profile_url or "",
                "visit_grade": d.visit_grade,
                "notes": d.notes or "",
            }
            for d in doctors
        ],
    }


@router.post("/sync/{hospital_code}", summary="병원 교수 목록 크롤링 → DB 저장")
async def sync_hospital(
    hospital_code: str,
    department: str = Query("", description="특정 진료과만"),
    db: AsyncSession = Depends(get_db),
):
    """병원 사이트에서 교수 목록을 크롤링하여 DB에 저장합니다.
    이미 있는 교수는 업데이트, 없으면 신규 추가 (visit_grade=None, 탐색용)."""
    # 병원 찾기
    result = await db.execute(select(Hospital).where(Hospital.code == hospital_code))
    hospital = result.scalar_one_or_none()
    if not hospital:
        raise HTTPException(status_code=404, detail=f"병원 코드 {hospital_code} 없음")

    try:
        crawler = get_crawler(hospital_code)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # 크롤링
    doc_list = await crawler.crawl_doctor_list(department=department or None)

    created = 0
    updated = 0

    for d in doc_list:
        ext_id = d.get("external_id") or d.get("staff_id", "")
        name = d.get("name", "")

        # 기존 교수 찾기 (external_id 또는 이름+진료과)
        existing = None
        if ext_id:
            r = await db.execute(
                select(Doctor).where(
                    Doctor.hospital_id == hospital.id,
                    Doctor.external_id == ext_id,
                )
            )
            existing = r.scalar_one_or_none()

        if not existing and name:
            r = await db.execute(
                select(Doctor).where(
                    Doctor.hospital_id == hospital.id,
                    Doctor.name == name,
                    Doctor.department == d.get("department", ""),
                )
            )
            existing = r.scalar_one_or_none()

        if existing:
            # 업데이트 (visit_grade는 건드리지 않음 - 내 교수 등급 보존)
            if d.get("specialty"):
                existing.specialty = d["specialty"]
            if d.get("profile_url"):
                existing.profile_url = d["profile_url"]
            if ext_id:
                existing.external_id = ext_id
            if d.get("notes"):
                existing.notes = d["notes"]
            existing.updated_at = datetime.utcnow()
            updated += 1
        else:
            # 신규 추가 (visit_grade=None → 탐색용)
            new_doc = Doctor(
                hospital_id=hospital.id,
                name=name,
                department=d.get("department", ""),
                position=d.get("position", ""),
                specialty=d.get("specialty", ""),
                profile_url=d.get("profile_url", ""),
                external_id=ext_id,
                visit_grade=None,
                notes=d.get("notes", ""),
            )
            db.add(new_doc)
            created += 1

    # 크롤링 로그
    log = CrawlLog(
        hospital_code=hospital_code,
        status="success",
        doctors_crawled=len(doc_list),
        started_at=datetime.utcnow(),
        finished_at=datetime.utcnow(),
    )
    db.add(log)

    await db.commit()

    return {
        "status": "success",
        "hospital_code": hospital_code,
        "total_crawled": len(doc_list),
        "created": created,
        "updated": updated,
    }


@router.post("/my-doctors", summary="내 교수 크롤링")
async def run_my_doctors_crawl(db: AsyncSession = Depends(get_db)):
    """등록된 내 교수들의 진료일정만 크롤링하고 DB를 업데이트합니다."""
    result = await crawl_my_doctors(db)
    return result


@router.get("/doctor/{hospital_code}/{staff_id}", summary="의료진 개별 크롤링 (진료시간)")
async def crawl_single_doctor(hospital_code: str, staff_id: str):
    """특정 교수의 진료시간표를 실시간 크롤링합니다."""
    try:
        crawler = get_crawler(hospital_code)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    result = await crawler.crawl_doctor_schedule(staff_id)
    return result


@router.post("/register-doctor", summary="내 교수로 등록")
async def register_doctor(
    data: dict,
    db: AsyncSession = Depends(get_db),
):
    """교수를 내 교수로 등록합니다 (visit_grade=B).
    진료시간 정보가 있으면 함께 저장합니다."""
    hospital_code = data.get("hospital_code")
    if not hospital_code:
        raise HTTPException(status_code=400, detail="hospital_code 필수")

    # 병원 찾기
    result = await db.execute(select(Hospital).where(Hospital.code == hospital_code))
    hospital = result.scalar_one_or_none()
    if not hospital:
        raise HTTPException(status_code=404, detail=f"병원 코드 {hospital_code} 없음")

    external_id = data.get("external_id", "")
    name = data.get("name", "")

    # 이미 등록된 교수인지 확인
    existing = None
    if external_id:
        r = await db.execute(
            select(Doctor).where(
                Doctor.hospital_id == hospital.id,
                Doctor.external_id == external_id,
            )
        )
        existing = r.scalar_one_or_none()

    if not existing and name:
        r = await db.execute(
            select(Doctor).where(
                Doctor.hospital_id == hospital.id,
                Doctor.name == name,
                Doctor.department == data.get("department", ""),
            )
        )
        existing = r.scalar_one_or_none()

    if existing:
        # visit_grade를 B로 승격 (이미 A면 유지)
        if existing.visit_grade not in ("A",):
            existing.visit_grade = "B"
        if data.get("specialty"):
            existing.specialty = data["specialty"]
        if data.get("position"):
            existing.position = data["position"]
        if data.get("profile_url"):
            existing.profile_url = data["profile_url"]

        # 일정 동기화
        schedules = data.get("schedules", [])
        if schedules:
            from app.services.crawl_service import _sync_schedules
            await _sync_schedules(db, existing.id, schedules)

        await db.commit()
        await db.refresh(existing)
        return {
            "status": "updated",
            "doctor_id": existing.id,
            "name": existing.name,
            "message": f"{existing.name} 교수를 내 교수로 등록했습니다",
        }

    # 신규 등록
    new_doc = Doctor(
        hospital_id=hospital.id,
        name=name,
        department=data.get("department", ""),
        position=data.get("position", ""),
        specialty=data.get("specialty", ""),
        profile_url=data.get("profile_url", ""),
        photo_url=data.get("photo_url", ""),
        external_id=external_id,
        visit_grade="B",
    )
    db.add(new_doc)
    await db.flush()

    # 일정 저장
    for s in data.get("schedules", []):
        time_ranges = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00"), "evening": ("18:00", "21:00")}
        slot = s.get("time_slot", "")
        start, end = time_ranges.get(slot, (s.get("start_time", ""), s.get("end_time", "")))
        schedule = DoctorSchedule(
            doctor_id=new_doc.id,
            day_of_week=s.get("day_of_week", 0),
            time_slot=slot,
            start_time=start,
            end_time=end,
            location=s.get("location", ""),
            crawled_at=datetime.utcnow(),
        )
        db.add(schedule)

    await db.commit()
    return {
        "status": "created",
        "doctor_id": new_doc.id,
        "name": new_doc.name,
        "message": f"{new_doc.name} 교수를 내 교수로 등록했습니다",
    }
