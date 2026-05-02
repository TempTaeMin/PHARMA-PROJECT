"""PharmScheduler - FastAPI 메인 앱"""
import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()  # backend/.env → os.environ (ANTHROPIC_API_KEY 등)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
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
from app.api.reports import router as reports_router
from app.api.visits import router as visits_router
from app.auth.routes import router as auth_router

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

# 세션 쿠키 (OAuth state + 로그인 user_id 저장)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET_KEY", "dev-only-change-me"),
    same_site="lax",
    https_only=os.getenv("ENV") == "production",
)

# CORS: 쿠키 세션 사용 시 wildcard 불가 — origin 명시 필수
_cors_origins_env = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
_cors_origins = [o.strip() for o in _cors_origins_env.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
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
app.include_router(reports_router)
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
