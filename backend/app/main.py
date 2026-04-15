"""PharmScheduler - FastAPI 메인 앱"""
import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()  # backend/.env → os.environ (ANTHROPIC_API_KEY 등)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.models.connection import init_db, async_session
from app.models.seed import seed_database
from app.api.crawl import router as crawl_router
from app.api.dashboard import router as dashboard_router
from app.api.doctors import router as doctors_router
from app.api.hospitals import router as hospitals_router
from app.api.notifications import router as notifications_router
from app.api.scheduler import router as scheduler_router
from app.api.academic import router as academic_router
from app.api.memos import (
    router as memos_router,
    templates_router as memo_templates_router,
    doctor_memos_router,
)
from app.api.visits import router as visits_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with async_session() as db:
        await seed_database(db)
    logging.getLogger(__name__).info("PharmScheduler v0.4.0 시작")
    yield
    logging.getLogger(__name__).info("PharmScheduler 종료")


app = FastAPI(
    title="PharmScheduler API",
    description="제약 영업사원을 위한 교수 진료일정 크롤링 & 스케줄 관리 API",
    version="0.4.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(crawl_router)
app.include_router(dashboard_router)
app.include_router(hospitals_router)
app.include_router(doctors_router)
app.include_router(scheduler_router)
app.include_router(notifications_router)
app.include_router(academic_router)
app.include_router(memos_router)
app.include_router(memo_templates_router)
app.include_router(doctor_memos_router)
app.include_router(visits_router)


@app.get("/", tags=["헬스체크"])
async def root():
    from app.notifications.manager import notification_manager
    return {
        "service": "PharmScheduler",
        "version": "0.4.0",
        "status": "running",
        "websocket_connections": notification_manager.active_count,
    }


@app.get("/health", tags=["헬스체크"])
async def health():
    return {"status": "ok"}
