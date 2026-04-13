"""학회 마스터/이벤트 Celery 태스크.

- seed_academic_organizers: KAMS 회원학회 마스터 리스트 재구축 (연 1회 / 수동)
- crawl_academic_events: healthmedia 학술행사 월간 크롤링 (매월 1일)
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.tasks.celery_app import celery_app
from app.models.connection import async_session
from app.models.database import (
    AcademicEvent,
    AcademicEventDepartment,
    AcademicOrganizer,
)
from app.crawlers.academic.kams_organizer_crawler import KamsOrganizerCrawler
from app.crawlers.academic.healthmedia_event_crawler import HealthmediaEventCrawler
from app.crawlers.academic.kma_edu_crawler import KmaEduCrawler
from app.services.academic_mapping import (
    departments_from_json,
    departments_to_json,
    extract_departments,
    resolve_event,
)

logger = logging.getLogger(__name__)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_external_key(
    source: str, organizer: str | None, name: str, start_date: str | None
) -> str:
    raw = f"{source}|{organizer or ''}|{name}|{start_date or ''}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:32]


# ============================================================
# seed_academic_organizers
# ============================================================
@celery_app.task(name="app.tasks.academic_tasks.seed_academic_organizers")
def seed_academic_organizers() -> dict:
    """KAMS 회원학회 전체 재구축."""
    return _run_async(_seed_async())


async def _seed_async() -> dict:
    crawler = KamsOrganizerCrawler()
    raw = await crawler.crawl_organizers()
    if not raw:
        return {"status": "empty", "total": 0}

    stats = {"total": 0, "mapped": 0, "unclassified": 0, "created": 0, "updated": 0}

    async with async_session() as db:  # type: AsyncSession
        for item in raw:
            name = item["name"]
            depts, status = extract_departments(name)
            stats["total"] += 1
            if status == "keyword":
                stats["mapped"] += 1
            else:
                stats["unclassified"] += 1

            existing = (await db.execute(
                select(AcademicOrganizer).where(AcademicOrganizer.name == name)
            )).scalar_one_or_none()

            if existing:
                existing.name_en = item.get("name_en") or existing.name_en
                existing.domain = item.get("domain") or existing.domain
                existing.membership_type = item.get("membership_type") or existing.membership_type
                existing.homepage = item.get("homepage") or existing.homepage
                # classification_status 가 mapped(수동 override) 면 키워드 재계산 덮어쓰지 않음
                if existing.classification_status != "mapped":
                    existing.departments_json = departments_to_json(depts)
                    existing.classification_status = status
                existing.updated_at = datetime.utcnow()
                stats["updated"] += 1
            else:
                org = AcademicOrganizer(
                    name=name,
                    name_en=item.get("name_en"),
                    domain=item.get("domain"),
                    membership_type=item.get("membership_type"),
                    homepage=item.get("homepage"),
                    departments_json=departments_to_json(depts),
                    classification_status=status,
                )
                db.add(org)
                stats["created"] += 1
        await db.commit()

    logger.info(f"seed_academic_organizers: {stats}")
    return {"status": "ok", **stats}


# ============================================================
# crawl_academic_events
# ============================================================
@celery_app.task(name="app.tasks.academic_tasks.crawl_academic_events")
def crawl_academic_events(max_pages: int = 3, kma_scan_back: int = 1500) -> dict:
    """healthmedia + KMA 에서 학술행사 이벤트 크롤링 + DB 저장."""
    return _run_async(_crawl_events_async(max_pages, kma_scan_back))


async def _crawl_events_async(max_pages: int, kma_scan_back: int = 1500) -> dict:
    # 1. organizer lookup
    async with async_session() as db:  # type: AsyncSession
        rows = (await db.execute(select(AcademicOrganizer))).scalars().all()
        lookup: dict[str, list[str]] = {
            row.name: departments_from_json(row.departments_json) for row in rows
        }

    logger.info(f"crawl_academic_events: organizer lookup size={len(lookup)}")

    # 2. 두 소스 병렬 크롤링
    hm_result, kma_result = await asyncio.gather(
        HealthmediaEventCrawler().crawl_events(max_pages=max_pages),
        KmaEduCrawler().crawl_events(months_ahead=3, scan_back=kma_scan_back),
        return_exceptions=True,
    )

    events_by_source: list[tuple[str, list[dict]]] = []
    if isinstance(hm_result, Exception):
        logger.error(f"healthmedia crawl failed: {hm_result}")
        events_by_source.append(("healthmedia", []))
    else:
        events_by_source.append(("healthmedia", hm_result))
    if isinstance(kma_result, Exception):
        logger.error(f"kma_edu crawl failed: {kma_result}")
        events_by_source.append(("kma_edu", []))
    else:
        events_by_source.append(("kma_edu", kma_result))

    stats = {
        "total": 0,
        "new": 0,
        "updated": 0,
        "kma": 0,
        "mapped": 0,
        "keyword": 0,
        "unclassified": 0,
        "by_source": {src: len(evts) for src, evts in events_by_source},
    }

    # 3. DB 저장
    async with async_session() as db:
        for source, events in events_by_source:
            for e in events:
                organizer_name = e.get("organizer")
                name = e.get("name")
                start_date = e.get("start_date")
                if not name or not start_date:
                    continue
                stats["total"] += 1

                kma_category = e.get("kma_category")
                depts, status = resolve_event(
                    organizer_name, name, lookup, kma_category=kma_category
                )
                stats[status] = stats.get(status, 0) + 1

                external_key = _make_external_key(source, organizer_name, name, start_date)

                existing = (await db.execute(
                    select(AcademicEvent)
                    .options(selectinload(AcademicEvent.departments))
                    .where(AcademicEvent.external_key == external_key)
                )).scalar_one_or_none()

                organizer_id = None
                if organizer_name:
                    org_row = (await db.execute(
                        select(AcademicOrganizer).where(AcademicOrganizer.name == organizer_name)
                    )).scalar_one_or_none()
                    if org_row:
                        organizer_id = org_row.id

                if existing:
                    existing.name = name
                    existing.organizer_name = organizer_name
                    existing.organizer_id = organizer_id
                    existing.start_date = start_date
                    existing.end_date = e.get("end_date") or start_date
                    existing.location = e.get("location")
                    existing.url = e.get("url")
                    existing.description = e.get("description")
                    existing.source = source
                    existing.kma_category = kma_category
                    existing.kma_eduidx = e.get("eduidx")
                    existing.classification_status = status
                    existing.updated_at = datetime.utcnow()
                    existing.departments.clear()
                    for dept in depts:
                        existing.departments.append(
                            AcademicEventDepartment(department=dept)
                        )
                    stats["updated"] += 1
                else:
                    event = AcademicEvent(
                        name=name,
                        organizer_name=organizer_name,
                        organizer_id=organizer_id,
                        start_date=start_date,
                        end_date=e.get("end_date") or start_date,
                        location=e.get("location"),
                        url=e.get("url"),
                        description=e.get("description"),
                        source=source,
                        kma_category=kma_category,
                        kma_eduidx=e.get("eduidx"),
                        classification_status=status,
                        external_key=external_key,
                    )
                    event.departments = [
                        AcademicEventDepartment(department=d) for d in depts
                    ]
                    db.add(event)
                    stats["new"] += 1

        await db.commit()

    logger.info(f"crawl_academic_events: {stats}")
    return {"status": "ok", **stats}
