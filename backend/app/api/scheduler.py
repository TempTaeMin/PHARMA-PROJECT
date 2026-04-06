"""크롤링 스케줄러 관리 API"""
from fastapi import APIRouter, HTTPException, Query
from datetime import datetime

router = APIRouter(prefix="/api/scheduler", tags=["스케줄러"])


@router.post("/run/{hospital_code}", summary="수동 크롤링 실행")
async def trigger_crawl(
    hospital_code: str,
    department: str = Query(None, description="특정 진료과만 (선택)"),
):
    """Celery 태스크로 크롤링을 수동 실행합니다."""
    try:
        from app.tasks.crawl_tasks import crawl_single_hospital
        task = crawl_single_hospital.delay(hospital_code, department)
        return {
            "status": "dispatched",
            "task_id": task.id,
            "hospital_code": hospital_code,
            "department": department,
            "dispatched_at": datetime.now().isoformat(),
        }
    except Exception as e:
        # Celery/Redis 미연결 시 동기 실행 폴백
        return await _fallback_sync_crawl(hospital_code, department, str(e))


@router.post("/run-all", summary="전체 병원 크롤링 실행")
async def trigger_crawl_all():
    """모든 지원 병원의 크롤링을 Celery 태스크로 실행합니다."""
    try:
        from app.tasks.crawl_tasks import crawl_all_hospitals
        task = crawl_all_hospitals.delay()
        return {
            "status": "dispatched",
            "task_id": task.id,
            "dispatched_at": datetime.now().isoformat(),
        }
    except Exception as e:
        return {
            "status": "celery_unavailable",
            "error": str(e),
            "message": "Redis/Celery가 실행되지 않았습니다. 수동 크롤링을 사용하세요.",
        }


@router.get("/task/{task_id}", summary="태스크 상태 조회")
async def get_task_status(task_id: str):
    """Celery 태스크의 실행 상태를 조회합니다."""
    try:
        from app.tasks.celery_app import celery_app
        result = celery_app.AsyncResult(task_id)
        return {
            "task_id": task_id,
            "status": result.status,       # PENDING, STARTED, SUCCESS, FAILURE, RETRY
            "result": result.result if result.ready() else None,
            "traceback": str(result.traceback) if result.failed() else None,
        }
    except Exception as e:
        return {
            "task_id": task_id,
            "status": "unknown",
            "error": str(e),
        }


@router.get("/status", summary="스케줄러 상태")
async def scheduler_status():
    """크롤링 스케줄러의 전체 상태를 확인합니다."""
    celery_connected = False
    try:
        from app.tasks.celery_app import celery_app
        inspect = celery_app.control.inspect()
        active = inspect.active()
        celery_connected = active is not None
        workers = list(active.keys()) if active else []
    except:
        workers = []

    from app.crawlers.factory import list_supported_hospitals

    return {
        "celery_connected": celery_connected,
        "workers": workers,
        "supported_hospitals": list_supported_hospitals(),
        "schedule": {
            "full_crawl": "매일 03:00 KST",
            "change_check": "30분 간격",
        },
        "checked_at": datetime.now().isoformat(),
    }


async def _fallback_sync_crawl(hospital_code: str, department: str, error: str):
    """Celery 미연결 시 동기 방식으로 크롤링 실행 (개발/테스트용)"""
    from app.crawlers.factory import get_crawler

    try:
        crawler = get_crawler(hospital_code)
        result = await crawler.crawl_doctors(department=department)
        return {
            "status": "completed_sync",
            "message": f"Celery 미연결({error}), 동기 실행 완료",
            "hospital_code": hospital_code,
            "doctors_count": len(result.doctors),
            "crawl_status": result.status,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
