"""Celery 앱 설정

사용법:
  # Worker 실행
  celery -A app.tasks.celery_app worker --loglevel=info

  # Beat 스케줄러 실행 (자동 주기 크롤링)
  celery -A app.tasks.celery_app beat --loglevel=info

  # Worker + Beat 동시 실행 (개발용)
  celery -A app.tasks.celery_app worker --beat --loglevel=info
"""
from celery import Celery
from celery.schedules import crontab
from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "pharma_scheduler",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.tasks.crawl_tasks"],
)

# Celery 설정
celery_app.conf.update(
    # 직렬화
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",

    # 타임존
    timezone="Asia/Seoul",
    enable_utc=False,

    # 재시도
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_default_retry_delay=60,       # 재시도 간격 (초)
    task_max_retries=settings.CRAWL_MAX_RETRIES,

    # 동시성 제어 (크롤링은 순차 처리)
    worker_concurrency=2,
    worker_prefetch_multiplier=1,

    # Beat 스케줄 (자동 주기 크롤링)
    beat_schedule={
        # 매일 새벽 3시 전체 병원 크롤링
        "crawl-all-hospitals-daily": {
            "task": "app.tasks.crawl_tasks.crawl_all_hospitals",
            "schedule": crontab(hour=3, minute=0),
            "options": {"queue": "crawl"},
        },
        # 30분마다 변경 감지용 경량 크롤링 (등록된 교수만)
        "check-schedule-changes": {
            "task": "app.tasks.crawl_tasks.check_registered_doctors",
            "schedule": crontab(minute="*/30"),
            "options": {"queue": "crawl"},
        },
    },

    # 큐 라우팅
    task_routes={
        "app.tasks.crawl_tasks.*": {"queue": "crawl"},
        "app.tasks.notification_tasks.*": {"queue": "notify"},
    },
)
