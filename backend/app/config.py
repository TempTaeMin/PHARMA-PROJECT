"""PharmScheduler 설정 관리"""
import os
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    APP_NAME: str = "PharmScheduler"
    APP_VERSION: str = "0.2.0"
    DEBUG: bool = True

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./pharma_scheduler.db"

    # Redis (Celery broker + 알림 pub/sub)
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    CELERY_RESULT_BACKEND: str = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

    # 크롤링 설정
    CRAWL_INTERVAL_HOURS: int = 24         # 기본 크롤링 주기 (시간)
    CRAWL_TIME: str = "03:00"              # 자동 크롤링 실행 시각 (KST)
    CRAWL_REQUEST_DELAY: float = 1.0       # 요청 간 딜레이 (초) - 서버 부하 방지
    CRAWL_MAX_RETRIES: int = 3             # 크롤링 실패 시 재시도 횟수
    CRAWL_TIMEOUT: int = 30                # 요청 타임아웃 (초)

    # 알림 설정
    NOTIFICATION_ENABLED: bool = True
    WEBSOCKET_HEARTBEAT: int = 30          # WebSocket 하트비트 (초)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
