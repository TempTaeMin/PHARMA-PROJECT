"""의사·병원 라이프사이클 컬럼 추가 (1회성 마이그레이션).

SQLite 특성상 create_all() 은 기존 테이블에 컬럼을 추가하지 않으므로
명시적 ALTER TABLE 실행. 컬럼이 이미 있으면 조용히 skip.

추가 컬럼:
  hospitals: source, region
  doctors:   source, deactivated_at, deactivated_reason, linked_doctor_id, missing_count
  doctor_schedules: source
  doctor_date_schedules: source
  visit_logs: doctor_name_snapshot, doctor_dept_snapshot, hospital_name_snapshot
  visits_memo: doctor_name_snapshot, doctor_dept_snapshot, hospital_name_snapshot

backfill:
  Hospital.region  ← app.crawlers.factory._HOSPITAL_REGION
  *.source         ← 'crawler' (이미 default 지만 NULL row 안전)
  visit_logs.*_snapshot     ← 현재 연결된 doctor/hospital 값
  visits_memo.*_snapshot    ← 동일

NOTE: SQLite 는 ALTER TABLE 로 FK ondelete 정책을 변경할 수 없다.
모델에 정의된 ondelete='CASCADE'/'SET NULL' 은 새로 만들어지는 테이블에만 적용된다.
기존 테이블에서 무결성을 유지하려면 ORM 레벨 cascade(이미 추가됨) 와
운영상 hard delete 를 피하는 정책으로 보강한다.
"""
import asyncio
import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(THIS_DIR)
sys.path.insert(0, BACKEND_DIR)

from sqlalchemy import text
from app.models.connection import engine


COLUMN_DEFS: list[tuple[str, str, str]] = [
    # (table, column, "<col_def for ALTER TABLE>")
    ("hospitals", "source", "VARCHAR(16) NOT NULL DEFAULT 'crawler'"),
    ("hospitals", "region", "VARCHAR(32)"),
    ("doctors", "source", "VARCHAR(16) NOT NULL DEFAULT 'crawler'"),
    ("doctors", "deactivated_at", "DATETIME"),
    ("doctors", "deactivated_reason", "VARCHAR(32)"),
    ("doctors", "linked_doctor_id", "INTEGER"),
    ("doctors", "missing_count", "INTEGER NOT NULL DEFAULT 0"),
    ("doctor_schedules", "source", "VARCHAR(16) NOT NULL DEFAULT 'crawler'"),
    ("doctor_date_schedules", "source", "VARCHAR(16) NOT NULL DEFAULT 'crawler'"),
    ("visit_logs", "doctor_name_snapshot", "VARCHAR(100)"),
    ("visit_logs", "doctor_dept_snapshot", "VARCHAR(200)"),
    ("visit_logs", "hospital_name_snapshot", "VARCHAR(200)"),
    ("visits_memo", "doctor_name_snapshot", "VARCHAR(100)"),
    ("visits_memo", "doctor_dept_snapshot", "VARCHAR(200)"),
    ("visits_memo", "hospital_name_snapshot", "VARCHAR(200)"),
]


async def _existing_columns(conn, table: str) -> set[str]:
    rows = (await conn.execute(text(f"PRAGMA table_info({table})"))).fetchall()
    return {row[1] for row in rows}


async def add_columns(conn) -> int:
    added = 0
    for table, col, col_def in COLUMN_DEFS:
        cols = await _existing_columns(conn, table)
        if col in cols:
            print(f"[skip] {table}.{col} already exists")
            continue
        await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}"))
        print(f"[ok]   added {table}.{col}")
        added += 1
    return added


async def backfill_region(conn) -> int:
    """factory.py 의 _HOSPITAL_REGION 으로 hospital.region 백필."""
    from app.crawlers.factory import _HOSPITAL_REGION
    updated = 0
    for code, region in _HOSPITAL_REGION.items():
        result = await conn.execute(
            text("UPDATE hospitals SET region = :r WHERE code = :c AND (region IS NULL OR region = '')"),
            {"r": region, "c": code},
        )
        updated += result.rowcount or 0
    print(f"[backfill] hospitals.region updated {updated} rows")
    return updated


async def backfill_visit_snapshots(conn) -> int:
    """visit_logs / visits_memo 의 *_snapshot 컬럼을 현재 doctor/hospital 값으로 채움."""
    queries = [
        # visit_logs 의 doctor 가 살아있는 경우
        ("""
        UPDATE visit_logs
           SET doctor_name_snapshot = (SELECT d.name FROM doctors d WHERE d.id = visit_logs.doctor_id),
               doctor_dept_snapshot = (SELECT d.department FROM doctors d WHERE d.id = visit_logs.doctor_id),
               hospital_name_snapshot = (
                 SELECT h.name FROM hospitals h
                 JOIN doctors d ON d.hospital_id = h.id
                 WHERE d.id = visit_logs.doctor_id
               )
         WHERE doctor_id IS NOT NULL
           AND doctor_name_snapshot IS NULL
        """, "visit_logs"),
        ("""
        UPDATE visits_memo
           SET doctor_name_snapshot = (SELECT d.name FROM doctors d WHERE d.id = visits_memo.doctor_id),
               doctor_dept_snapshot = (SELECT d.department FROM doctors d WHERE d.id = visits_memo.doctor_id),
               hospital_name_snapshot = (
                 SELECT h.name FROM hospitals h
                 JOIN doctors d ON d.hospital_id = h.id
                 WHERE d.id = visits_memo.doctor_id
               )
         WHERE doctor_id IS NOT NULL
           AND doctor_name_snapshot IS NULL
        """, "visits_memo"),
    ]
    total = 0
    for sql, table in queries:
        result = await conn.execute(text(sql))
        n = result.rowcount or 0
        print(f"[backfill] {table}.*_snapshot updated {n} rows")
        total += n
    return total


async def run():
    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys=ON"))
        added = await add_columns(conn)
        await backfill_region(conn)
        await backfill_visit_snapshots(conn)
        print(f"\n[done] columns added: {added}")


if __name__ == "__main__":
    asyncio.run(run())
