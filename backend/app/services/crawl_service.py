"""크롤링 결과 → DB 저장 서비스

크롤링 결과를 받아서:
1. 신규 교수 → Doctor 테이블에 INSERT
2. 기존 교수 → 정보 UPDATE
3. 진료 일정 → DoctorSchedule UPSERT
4. 변경 감지 → ScheduleChange 기록
5. 크롤링 로그 → CrawlLog 기록
6. 누락 의사 감지 → missing_count++, 2회 누락 시 자동 비활성/알림
"""
import logging
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.database import Hospital, Doctor, DoctorSchedule, DoctorDateSchedule, ScheduleChange, CrawlLog
from app.schemas.schemas import CrawlResult, CrawledDoctor

logger = logging.getLogger(__name__)


# 크롤링 결과에서 N회 연속 누락된 의사를 자동 비활성화하는 임계값.
# 1회 누락은 네트워크/페이지 오류로 흔히 발생하므로 보호.
MISSING_THRESHOLD = 2

# 진료과명 정리용 패턴: "가정의학과일반" → "가정의학과"
import re
_DEPT_CLEAN_RE = re.compile(r"일반$")


def _clean_department(name: str) -> str:
    """진료과명에서 불필요한 '일반' 접미사를 제거합니다."""
    if not name:
        return name
    return _DEPT_CLEAN_RE.sub("", name).strip()


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
    matched_ids: set[int] = set()

    for crawled_doc in crawl_result.doctors:
        # 진료과명 정리
        crawled_doc.department = _clean_department(crawled_doc.department)

        # 기존 교수 찾기 (external_id 또는 이름+진료과). source='manual' 은 매칭 제외.
        existing = await _find_doctor(db, hospital.id, crawled_doc)

        if existing:
            # 기존 교수 업데이트
            _update_doctor_info(existing, crawled_doc)
            # 누락 카운터 리셋 + 자동 비활성화 해제
            if existing.missing_count:
                existing.missing_count = 0
            if existing.deactivated_reason == "auto-missing" and not existing.is_active:
                existing.is_active = True
                existing.deactivated_reason = None
                existing.deactivated_at = None
            matched_ids.add(existing.id)

            # 일정 변경 감지 + 업데이트
            ch = await _sync_schedules(db, existing.id, crawled_doc.schedules)
            if crawled_doc.date_schedules:
                await _sync_date_schedules(db, existing.id, crawled_doc.date_schedules)
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
                source="crawler",
            )
            db.add(new_doc)
            await db.flush()
            matched_ids.add(new_doc.id)

            # 이직 후보 감지 — 같은 이름+진료과 비활성 의사 있으면 알림
            await detect_transfer_candidate(db, new_doc)

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
            # 날짜별 일정 저장
            for ds in crawled_doc.date_schedules:
                date_sched = DoctorDateSchedule(
                    doctor_id=new_doc.id,
                    schedule_date=ds["schedule_date"],
                    time_slot=ds.get("time_slot", ""),
                    start_time=ds.get("start_time", ""),
                    end_time=ds.get("end_time", ""),
                    location=ds.get("location", ""),
                    status=ds.get("status", "진료"),
                )
                db.add(date_sched)
            saved += 1

    # 누락 의사 감지 + 자동 비활성/알림
    missing_summary = await _handle_missing_doctors(db, hospital, matched_ids)

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
        **missing_summary,
    }
    logger.info(f"크롤링 결과 저장: {summary}")
    return summary


async def crawl_my_doctors(db: AsyncSession) -> dict:
    """등록된 '내 교수'들의 진료일정만 크롤링합니다."""
    from app.crawlers.factory import get_crawler

    # 내 교수만 (visit_grade A/B/C + external_id 있는 교수만 크롤링 가능).
    # 수동 등록 의사(source='manual')는 외부 크롤러로 가져올 수 없으므로 제외.
    result = await db.execute(
        select(Doctor)
        .where(Doctor.is_active == True)
        .where(Doctor.source == "crawler")
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
            if detail.get("date_schedules"):
                await _sync_date_schedules(db, doc.id, detail["date_schedules"])
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
    """external_id 또는 이름+진료과로 기존 교수 찾기.

    source='manual' 의사는 크롤러 매칭 대상에서 제외 — 수동 입력 보호.
    """
    if crawled.external_id:
        result = await db.execute(
            select(Doctor).where(
                Doctor.hospital_id == hospital_id,
                Doctor.external_id == crawled.external_id,
                Doctor.source == "crawler",
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
                Doctor.source == "crawler",
            )
        )
        return result.scalar_one_or_none()

    return None


async def _handle_missing_doctors(
    db: AsyncSession, hospital: Hospital, matched_ids: set[int]
) -> dict:
    """이번 크롤링에서 매칭 안 된 기존 source='crawler' 의사들 처리.

    - missing_count += 1
    - missing_count >= MISSING_THRESHOLD 면:
        * visit_grade ∈ {A,B,C} (내 교수): 알림만 발송, 활성 유지
        * 그 외: is_active=False, deactivated_reason='auto-missing'
    """
    result = await db.execute(
        select(Doctor).where(
            Doctor.hospital_id == hospital.id,
            Doctor.source == "crawler",
            Doctor.is_active == True,
        )
    )
    all_active = result.scalars().all()
    missing = [d for d in all_active if d.id not in matched_ids]

    auto_deactivated = 0
    notifications_queued = 0

    for doc in missing:
        doc.missing_count = (doc.missing_count or 0) + 1
        if doc.missing_count < MISSING_THRESHOLD:
            continue

        if doc.visit_grade in ("A", "B", "C"):
            # 내 교수: 자동 비활성화 대신 알림
            await _broadcast_doctor_missing(doc, hospital)
            notifications_queued += 1
        else:
            doc.is_active = False
            doc.deactivated_reason = "auto-missing"
            doc.deactivated_at = datetime.utcnow()
            auto_deactivated += 1

    if auto_deactivated or notifications_queued:
        logger.info(
            f"[누락 감지] {hospital.code}: 자동 비활성 {auto_deactivated}명 / 알림 {notifications_queued}명"
        )

    return {
        "missing_total": len(missing),
        "auto_deactivated": auto_deactivated,
        "missing_alerts": notifications_queued,
    }


async def detect_transfer_candidate(db: AsyncSession, new_doctor: Doctor) -> None:
    """새로 등록되는 의사가 비활성된 의사와 매칭되면 알림 발송.

    매칭 조건:
    - 같은 이름 + 같은 진료과 + 다른 병원 + is_active=False
    - 같은 재단 그룹이면 강한 매칭 (점수 +100), 아니면 약한 매칭 (점수 50).
    가장 점수 높은 1명만 알림. 이미 linked_doctor_id 가 있으면 skip.
    """
    if not new_doctor.name or not new_doctor.department or not new_doctor.hospital_id:
        return
    if new_doctor.linked_doctor_id:
        # 이미 다른 record 와 link 되어 있으면 추가 알림 불필요
        return

    from sqlalchemy.orm import selectinload as _sel
    from app.crawlers.factory import get_hospital_group

    # 비활성 의사 후보 검색
    result = await db.execute(
        select(Doctor)
        .options(_sel(Doctor.hospital))
        .where(
            Doctor.name == new_doctor.name,
            Doctor.department == new_doctor.department,
            Doctor.is_active == False,  # noqa: E712
            Doctor.id != new_doctor.id,
            Doctor.hospital_id != new_doctor.hospital_id,
        )
    )
    candidates = result.scalars().all()
    if not candidates:
        return

    # 새 의사 hospital 정보 (alarm 메시지용)
    new_hospital = (await db.execute(
        select(Hospital).where(Hospital.id == new_doctor.hospital_id)
    )).scalar_one_or_none()
    new_group = get_hospital_group(new_hospital.code if new_hospital else None)

    # score 계산
    best = None
    best_score = 0
    for cand in candidates:
        cand_code = cand.hospital.code if cand.hospital else None
        cand_group = get_hospital_group(cand_code)
        score = 50  # 같은 이름 + 같은 진료과 기본
        if new_group and cand_group and new_group == cand_group:
            score += 100  # 같은 재단 그룹: 강한 시그널
        if score > best_score:
            best = cand
            best_score = score

    if not best:
        return

    same_group = best_score >= 150
    try:
        from app.notifications.manager import notification_manager
        msg = (
            f"{best.hospital.name if best.hospital else ''} {best.name} 교수님이 "
            f"{new_hospital.name if new_hospital else ''}에 새로 등장했습니다. "
            f"이직 맞나요?"
            + (" (같은 재단)" if same_group else "")
        )
        await notification_manager.broadcast({
            "type": "doctor_transfer_candidate",
            "data": {
                "new_doctor_id": new_doctor.id,
                "new_doctor_name": new_doctor.name,
                "new_hospital_name": new_hospital.name if new_hospital else None,
                "new_department": new_doctor.department,
                "old_doctor_id": best.id,
                "old_doctor_name": best.name,
                "old_hospital_name": best.hospital.name if best.hospital else None,
                "old_department": best.department,
                "same_group": same_group,
                "score": best_score,
                "message": msg,
            },
            "created_at": datetime.utcnow().isoformat(),
            "read": False,
        })
    except Exception as e:
        logger.warning(f"[이직 후보 알림 실패] {new_doctor.name}: {e}")


async def _broadcast_doctor_missing(doctor: Doctor, hospital: Hospital) -> None:
    """내 교수 누락 알림. NotificationPanel 의 doctor_auto_missing 타입."""
    try:
        from app.notifications.manager import notification_manager
        await notification_manager.broadcast({
            "type": "doctor_auto_missing",
            "data": {
                "doctor_id": doctor.id,
                "doctor_name": doctor.name,
                "hospital_code": hospital.code,
                "hospital_name": hospital.name,
                "department": doctor.department,
                "visit_grade": doctor.visit_grade,
                "missing_count": doctor.missing_count,
                "message": f"{hospital.name} {doctor.name} 교수님이 최근 크롤링에서 보이지 않습니다. 이직/퇴직 여부를 확인해 주세요.",
            },
            "created_at": datetime.utcnow().isoformat(),
            "read": False,
        })
    except Exception as e:
        # 알림 실패해도 크롤링 자체는 계속 진행
        logger.warning(f"[알림 실패] {doctor.name}: {e}")


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


async def _sync_date_schedules(db: AsyncSession, doctor_id: int, new_date_schedules: list[dict]):
    """날짜별 진료 일정을 동기화합니다. 기존 데이터를 삭제하고 새로 저장."""
    if not new_date_schedules:
        return

    # 새 데이터의 날짜 범위
    dates = [ds["schedule_date"] for ds in new_date_schedules]
    min_date = min(dates)
    max_date = max(dates)

    # 해당 범위의 기존 데이터 삭제
    result = await db.execute(
        select(DoctorDateSchedule).where(
            DoctorDateSchedule.doctor_id == doctor_id,
            DoctorDateSchedule.schedule_date >= min_date,
            DoctorDateSchedule.schedule_date <= max_date,
        )
    )
    for old in result.scalars().all():
        await db.delete(old)

    # 새 데이터 저장
    for ds in new_date_schedules:
        date_sched = DoctorDateSchedule(
            doctor_id=doctor_id,
            schedule_date=ds["schedule_date"],
            time_slot=ds.get("time_slot", ""),
            start_time=ds.get("start_time", ""),
            end_time=ds.get("end_time", ""),
            location=ds.get("location", ""),
            status=ds.get("status", "진료"),
            crawled_at=datetime.utcnow(),
        )
        db.add(date_sched)
