"""크롤링 Celery 태스크

주요 태스크:
1. crawl_all_hospitals    - 전체 병원 크롤링 (매일 새벽)
2. crawl_single_hospital  - 특정 병원 크롤링
3. crawl_single_doctor    - 특정 의료진 크롤링
4. check_registered_doctors - 등록된 의료진만 빠르게 변경 체크
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from app.tasks.celery_app import celery_app
from app.crawlers.factory import get_crawler, CRAWLER_REGISTRY
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def run_async(coro):
    """Celery 태스크 내에서 async 함수 실행 헬퍼"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ============================================================
# 태스크 1: 전체 병원 크롤링
# ============================================================
@celery_app.task(
    name="app.tasks.crawl_tasks.crawl_all_hospitals",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
)
def crawl_all_hospitals(self):
    """모든 지원 병원의 의료진 진료일정을 크롤링합니다.
    
    Beat 스케줄: 매일 새벽 3시 자동 실행
    """
    logger.info("=" * 50)
    logger.info("전체 병원 크롤링 시작")
    logger.info("=" * 50)

    results = {}
    for hospital_code in CRAWLER_REGISTRY:
        try:
            result = crawl_single_hospital.delay(hospital_code)
            results[hospital_code] = "dispatched"
            logger.info(f"  → {hospital_code} 크롤링 태스크 발행 (task_id: {result.id})")
        except Exception as e:
            results[hospital_code] = f"error: {str(e)}"
            logger.error(f"  → {hospital_code} 태스크 발행 실패: {e}")

    return {
        "task": "crawl_all_hospitals",
        "dispatched_at": datetime.now().isoformat(),
        "hospitals": results,
    }


# ============================================================
# 태스크 2: 특정 병원 크롤링
# ============================================================
@celery_app.task(
    name="app.tasks.crawl_tasks.crawl_single_hospital",
    bind=True,
    max_retries=settings.CRAWL_MAX_RETRIES,
    default_retry_delay=120,
)
def crawl_single_hospital(self, hospital_code: str, department: str = None):
    """특정 병원의 의료진 진료일정을 크롤링하고 변경사항을 감지합니다."""
    logger.info(f"[{hospital_code}] 크롤링 시작" + (f" (진료과: {department})" if department else ""))

    try:
        crawler = get_crawler(hospital_code)
        result = run_async(crawler.crawl_doctors(department=department))

        # 크롤링 결과 처리
        summary = {
            "hospital_code": hospital_code,
            "hospital_name": result.hospital_name,
            "status": result.status,
            "doctors_count": len(result.doctors),
            "crawled_at": result.crawled_at.isoformat(),
        }

        if result.status == "success" or result.status == "partial":
            # 변경 감지 태스크 실행
            changes = _detect_schedule_changes(hospital_code, result)
            summary["changes_detected"] = len(changes)

            if changes:
                # 알림 발송 태스크 트리거
                _trigger_change_notifications(changes)
                logger.info(f"[{hospital_code}] {len(changes)}건 일정 변경 감지 → 알림 발송")

            # DB 저장 (비동기)
            _save_crawl_result(hospital_code, result)

        logger.info(f"[{hospital_code}] 크롤링 완료: {summary}")
        return summary

    except Exception as e:
        logger.error(f"[{hospital_code}] 크롤링 실패: {e}")
        # 재시도
        raise self.retry(exc=e)


# ============================================================
# 태스크 3: 특정 의료진 크롤링
# ============================================================
@celery_app.task(
    name="app.tasks.crawl_tasks.crawl_single_doctor",
    bind=True,
    max_retries=settings.CRAWL_MAX_RETRIES,
    default_retry_delay=60,
)
def crawl_single_doctor(self, hospital_code: str, staff_id: str):
    """특정 의료진의 진료시간표를 크롤링합니다."""
    logger.info(f"[{hospital_code}] 의료진 {staff_id} 개별 크롤링")

    try:
        crawler = get_crawler(hospital_code)
        result = run_async(crawler.crawl_doctor_schedule(staff_id))

        return {
            "hospital_code": hospital_code,
            "staff_id": staff_id,
            "name": result.get("name", ""),
            "schedules_count": len(result.get("schedules", [])),
            "crawled_at": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"[{hospital_code}] 의료진 {staff_id} 크롤링 실패: {e}")
        raise self.retry(exc=e)


# ============================================================
# 태스크 4: 등록된 의료진 변경 체크 (경량 크롤링)
# ============================================================
@celery_app.task(
    name="app.tasks.crawl_tasks.check_registered_doctors",
    bind=True,
    max_retries=1,
    default_retry_delay=60,
)
def check_registered_doctors(self):
    """등록된 의료진만 대상으로 빠르게 진료일정 변경 여부를 확인합니다.
    
    Beat 스케줄: 30분마다 실행
    전체 크롤링과 달리, DB에 등록된 의료진만 개별 체크합니다.
    """
    logger.info("등록된 의료진 변경 체크 시작")

    # TODO: DB에서 등록된 의료진 목록 조회
    # 현재는 구조만 잡아둠
    registered_doctors = _get_registered_doctors()

    checked = 0
    changes_found = 0

    for doc in registered_doctors:
        try:
            crawl_single_doctor.delay(
                hospital_code=doc["hospital_code"],
                staff_id=doc["external_id"],
            )
            checked += 1
        except Exception as e:
            logger.error(f"의료진 {doc['name']} 체크 실패: {e}")

    logger.info(f"등록된 의료진 {checked}명 체크 태스크 발행 완료")

    return {
        "task": "check_registered_doctors",
        "checked": checked,
        "timestamp": datetime.now().isoformat(),
    }


# ============================================================
# 내부 헬퍼 함수들
# ============================================================
def _detect_schedule_changes(hospital_code: str, crawl_result) -> list[dict]:
    """이전 크롤링 결과와 비교하여 변경사항 감지
    
    Returns:
        변경 내역 리스트: [{doctor_name, change_type, old, new, ...}]
    """
    changes = []

    # TODO: DB에서 이전 일정 조회 후 비교
    # 현재는 인메모리 캐시 기반 비교 구조
    for doctor in crawl_result.doctors:
        previous = _get_previous_schedule(hospital_code, doctor.external_id)
        if previous is None:
            continue  # 최초 크롤링이면 비교 불가

        old_set = {(s["day_of_week"], s["time_slot"]) for s in previous}
        new_set = {(s["day_of_week"], s["time_slot"]) for s in doctor.schedules}

        removed = old_set - new_set
        added = new_set - old_set

        DAY_NAMES = ["월", "화", "수", "목", "금", "토", "일"]
        SLOT_NAMES = {"morning": "오전", "afternoon": "오후", "evening": "야간"}

        for day, slot in removed:
            changes.append({
                "doctor_name": doctor.name,
                "doctor_id": doctor.external_id,
                "hospital_code": hospital_code,
                "change_type": "removed",
                "day": DAY_NAMES[day],
                "time_slot": SLOT_NAMES.get(slot, slot),
                "message": f"{doctor.name} 교수 {DAY_NAMES[day]} {SLOT_NAMES.get(slot, slot)} 진료 취소",
                "detected_at": datetime.now().isoformat(),
            })

        for day, slot in added:
            changes.append({
                "doctor_name": doctor.name,
                "doctor_id": doctor.external_id,
                "hospital_code": hospital_code,
                "change_type": "added",
                "day": DAY_NAMES[day],
                "time_slot": SLOT_NAMES.get(slot, slot),
                "message": f"{doctor.name} 교수 {DAY_NAMES[day]} {SLOT_NAMES.get(slot, slot)} 진료 추가",
                "detected_at": datetime.now().isoformat(),
            })

    return changes


def _trigger_change_notifications(changes: list[dict]):
    """변경사항 알림 발송 태스크 트리거"""
    from app.tasks.notification_tasks import send_schedule_change_notification

    for change in changes:
        try:
            send_schedule_change_notification.delay(change)
        except Exception as e:
            logger.error(f"알림 발송 태스크 실패: {e}")


def _get_previous_schedule(hospital_code: str, staff_id: str) -> Optional[list]:
    """이전 크롤링 결과 조회 (DB 연동 전 임시 구현)"""
    # TODO: DB에서 마지막 크롤링 결과 조회
    # DoctorSchedule 테이블에서 해당 의료진의 현재 일정 반환
    return None


def _get_registered_doctors() -> list[dict]:
    """DB에서 등록된 의료진 목록 조회 (DB 연동 전 임시 구현)"""
    # TODO: Doctor 테이블에서 is_active=True인 의료진 목록
    return []


def _save_crawl_result(hospital_code: str, crawl_result):
    """크롤링 결과를 DB에 저장 (DB 연동 전 임시 구현)"""
    # TODO: 비동기 DB 세션으로 결과 저장
    # 1) CrawlLog에 크롤링 이력 저장
    # 2) Doctor 테이블에 신규 의료진 추가/기존 정보 업데이트
    # 3) DoctorSchedule 테이블에 일정 upsert
    # 4) ScheduleChange에 변경 이력 저장
    logger.info(f"[{hospital_code}] 크롤링 결과 DB 저장 (TODO: 구현 예정)")
