"""알림 발송 Celery 태스크

일정 변경이 감지되면 크롤링 태스크에서 호출됩니다.
알림 채널: WebSocket (실시간), DB 저장 (히스토리), 향후 Push/Email 확장 가능
"""
import json
import logging
from datetime import datetime

from app.tasks.celery_app import celery_app
from app.notifications.manager import notification_manager

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.tasks.notification_tasks.send_schedule_change_notification",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def send_schedule_change_notification(self, change: dict):
    """일정 변경 알림을 발송합니다.
    
    Args:
        change: {
            "doctor_name": "김정형",
            "doctor_id": "1001",
            "hospital_code": "AMC",
            "change_type": "removed" | "added",
            "day": "월",
            "time_slot": "오전",
            "message": "김정형 교수 월 오전 진료 취소",
            "detected_at": "2026-03-26T03:00:00",
        }
    """
    logger.info(f"알림 발송: {change['message']}")

    notification = {
        "type": "schedule_change",
        "data": change,
        "created_at": datetime.now().isoformat(),
        "read": False,
    }

    try:
        # 1) WebSocket으로 실시간 전달
        notification_manager.broadcast_sync(notification)

        # 2) DB에 알림 히스토리 저장 (TODO)
        _save_notification_to_db(notification)

        # 3) 향후: Push / Email / SMS
        # _send_push_notification(notification)
        # _send_email_notification(notification)

        logger.info(f"알림 발송 완료: {change['message']}")
        return {"status": "sent", "message": change["message"]}

    except Exception as e:
        logger.error(f"알림 발송 실패: {e}")
        raise self.retry(exc=e)


@celery_app.task(name="app.tasks.notification_tasks.send_visit_reminder")
def send_visit_reminder(doctor_name: str, visit_time: str, hospital_name: str):
    """방문 리마인더 알림을 발송합니다."""
    notification = {
        "type": "visit_reminder",
        "data": {
            "doctor_name": doctor_name,
            "visit_time": visit_time,
            "hospital_name": hospital_name,
            "message": f"{visit_time} {hospital_name} {doctor_name} 교수 방문 예정",
        },
        "created_at": datetime.now().isoformat(),
        "read": False,
    }

    notification_manager.broadcast_sync(notification)
    logger.info(f"방문 리마인더: {notification['data']['message']}")
    return {"status": "sent"}


@celery_app.task(name="app.tasks.notification_tasks.send_overdue_warning")
def send_overdue_warning(doctor_name: str, grade: str, days_overdue: int):
    """미방문 경고 알림을 발송합니다."""
    notification = {
        "type": "overdue_warning",
        "data": {
            "doctor_name": doctor_name,
            "grade": grade,
            "days_overdue": days_overdue,
            "message": f"{doctor_name} 교수({grade}등급) {days_overdue}일간 미방문",
        },
        "created_at": datetime.now().isoformat(),
        "read": False,
    }

    notification_manager.broadcast_sync(notification)
    logger.info(f"미방문 경고: {notification['data']['message']}")
    return {"status": "sent"}


def _save_notification_to_db(notification: dict):
    """알림을 DB에 저장 (향후 구현)"""
    # TODO: Notification 테이블에 저장
    pass
