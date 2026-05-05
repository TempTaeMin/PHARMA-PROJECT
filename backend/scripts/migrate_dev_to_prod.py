"""dev SQLite → prod Postgres 마스터 데이터 마이그레이션.

옮기는 테이블 (user 무관 마스터):
  hospitals → doctors → doctor_schedules / doctor_date_schedules
            → academic_organizers / academic_events / academic_event_departments

옮기지 않는 테이블 (user-specific, 운영에서 새로 시작):
  users, teams, team_members, team_invitations,
  user_doctor_grades, user_doctor_memos, user_academic_pins,
  visit_logs, visit_log_recipients, visits_memo, memo_templates, reports,
  schedule_changes, crawl_logs (운영 이력)

사용:
  DATABASE_URL=postgresql://medisync:비번@localhost:5432/medisync \
      python scripts/migrate_dev_to_prod.py /path/to/pharma_scheduler.db [--dry-run]
"""
import argparse
import os
import sys

from sqlalchemy import MetaData, create_engine, text


# FK 의존 순서대로
TABLES = [
    "hospitals",
    "doctors",
    "doctor_schedules",
    "doctor_date_schedules",
    "academic_organizers",
    "academic_events",
    "academic_event_departments",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sqlite_path")
    ap.add_argument("--dry-run", action="store_true",
                    help="prod 변경 없이 양쪽 row count 만 출력")
    args = ap.parse_args()

    if not os.path.exists(args.sqlite_path):
        sys.exit(f"SQLite 파일 없음: {args.sqlite_path}")

    dst_url = os.environ.get("DATABASE_URL")
    if not dst_url:
        sys.exit("DATABASE_URL 환경변수 필요 (예: postgresql://user:pw@localhost:5432/db)")
    # asyncpg 드라이버 표기는 sync 엔진과 호환 안 됨 — psycopg/psycopg2 로 강제
    dst_url = dst_url.replace("+asyncpg", "").replace("postgresql+psycopg2", "postgresql")

    print(f"src: sqlite {args.sqlite_path}")
    print(f"dst: {dst_url.split('@')[-1] if '@' in dst_url else dst_url}")
    print()

    src = create_engine(f"sqlite:///{args.sqlite_path}")
    dst = create_engine(dst_url)

    src_md = MetaData()
    src_md.reflect(bind=src, only=TABLES)
    dst_md = MetaData()
    dst_md.reflect(bind=dst, only=TABLES)

    # 양쪽 row count
    print(f"{'table':35s} {'src':>7} {'dst(before)':>12}")
    print("-" * 60)
    with src.connect() as s, dst.connect() as d:
        for t in TABLES:
            src_cnt = s.execute(text(f"select count(*) from {t}")).scalar()
            dst_cnt = d.execute(text(f"select count(*) from {t}")).scalar()
            print(f"{t:35s} {src_cnt:>7} {dst_cnt:>12}")
    print()

    if args.dry_run:
        print("[dry-run] 변경 없이 종료")
        return

    confirm = os.environ.get("MIGRATE_CONFIRM")
    if confirm != "yes":
        print("실제 마이그레이션은 MIGRATE_CONFIRM=yes 환경변수와 함께 다시 실행")
        return

    # 1) 기존 마스터 데이터 비우기 (FK 역순, CASCADE 로 user-specific 참조 정리)
    print("1) prod 의 기존 마스터 데이터 비우기 ...")
    with dst.begin() as d:
        # CASCADE: user_doctor_grades / user_doctor_memos / user_academic_pins 등 자동 정리
        d.execute(text(f"truncate table {', '.join(TABLES)} restart identity cascade"))
    print("   완료\n")

    # 2) row 복사 (ID 보존)
    print("2) row 복사 ...")
    for t in TABLES:
        src_table = src_md.tables[t]
        dst_table = dst_md.tables[t]
        with src.connect() as s:
            rows = [dict(row._mapping) for row in s.execute(src_table.select())]
        if not rows:
            print(f"   {t:35s} skip (0 rows)")
            continue
        # 청크 단위 INSERT (큰 테이블 메모리 절약)
        chunk = 500
        with dst.begin() as d:
            for i in range(0, len(rows), chunk):
                d.execute(dst_table.insert(), rows[i:i + chunk])
        print(f"   {t:35s} {len(rows):>7} rows")
    print()

    # 3) Postgres SEQUENCE 재설정 (id 자동 발급이 max(id)+1 부터 되도록)
    print("3) sequence 재설정 ...")
    with dst.begin() as d:
        for t in TABLES:
            seq = d.execute(text(
                f"select pg_get_serial_sequence('{t}', 'id')"
            )).scalar()
            if not seq:
                continue
            d.execute(text(
                f"select setval('{seq}', "
                f"  coalesce((select max(id) from {t}), 1), "
                f"  (select max(id) from {t}) is not null)"
            ))
            print(f"   {t} sequence ok")
    print()

    # 4) 결과 확인
    print("4) 마이그레이션 결과:")
    with dst.connect() as d:
        for t in TABLES:
            cnt = d.execute(text(f"select count(*) from {t}")).scalar()
            print(f"   {t:35s} {cnt:>7}")

    print("\n완료.")


if __name__ == "__main__":
    main()
