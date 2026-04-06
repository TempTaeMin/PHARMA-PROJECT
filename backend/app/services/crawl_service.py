"""크롤링 결과 → DB 저장 서비스

크롤링 결과를 받아서:
1. 신규 교수 → Doctor 테이블에 INSERT
2. 기존 교수 → 정보 UPDATE
3. 진료 일정 → DoctorSchedule UPSERT
4. 변경 감지 → ScheduleChange 기록
5. 크롤링 로그 → CrawlLog 기록
"""
import logging
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.database import Hospital, Doctor, DoctorSchedule, ScheduleChange, CrawlLog
from app.schemas.schemas import CrawlResult, CrawledDoctor

logger = logging.getLogger(__name__)


async def save_crawl_result(db: AsyncSession, crawl_result: CrawlResult) -> dict:
    """크롤링 결과를 DB에 저장하고 변경사항을 반환합니다."""

    # 병원 찾기
    hospital = await _get_hospital_by_code(db, crawl_result.hospital_code)
    if not hospital:
        logger.error(f"병원 코드 {crawl_result.hospital_code} 없음")
        return {"error": "병원 없음", "saved": 0, "updated": 0, "changes": 0}

    saved = 0
    updated = 0
    changes_detected = 0

    for crawled_doc in crawl_result.doctors:
        # 기존 교수 찾기 (external_id 또는 이름+진료과)
        existing = await _find_doctor(db, hospital.id, crawled_doc)

        if existing:
            # 기존 교수 업데이트
            _update_doctor_info(existing, crawled_doc)

            # 일정 변경 감지 + 업데이트
            ch = await _sync_schedules(db, existing.id, crawled_doc.schedules)
            changes_detected += ch
            updated += 1
        else:
            # 신규 교수 등록
            new_doc = Doctor(
                hospital_id=hospital.id,
                name=crawled_doc.name,
                department=crawled_doc.department,
                position=crawled_doc.position,
                specialty=crawled_doc.specialty,
                profile_url=crawled_doc.profile_url,
                photo_url=crawled_doc.photo_url,
                external_id=crawled_doc.external_id,
                visit_grade="B",  # 기본 등급
            )
            db.add(new_doc)
            await db.flush()

            # 일정 등록
            for s in crawled_doc.schedules:
                time_ranges = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00"), "evening": ("18:00", "21:00")}
                start, end = time_ranges.get(s.get("time_slot", ""), ("", ""))
                schedule = DoctorSchedule(
                    doctor_id=new_doc.id,
                    day_of_week=s["day_of_week"],
                    time_slot=s.get("time_slot", ""),
                    start_time=start,
                    end_time=end,
                    location=s.get("location", ""),
                )
                db.add(schedule)
            saved += 1

    # 크롤링 로그 저장
    crawl_log = CrawlLog(
        hospital_code=crawl_result.hospital_code,
        status=crawl_result.status,
        doctors_crawled=len(crawl_result.doctors),
        schedules_updated=updated,
        changes_detected=changes_detected,
        started_at=crawl_result.crawled_at,
        finished_at=datetime.utcnow(),
    )
    db.add(crawl_log)
    await db.commit()

    summary = {
        "hospital": hospital.name,
        "saved": saved,
        "updated": updated,
        "changes": changes_detected,
        "total_crawled": len(crawl_result.doctors),
    }
    logger.info(f"크롤링 결과 저장: {summary}")
    return summary


async def crawl_my_doctors(db: AsyncSession) -> dict:
    """등록된 '내 교수'들의 진료일정만 크롤링합니다."""
    from app.crawlers.factory import get_crawler

    # 내 교수만 (visit_grade A/B/C + external_id 있는 교수만 크롤링 가능)
    result = await db.execute(
        select(Doctor)
        .where(Doctor.is_active == True)
        .where(Doctor.visit_grade.in_(["A", "B", "C"]))
        .where(Doctor.external_id != None)
        .where(Doctor.external_id != "")
    )
    doctors = result.scalars().all()

    if not doctors:
        return {"message": "크롤링할 교수가 없습니다", "crawled": 0}

    # 병원별로 그룹핑
    hospital_ids = set(d.hospital_id for d in doctors)
    hospital_map = {}
    for hid in hospital_ids:
        h_result = await db.execute(select(Hospital).where(Hospital.id == hid))
        h = h_result.scalar_one_or_none()
        if h:
            hospital_map[hid] = h

    crawled = 0
    errors = []
    changes = 0
    DAY_NAMES = ["월", "화", "수", "목", "금", "토", "일"]
    SLOT_NAMES = {"morning": "오전", "afternoon": "오후", "evening": "야간"}

    for doc in doctors:
        hospital = hospital_map.get(doc.hospital_id)
        if not hospital or not hospital.code:
            continue

        try:
            crawler = get_crawler(hospital.code)
            detail = await crawler.crawl_doctor_schedule(doc.external_id)

            # 기본 정보 업데이트
            if detail.get("name") and not doc.name:
                doc.name = detail["name"]
            if detail.get("specialty"):
                doc.specialty = detail["specialty"]
            if detail.get("notes") is not None:
                doc.notes = detail["notes"]
            if detail.get("staff_id") and doc.external_id != detail["staff_id"]:
                doc.external_id = detail["staff_id"]

            # 일정 동기화
            ch = await _sync_schedules(db, doc.id, detail.get("schedules", []))
            changes += ch
            crawled += 1

            logger.info(f"[내 교수 크롤링] {doc.name} ({hospital.name}) - 일정 {len(detail.get('schedules', []))}개, 변경 {ch}건")

        except Exception as e:
            errors.append(f"{doc.name}: {str(e)}")
            logger.error(f"[내 교수 크롤링] {doc.name} 실패: {e}")

    await db.commit()

    return {
        "crawled": crawled,
        "total": len(doctors),
        "changes": changes,
        "errors": errors,
    }


async def crawl_department(db: AsyncSession, hospital_code: str, department: str) -> dict:
    """특정 병원의 특정 진료과를 크롤링하고 결과를 DB에 저장합니다."""
    from app.crawlers.factory import get_crawler

    try:
        crawler = get_crawler(hospital_code)
        result = await crawler.crawl_doctors(department=department)
        summary = await save_crawl_result(db, result)
        return summary
    except Exception as e:
        logger.error(f"진료과 크롤링 실패 [{hospital_code}/{department}]: {e}")
        return {"error": str(e)}


# ─── 내부 헬퍼 ───

async def _get_hospital_by_code(db: AsyncSession, code: str) -> Hospital | None:
    result = await db.execute(select(Hospital).where(Hospital.code == code))
    return result.scalar_one_or_none()


async def _find_doctor(db: AsyncSession, hospital_id: int, crawled: CrawledDoctor) -> Doctor | None:
    """external_id 또는 이름+진료과로 기존 교수 찾기"""
    if crawled.external_id:
        result = await db.execute(
            select(Doctor).where(
                Doctor.hospital_id == hospital_id,
                Doctor.external_id == crawled.external_id,
            )
        )
        doc = result.scalar_one_or_none()
        if doc:
            return doc

    # 이름 + 진료과로 폴백 검색
    if crawled.name:
        result = await db.execute(
            select(Doctor).where(
                Doctor.hospital_id == hospital_id,
                Doctor.name == crawled.name,
                Doctor.department == crawled.department,
            )
        )
        return result.scalar_one_or_none()

    return None


def _update_doctor_info(doctor: Doctor, crawled: CrawledDoctor):
    """교수 기본 정보 업데이트"""
    if crawled.position:
        doctor.position = crawled.position
    if crawled.specialty:
        doctor.specialty = crawled.specialty
    if crawled.profile_url:
        doctor.profile_url = crawled.profile_url
    if crawled.photo_url:
        doctor.photo_url = crawled.photo_url


async def _sync_schedules(db: AsyncSession, doctor_id: int, new_schedules: list[dict]) -> int:
    """진료 일정을 동기화하고 변경 건수를 반환합니다."""
    # 기존 일정 조회
    result = await db.execute(
        select(DoctorSchedule).where(
            DoctorSchedule.doctor_id == doctor_id,
            DoctorSchedule.is_active == True,
        )
    )
    existing = result.scalars().all()

    old_set = {(s.day_of_week, s.time_slot) for s in existing}
    new_set = {(s["day_of_week"], s.get("time_slot", "")) for s in new_schedules}

    changes = 0

    # 삭제된 일정
    for day, slot in (old_set - new_set):
        for s in existing:
            if s.day_of_week == day and s.time_slot == slot:
                s.is_active = False
                change = ScheduleChange(
                    doctor_id=doctor_id,
                    change_type="휴진",
                    original_day=day,
                    original_time_slot=slot,
                    reason="크롤링 감지: 일정 삭제",
                )
                db.add(change)
                changes += 1

    # 추가된 일정
    for day, slot in (new_set - old_set):
        sched_data = next((s for s in new_schedules if s["day_of_week"] == day and s.get("time_slot") == slot), {})
        time_ranges = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}
        start, end = time_ranges.get(slot, ("", ""))

        new_sched = DoctorSchedule(
            doctor_id=doctor_id,
            day_of_week=day,
            time_slot=slot,
            start_time=start,
            end_time=end,
            location=sched_data.get("location", ""),
            crawled_at=datetime.utcnow(),
        )
        db.add(new_sched)

        change = ScheduleChange(
            doctor_id=doctor_id,
            change_type="추가",
            new_day=day,
            new_time_slot=slot,
            reason="크롤링 감지: 일정 추가",
        )
        db.add(change)
        changes += 1

    # 기존 일정 location 업데이트
    for day, slot in (old_set & new_set):
        sched_data = next((s for s in new_schedules if s["day_of_week"] == day and s.get("time_slot") == slot), {})
        new_loc = sched_data.get("location", "")
        for s in existing:
            if s.day_of_week == day and s.time_slot == slot and s.location != new_loc:
                s.location = new_loc
                s.crawled_at = datetime.utcnow()

    return changes
