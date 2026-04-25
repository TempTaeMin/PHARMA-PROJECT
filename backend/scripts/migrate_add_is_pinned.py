"""학회 이벤트 is_pinned 컬럼 추가 (1회성 마이그레이션).

SQLite 특성상 create_all() 은 기존 테이블에 컬럼을 추가하지 않으므로
명시적 ALTER TABLE 실행. 컬럼이 이미 있으면 조용히 skip.
"""
import asyncio
import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(THIS_DIR)
sys.path.insert(0, BACKEND_DIR)

from sqlalchemy import text
from app.models.connection import engine


async def run():
    async with engine.begin() as conn:
        existing_cols = (await conn.execute(text("PRAGMA table_info(academic_events)"))).fetchall()
        cols = {row[1] for row in existing_cols}
        if "is_pinned" in cols:
            print("[skip] academic_events.is_pinned already exists")
            return
        await conn.execute(text(
            "ALTER TABLE academic_events ADD COLUMN is_pinned BOOLEAN DEFAULT 0"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_academic_events_is_pinned "
            "ON academic_events(is_pinned)"
        ))
        print("[ok] added is_pinned column + index")


if __name__ == "__main__":
    asyncio.run(run())
