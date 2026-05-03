"""Database connection configuration.

dev (default): SQLite via aiosqlite — 빠른 로컬 iteration.
prod: DATABASE_URL=postgresql+asyncpg://... 환경변수로 PG 지정.

스키마 변경은 prod 에서 alembic 으로 관리 (`alembic upgrade head`). dev 편의를 위해
`init_db()` 가 `Base.metadata.create_all()` 로 새 테이블만 자동 추가.
"""
import os

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.models.database import Base

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./pharma_scheduler.db",
)

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """dev 편의용 — SQLite 에서 새 테이블만 자동 생성. prod 는 alembic 사용."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
