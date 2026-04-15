"""academic_events 테이블에 lectures_json 컬럼 추가 (일회성 마이그레이션).

KMA 상세 페이지의 강의 프로그램(시간/제목/강사/소속) 을 JSON 배열로 저장하기 위한 컬럼.

사용법:
    cd backend
    python scripts/add_academic_lectures_column.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "pharma_scheduler.db"


def main() -> int:
    if not DB_PATH.exists():
        print(f"[ERROR] DB 파일 없음: {DB_PATH}")
        return 1

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(academic_events)")
    existing = {row[1] for row in cur.fetchall()}

    if "lectures_json" in existing:
        print("[SKIP] lectures_json 이미 존재")
    else:
        cur.execute("ALTER TABLE academic_events ADD COLUMN lectures_json TEXT")
        print("[OK] added: lectures_json")

    conn.commit()
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
