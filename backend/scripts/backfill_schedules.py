"""스케줄 백필 스크립트.

배경: 4월 초 sync_hospital 가 crawl_doctor_list() 만 호출하던 시절(744461e) 들어간
대학병원들이 의사 명단은 있는데 schedules 가 비어있다. 그 뒤 코드는 _fetch_all() 로
바뀌었지만 HTTP sync 가 2~3분 걸려 proxy timeout 으로 끊기는 일이 잦아 재크롤이
사실상 안 되고 있다. 이 스크립트는 HTTP 를 우회해 직접 Python 으로
sync_hospital() 의 본문을 호출해 채운다.

사용법 (backend/ 에서):
    # 한 병원
    python scripts/backfill_schedules.py EUMCMK

    # 여러 병원 순차
    python scripts/backfill_schedules.py EUMCMK EUMCSL AJOUMC GIL INHA

    # 영향받은 대학병원 일괄 (스케줄 0~1% 그룹)
    python scripts/backfill_schedules.py --preset universities

운영 환경에서:
    docker compose exec backend python scripts/backfill_schedules.py --preset universities

DATABASE_URL 환경변수가 운영 PG 를 가리키면 그쪽으로, 없으면 로컬 SQLite 로 적용된다.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.api.crawl import sync_hospital
from app.models.connection import async_session


# 4/8 옛 sync 코드로 들어와 스케줄 비어있는 대학병원 그룹.
# pharma_scheduler.db 의 doctor_schedules 통계 기준 (스케줄 보유율 ≤ 1%).
UNIVERSITY_PRESET = [
    "AMC", "SMC", "CMCSEOUL", "SNUH", "SNUBH", "SEVERANCE",
    "AJOUMC", "KUANAM", "GIL", "INHA", "CMCIC", "CMCSV",
    "KUH", "CAU", "HALLYM", "CMCEP", "KHU", "GANSEV",
    "EUMCMK", "EUMCSL", "CMCYD", "KUANSAN", "DUIH",
    "SCHBC", "KCCH", "NCC",
]


async def backfill_one(code: str) -> dict:
    t0 = time.time()
    async with async_session() as db:
        try:
            result = await sync_hospital(code, department="", db=db)
            elapsed = time.time() - t0
            print(
                f"[{code}] OK  {elapsed:6.1f}s  "
                f"total={result['total_crawled']:>4}  "
                f"created={result['created']:>4}  "
                f"updated={result['updated']:>4}  "
                f"sched={result['schedules_saved']:>5}"
            )
            return {"code": code, "status": "ok", "elapsed": elapsed, "result": result}
        except Exception as e:
            elapsed = time.time() - t0
            print(f"[{code}] FAIL {elapsed:6.1f}s  {type(e).__name__}: {e}")
            await db.rollback()
            return {"code": code, "status": "fail", "elapsed": elapsed, "error": str(e)}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("codes", nargs="*", help="병원 코드 (예: EUMCMK EUMCSL)")
    ap.add_argument(
        "--preset",
        choices=["universities"],
        help="사전 정의된 그룹 (universities = 스케줄 비어있는 대학병원 26개)",
    )
    args = ap.parse_args()

    if args.preset == "universities":
        codes = UNIVERSITY_PRESET
    elif args.codes:
        codes = args.codes
    else:
        ap.error("병원 코드 또는 --preset 지정 필요")
        return

    print(f"백필 대상 {len(codes)}개: {', '.join(codes)}")
    print()
    t0 = time.time()
    summary = []
    for code in codes:
        summary.append(await backfill_one(code))

    print()
    print(f"전체 소요 {time.time() - t0:.1f}s")
    ok = sum(1 for s in summary if s["status"] == "ok")
    print(f"성공 {ok}/{len(summary)}")
    failed = [s for s in summary if s["status"] != "ok"]
    if failed:
        print("실패:")
        for s in failed:
            print(f"  {s['code']}: {s.get('error', '?')}")


if __name__ == "__main__":
    asyncio.run(main())
