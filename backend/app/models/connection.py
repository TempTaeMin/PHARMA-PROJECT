"""Database connection configuration.

dev (default): SQLite via aiosqlite — 빠른 로컬 iteration.
prod: DATABASE_URL=postgresql+asyncpg://... 환경변수로 PG 지정.

스키마는 **alembic 으로만** 관리한다. 스키마 변경 시 `alembic upgrade head`.
이전엔 `init_db()` 가 `Base.metadata.create_all()` 로 새 테이블을 자동 생성했지만,
이게 alembic 의 `op.create_table()` 과 DuplicateTableError 로 충돌하면서 운영 마이그가
조용히 깨지는 사고가 반복돼 제거했다 (5/6 visit_logs 4컬럼 누락, feedbacks 충돌).

새 환경 시작 절차:
    cd backend && alembic upgrade head     # 빈 DB 또는 새 마이그 적용

기존 SQLite 가 있는데 alembic_version 이 없는 dev 환경:
    cd backend && alembic stamp head       # 한 번만, schema 가 이미 head 와 같다고 마킹
    cd backend && alembic upgrade head     # 이후엔 정상
"""
import os

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.models.database import Base  # noqa: F401 — 다른 모듈이 connection.py 경유로 Base 참조

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./pharma_scheduler.db",
)

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """no-op — schema 는 alembic 이 관리한다.

    이전엔 `Base.metadata.create_all` 호출했지만 alembic 마이그와 충돌해 제거.
    schema 가 비어있거나 뒤처져 있으면 첫 쿼리에서 명확한 SQL 에러로 실패하므로
    사일런트 데이터 사고를 막는 쪽이 안전하다.
    """
    return None


async def get_db():
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
