"""1회성 마이그레이션.

과거에 프론트엔드가 `new Date(localStr).toISOString()` 으로 UTC 변환 후 저장해서
`visit_logs.visit_date` 가 naive UTC 로 들어가 있음. 이를 로컬 시간대로 shift
(naive local 로 다시 기록) 하여 화면에 입력한 시각과 일치시킨다.

사용: python backend/scripts/fix_visit_tz.py
"""
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "pharma_scheduler.db"


def main():
    if not DB.exists():
        print(f"DB not found: {DB}", file=sys.stderr)
        sys.exit(1)

    # 로컬 시간대 결정 (시스템 기준)
    local_tz = datetime.now().astimezone().tzinfo
    print(f"[info] local tz = {local_tz}")

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    rows = cur.execute("SELECT id, visit_date FROM visit_logs WHERE visit_date IS NOT NULL").fetchall()
    print(f"[info] rows to process: {len(rows)}")

    updated = 0
    samples = []
    for row in rows:
        raw = row["visit_date"]
        if not raw:
            continue
        # SQLite returns as text/naive; parse
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:
            # 혹시 타임존 문자열이 있는 경우
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))

        if dt.tzinfo is not None:
            # aware → 이미 이전에 처리된 경우: 로컬로 맞추고 naive 기록
            local = dt.astimezone(local_tz).replace(tzinfo=None)
        else:
            # naive UTC 로 간주 → 로컬로 shift
            local = dt.replace(tzinfo=timezone.utc).astimezone(local_tz).replace(tzinfo=None)

        new_raw = local.isoformat(sep=" ")
        if len(samples) < 5:
            samples.append((row["id"], raw, new_raw))
        cur.execute(
            "UPDATE visit_logs SET visit_date = ? WHERE id = ?",
            (new_raw, row["id"]),
        )
        updated += 1

    conn.commit()
    conn.close()

    print(f"[done] updated {updated} rows")
    if samples:
        print("[samples]")
        for s in samples:
            print(f"  id={s[0]}  {s[1]}  ->  {s[2]}")


if __name__ == "__main__":
    main()
