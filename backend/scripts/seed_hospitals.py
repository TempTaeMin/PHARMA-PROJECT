"""factory.py 의 _DEDICATED_CRAWLERS + _HOSPITAL_REGION 으로 hospitals 테이블 upsert.

신규 크롤러 추가 후 실행하면 누락된 병원을 hospitals 테이블에 INSERT.
이미 있는 병원은 region 만 갱신 (변경된 경우).
"""
import asyncio
import os
import sys
from datetime import datetime

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(THIS_DIR)
sys.path.insert(0, BACKEND_DIR)

import io
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from sqlalchemy import select
from app.models.connection import engine, async_session
from app.models.database import Hospital
from app.crawlers.factory import _DEDICATED_CRAWLERS, _HOSPITAL_REGION


async def run():
    inserted = 0
    updated_region = 0
    skipped = 0

    async with async_session() as session:
        for code, (_, name) in _DEDICATED_CRAWLERS.items():
            region = _HOSPITAL_REGION.get(code, "")
            existing = (await session.execute(
                select(Hospital).where(Hospital.code == code)
            )).scalar_one_or_none()

            if existing:
                changed = False
                if not existing.region and region:
                    existing.region = region
                    changed = True
                # name 이 비어있는 row 만 보정 (기존 사용자 입력 보호)
                if not existing.name and name:
                    existing.name = name
                    changed = True
                if changed:
                    existing.updated_at = datetime.utcnow()
                    updated_region += 1
                else:
                    skipped += 1
            else:
                hospital = Hospital(
                    name=name,
                    code=code,
                    region=region,
                    crawler_type="dedicated",
                    source="crawler",
                    is_active=True,
                )
                session.add(hospital)
                inserted += 1
                print(f"[insert] {code} ({region or '?'}) — {name}")

        await session.commit()

    print(f"\n[done] inserted={inserted}, region_updated={updated_region}, skipped={skipped}")


if __name__ == "__main__":
    asyncio.run(run())
