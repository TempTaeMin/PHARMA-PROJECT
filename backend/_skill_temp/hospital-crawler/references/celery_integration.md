# Celery 태스크 연동 패턴

완성된 크롤러를 MR 스케줄러의 Celery 비동기 태스크로 연결하는 표준 패턴.

## 기본 태스크 구조

```python
# tasks/crawl_tasks.py
from celery import shared_task
from crawlers.snuh import SNUHCrawler
from db.session import get_db
from db.models import DoctorSchedule
import logging

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3)
def crawl_hospital(self, hospital_code: str):
    """단일 병원 크롤링 태스크"""
    crawler_map = {
        "SNUH": SNUHCrawler,
        # 신규 병원 추가 시 여기에 등록
    }

    CrawlerClass = crawler_map.get(hospital_code)
    if not CrawlerClass:
        logger.error(f"Unknown hospital_code: {hospital_code}")
        return

    try:
        crawler = CrawlerClass()
        results = crawler.crawl_all()
        _save_results(results)
        logger.info(f"{hospital_code} crawl complete: {len(results)} records")
    except Exception as exc:
        logger.error(f"{hospital_code} crawl failed: {exc}")
        raise self.retry(exc=exc, countdown=60)


def _save_results(results: list):
    """크롤링 결과 DB upsert"""
    db = next(get_db())
    for row in results:
        # deptcd + drcd 기준 upsert
        existing = db.query(DoctorSchedule).filter_by(
            hospital_code=row["hospital_code"],
            deptcd=row["deptcd"],
            drcd=row["drcd"],
        ).first()

        if existing:
            existing.schedule = row["schedule"]
            existing.doctor_name = row["doctor_name"]
        else:
            db.add(DoctorSchedule(**row))
    db.commit()
```

## 전체 병원 일괄 크롤링

```python
@shared_task
def crawl_all_hospitals():
    """등록된 모든 병원 크롤링 (Celery beat 스케줄러로 주기 실행)"""
    hospital_codes = ["SNUH", "AMC", ...]  # DB에서 읽어도 됨
    for code in hospital_codes:
        crawl_hospital.delay(code)
```

## Celery Beat 스케줄 설정 (celeryconfig.py)

```python
from celery.schedules import crontab

beat_schedule = {
    "crawl-all-hospitals-daily": {
        "task": "tasks.crawl_tasks.crawl_all_hospitals",
        "schedule": crontab(hour=2, minute=0),  # 매일 새벽 2시
    },
}
```

## WebSocket 연동 (크롤링 진행률 실시간 전송)

```python
@shared_task(bind=True)
def crawl_hospital_with_progress(self, hospital_code: str):
    crawler = get_crawler(hospital_code)
    departments = crawler.get_departments()
    total = len(departments)

    for i, dept in enumerate(departments):
        # 진행률 WebSocket 전송
        self.update_state(state="PROGRESS", meta={"current": i, "total": total})
        # ... 크롤링 로직
```
