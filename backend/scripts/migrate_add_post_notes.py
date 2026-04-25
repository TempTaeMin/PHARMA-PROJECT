"""VisitLog.post_notes 컬럼 추가 + 완료된 교수 방문 notes → post_notes 이관.

사전/사후 메모 분리 도입. 이미 완료된(status ∈ 성공/부재/거절) 교수 방문(doctor_id 존재)은
기존 notes 가 "방문 결과 메모"로 쓰였을 것이므로 post_notes 로 옮기고 notes 는 비운다.
업무·공지(doctor_id 없음) 는 그대로 notes 를 유지.
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
        if "post_notes" not in cols:
            await conn.execute(text("ALTER TABLE visit_logs ADD COLUMN post_notes TEXT"))
            print("[ok] added visit_logs.post_notes column")
        else:
            print("[skip] visit_logs.post_notes already exists")

        # 이미 완료된 교수 방문만 이관 (예정 상태의 notes 는 사전 메모 — 건드리지 않음)
        result = await conn.execute(text(
            """
            UPDATE visit_logs
               SET post_notes = notes,
                   notes = NULL
             WHERE doctor_id IS NOT NULL
               AND status IN ('성공', '부재', '거절')
               AND notes IS NOT NULL
               AND (post_notes IS NULL OR post_notes = '')
            """
        ))
        print(f"[ok] migrated {result.rowcount} completed professor visits (notes → post_notes)")


if __name__ == "__main__":
    asyncio.run(run())
