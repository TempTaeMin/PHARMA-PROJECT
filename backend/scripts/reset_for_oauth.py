"""OAuth 도입 시점 데이터 초기화 스크립트 — 한 번만 실행.

비우는 대상 (= '내가 만든 흔적'):
- visit_memos, reports, memo_templates, visit_logs
- doctors.visit_grade, doctors.memo (사용자별 분리됐으므로 글로벌 컬럼 비움)
- academic_events.is_pinned (UserAcademicPin 으로 분리됐으므로 false 처리)

유지 대상 (= 마스터 DB):
- hospitals, doctors (row 자체), doctor_schedules, doctor_date_schedules
- academic_organizers, academic_events (row 자체), academic_event_departments
- crawl_logs, schedule_changes

신규 테이블(users, teams, team_members, user_doctor_grades, user_doctor_memos,
user_academic_pins)은 어차피 비어있으므로 truncate 불필요.

사용:
    cd backend && python -m scripts.reset_for_oauth
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "pharma_scheduler.db"


def main():
    if not DB_PATH.exists():
        raise SystemExit(f"DB 파일을 찾을 수 없음: {DB_PATH}")

    print(f"[reset_for_oauth] target: {DB_PATH}")
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    # 1) 사용자 흔적 테이블 truncate
    user_tables = ["visit_memos", "reports", "memo_templates", "visit_logs"]
    actual_user_tables = []
    for tbl in user_tables:
        # 실제 테이블 이름 확인 (visit_memos vs visits_memo)
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (tbl,)
        )
        if cur.fetchone():
            actual_user_tables.append(tbl)
    # visits_memo 대체명 처리
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='visits_memo'")
    if cur.fetchone() and "visits_memo" not in actual_user_tables:
        actual_user_tables.append("visits_memo")

    for tbl in actual_user_tables:
        cur.execute(f"DELETE FROM {tbl}")
        deleted = cur.rowcount
        print(f"  - {tbl}: {deleted} rows deleted")

    # 2) doctors 의 사용자 의견 컬럼 비우기
    cur.execute("UPDATE doctors SET visit_grade=NULL, memo=NULL")
    print(f"  - doctors.visit_grade/memo: {cur.rowcount} rows reset")

    # 3) academic_events 의 is_pinned 초기화
    cur.execute("UPDATE academic_events SET is_pinned=0")
    print(f"  - academic_events.is_pinned: {cur.rowcount} rows reset")

    con.commit()

    # 4) 마스터 row 카운트 확인용 출력
    print("\n[남은 마스터 데이터]")
    for tbl in ["hospitals", "doctors", "academic_events", "academic_organizers"]:
        cur.execute(f"SELECT COUNT(*) FROM {tbl}")
        cnt = cur.fetchone()[0]
        print(f"  - {tbl}: {cnt} rows")

    con.close()
    print("\n[reset_for_oauth] 완료. 백엔드 재기동 후 첫 Google 로그인이 가능합니다.")


if __name__ == "__main__":
    main()
