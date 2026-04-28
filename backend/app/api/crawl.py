"""크롤링 관련 API 엔드포인트"""
import re
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.crawlers.factory import get_crawler, list_supported_hospitals
from app.models.connection import get_db
from app.models.database import Hospital, Doctor, DoctorSchedule, DoctorDateSchedule, CrawlLog
from app.services.crawl_service import (
    crawl_my_doctors,
    _sync_schedules,
    _sync_date_schedules,
    _handle_missing_doctors,
    detect_transfer_candidate,
)

_DEPT_CLEAN_RE = re.compile(r"일반$")
def _clean_dept(name: str) -> str:
    return _DEPT_CLEAN_RE.sub("", name).strip() if name else name

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


@router.get("/search-doctors", summary="전 병원 교수 이름 검색")
async def search_doctors_global(
    q: str = Query("", description="교수 이름 검색어"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """모든 병원의 교수를 이름으로 검색합니다. 병원 선택 화면의 통합 검색용."""
    q = (q or "").strip()
    if not q:
        return {"query": q, "count": 0, "doctors": []}

    query = (
        select(Doctor, Hospital)
        .join(Hospital, Doctor.hospital_id == Hospital.id)
        .where(Doctor.is_active == True, Doctor.name.contains(q))
        .order_by(Hospital.name, Doctor.department, Doctor.name)
        .limit(limit)
    )
    rows = (await db.execute(query)).all()

    return {
        "query": q,
        "count": len(rows),
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
                "hospital_code": h.code,
                "hospital_name": h.name,
            }
            for d, h in rows
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

    # 크롤링 (스케줄 포함)
    # _fetch_all()은 스케줄 데이터를 포함하므로 이를 사용
    if hasattr(crawler, '_fetch_all'):
        raw_list = await crawler._fetch_all()
        if department:
            raw_list = [d for d in raw_list if d.get("department") == department]
    else:
        raw_list = await crawler.crawl_doctor_list(department=department or None)

    created = 0
    updated = 0
    schedules_saved = 0
    matched_ids: set[int] = set()

    for d in raw_list:
        ext_id = d.get("external_id") or d.get("staff_id", "")
        name = d.get("name", "")
        schedules = d.get("schedules", [])
        date_schedules = d.get("date_schedules", [])

        # 진료과명 정리
        if d.get("department"):
            d["department"] = _clean_dept(d["department"])

        # 기존 교수 찾기 (external_id 또는 이름+진료과). source='manual' 은 매칭 제외.
        existing = None
        if ext_id:
            r = await db.execute(
                select(Doctor).where(
                    Doctor.hospital_id == hospital.id,
                    Doctor.external_id == ext_id,
                    Doctor.source == "crawler",
                )
            )
            existing = r.scalar_one_or_none()

        if not existing and name:
            r = await db.execute(
                select(Doctor).where(
                    Doctor.hospital_id == hospital.id,
                    Doctor.name == name,
                    Doctor.department == d.get("department", ""),
                    Doctor.source == "crawler",
                )
            )
            existing = r.scalar_one_or_none()

        if existing:
            # 업데이트 (visit_grade는 건드리지 않음 - 내 교수 등급 보존)
            if name:
                existing.name = name
            if d.get("department"):
                existing.department = d["department"]
            if d.get("position"):
                existing.position = d["position"]
            if d.get("specialty"):
                existing.specialty = d["specialty"]
            if d.get("profile_url"):
                existing.profile_url = d["profile_url"]
            if ext_id:
                existing.external_id = ext_id
            if d.get("notes"):
                existing.notes = d["notes"]
            existing.is_active = True
            existing.updated_at = datetime.utcnow()
            # 누락 카운터 리셋 + auto-missing 자동 비활성화 해제
            if existing.missing_count:
                existing.missing_count = 0
            if existing.deactivated_reason == "auto-missing":
                existing.deactivated_reason = None
                existing.deactivated_at = None
            matched_ids.add(existing.id)
            updated += 1

            # 스케줄 동기화
            if schedules or hospital_code == "KBSMC":
                await _sync_schedules(db, existing.id, schedules)
                schedules_saved += len(schedules)
            if date_schedules:
                await _sync_date_schedules(db, existing.id, date_schedules)
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
                source="crawler",
            )
            db.add(new_doc)
            await db.flush()
            matched_ids.add(new_doc.id)
            created += 1

            # 이직 후보 감지 — 같은 이름+진료과 비활성 의사 있으면 알림
            await detect_transfer_candidate(db, new_doc)

            # 스케줄 저장
            if schedules:
                await _sync_schedules(db, new_doc.id, schedules)
                schedules_saved += len(schedules)
            if date_schedules:
                await _sync_date_schedules(db, new_doc.id, date_schedules)

    # 누락 의사 감지 + 자동 비활성/알림
    missing_summary = await _handle_missing_doctors(db, hospital, matched_ids)

    # 크롤링 로그
    log = CrawlLog(
        hospital_code=hospital_code,
        status="success",
        doctors_crawled=len(raw_list),
        started_at=datetime.utcnow(),
        finished_at=datetime.utcnow(),
    )
    db.add(log)

    await db.commit()

    return {
        "status": "success",
        "hospital_code": hospital_code,
        "total_crawled": len(raw_list),
        "created": created,
        "updated": updated,
        "schedules_saved": schedules_saved,
        **missing_summary,
    }


@router.post("/my-doctors", summary="내 교수 크롤링")
async def run_my_doctors_crawl(db: AsyncSession = Depends(get_db)):
    """등록된 내 교수들의 진료일정만 크롤링하고 DB를 업데이트합니다."""
    result = await crawl_my_doctors(db)
    return result


@router.get("/doctor/{hospital_code}/{staff_id:path}", summary="의료진 스케줄 조회 (DB 우선)")
async def crawl_single_doctor(
    hospital_code: str,
    staff_id: str,
    refresh: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """특정 교수의 진료시간표를 조회합니다.

    기본: DB에서 먼저 조회 (이미 sync 된 교수는 즉시 반환).
    refresh=true 또는 DB 미존재 시에만 크롤러로 실시간 조회합니다.
    """
    from sqlalchemy.orm import selectinload

    if not refresh:
        q = (
            select(Doctor)
            .options(
                selectinload(Doctor.schedules),
                selectinload(Doctor.date_schedules),
            )
            .join(Hospital, Doctor.hospital_id == Hospital.id)
            .where(
                Hospital.code == hospital_code,
                Doctor.external_id == staff_id,
                Doctor.is_active == True,
            )
        )
        doctor = (await db.execute(q)).scalar_one_or_none()

        if doctor and (doctor.schedules or doctor.date_schedules):
            today_str = datetime.now().strftime("%Y-%m-%d")
            schedules = [
                {
                    "day_of_week": s.day_of_week,
                    "time_slot": s.time_slot,
                    "start_time": s.start_time,
                    "end_time": s.end_time,
                    "location": s.location,
                }
                for s in doctor.schedules if s.is_active
            ]
            date_schedules = sorted(
                [
                    {
                        "schedule_date": ds.schedule_date,
                        "time_slot": ds.time_slot,
                        "start_time": ds.start_time,
                        "end_time": ds.end_time,
                        "location": ds.location,
                        "status": ds.status,
                    }
                    for ds in doctor.date_schedules
                    if ds.schedule_date >= today_str
                ],
                key=lambda x: (x["schedule_date"], x["time_slot"] or ""),
            )
            return {
                "staff_id": staff_id,
                "name": doctor.name or "",
                "department": doctor.department or "",
                "position": doctor.position or "",
                "specialty": doctor.specialty or "",
                "profile_url": doctor.profile_url or "",
                "photo_url": doctor.photo_url or "",
                "notes": doctor.notes or "",
                "schedules": schedules,
                "date_schedules": date_schedules,
                "source": "db",
            }

    try:
        crawler = get_crawler(hospital_code)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    result = await crawler.crawl_doctor_schedule(staff_id)
    if isinstance(result, dict):
        result.setdefault("source", "crawler")
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
    # 진료과명 정리
    if data.get("department"):
        data["department"] = _clean_dept(data["department"])

    # 스케줄이 없으면 자동으로 크롤링해서 가져오기
    schedules = data.get("schedules", [])
    date_schedules = data.get("date_schedules", [])
    if not schedules and external_id:
        try:
            crawler = get_crawler(hospital_code)
            crawled = await crawler.crawl_doctor_schedule(external_id)
            schedules = crawled.get("schedules", [])
            date_schedules = crawled.get("date_schedules", [])
            # 크롤링에서 추가 정보도 반영
            if not data.get("specialty") and crawled.get("specialty"):
                data["specialty"] = crawled["specialty"]
            if not data.get("position") and crawled.get("position"):
                data["position"] = crawled["position"]
        except Exception:
            pass

    # 이미 등록된 교수인지 확인 (수동 등록은 매칭 제외 — 별개 record 로 유지)
    existing = None
    if external_id:
        r = await db.execute(
            select(Doctor).where(
                Doctor.hospital_id == hospital.id,
                Doctor.external_id == external_id,
                Doctor.source == "crawler",
            )
        )
        existing = r.scalar_one_or_none()

    if not existing and name:
        r = await db.execute(
            select(Doctor).where(
                Doctor.hospital_id == hospital.id,
                Doctor.name == name,
                Doctor.department == data.get("department", ""),
                Doctor.source == "crawler",
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
        if schedules or date_schedules:
            from app.services.crawl_service import _sync_schedules, _sync_date_schedules
        if schedules or hospital_code == "KBSMC":
            await _sync_schedules(db, existing.id, schedules)
        if date_schedules:
            await _sync_date_schedules(db, existing.id, date_schedules)

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
    for s in schedules:
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

    # 날짜별 일정 저장
    for ds in date_schedules:
        date_sched = DoctorDateSchedule(
            doctor_id=new_doc.id,
            schedule_date=ds["schedule_date"],
            time_slot=ds.get("time_slot", ""),
            start_time=ds.get("start_time", ""),
            end_time=ds.get("end_time", ""),
            location=ds.get("location", ""),
            status=ds.get("status", "진료"),
            crawled_at=datetime.utcnow(),
        )
        db.add(date_sched)

    await db.commit()
    return {
        "status": "created",
        "doctor_id": new_doc.id,
        "name": new_doc.name,
        "message": f"{new_doc.name} 교수를 내 교수로 등록했습니다",
    }
