"""academic_events 테이블에 상세 정보 컬럼 4개 추가.

KMA 크롤러가 이미 추출하지만 버려지던 필드들을 저장하기 위한 일회성 마이그레이션.
- sub_organizer (주관)
- region (지역)
- event_code (교육코드)
- detail_url_external (비고의 외부 URL)

사용법:
    cd backend
    python scripts/add_academic_detail_columns.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "pharma_scheduler.db"

NEW_COLUMNS = [
    ("sub_organizer", "VARCHAR(300)"),
    ("region", "VARCHAR(100)"),
    ("event_code", "VARCHAR(100)"),
    ("detail_url_external", "VARCHAR(500)"),
]


def main() -> int:
    if not DB_PATH.exists():
        print(f"[ERROR] DB 파일 없음: {DB_PATH}")
        return 1

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(academic_events)")
    existing = {row[1] for row in cur.fetchall()}

    added = []
    skipped = []
    for col, type_ in NEW_COLUMNS:
        if col in existing:
            skipped.append(col)
            continue
        cur.execute(f"ALTER TABLE academic_events ADD COLUMN {col} {type_}")
        added.append(col)

    conn.commit()
    conn.close()

    print(f"[OK] added: {added or '(none)'}")
    if skipped:
        print(f"[SKIP] already exists: {skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
