"""기존 visibility='team' 데이터를 'private' 으로 일괄 되돌림.

선택 공유 모델 도입 1회 실행. 새 visit_log_recipients 테이블 자체는 create_all 이
백엔드 기동 시 자동 생성하므로 별도 처리 없음.
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
        cols = {row[1] for row in (await conn.execute(text("PRAGMA table_info(visit_logs)"))).fetchall()}
        if "visibility" not in cols:
            print("[skip] visibility column missing — nothing to migrate")
            return
        result = await conn.execute(text(
            "UPDATE visit_logs SET visibility='private' WHERE visibility='team'"
        ))
        print(f"[ok] reverted {result.rowcount} team-shared visits to private")


if __name__ == "__main__":
    asyncio.run(run())
