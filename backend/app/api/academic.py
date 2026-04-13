"""학회 일정 API — 회원학회 마스터 + 학술행사 이벤트."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.connection import get_db
from app.models.database import (
    AcademicEvent,
    AcademicEventDepartment,
    AcademicOrganizer,
)
from app.services.academic_mapping import (
    departments_from_json,
    departments_to_json,
)

router = APIRouter(prefix="/api", tags=["학회"])


def _event_to_dict(e: AcademicEvent) -> dict:
    return {
        "id": e.id,
        "name": e.name,
        "organizer_name": e.organizer_name,
        "organizer_id": e.organizer_id,
        "start_date": e.start_date,
        "end_date": e.end_date,
        "location": e.location,
        "url": e.url,
        "description": e.description,
        "source": e.source,
        "kma_category": e.kma_category,
        "kma_eduidx": e.kma_eduidx,
        "classification_status": e.classification_status,
        "departments": sorted({d.department for d in e.departments}),
    }


def _organizer_to_dict(o: AcademicOrganizer) -> dict:
    return {
        "id": o.id,
        "name": o.name,
        "name_en": o.name_en,
        "domain": o.domain,
        "membership_type": o.membership_type,
        "homepage": o.homepage,
        "departments": departments_from_json(o.departments_json),
        "classification_status": o.classification_status,
    }


# ============================================================
# Events
# ============================================================
@router.get("/academic-events/")
async def list_events(
    department: Optional[str] = None,
    start_from: Optional[str] = None,
    start_to: Optional[str] = None,
    status: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = Query(200, le=2000),
    db: AsyncSession = Depends(get_db),
):
    query = select(AcademicEvent).options(selectinload(AcademicEvent.departments))

    if department:
        query = query.join(AcademicEventDepartment).where(
            AcademicEventDepartment.department == department
        )
    if start_from:
        query = query.where(AcademicEvent.start_date >= start_from)
    if start_to:
        query = query.where(AcademicEvent.start_date <= start_to)
    if status:
        query = query.where(AcademicEvent.classification_status == status)
    if source:
        query = query.where(AcademicEvent.source == source)

    query = query.order_by(AcademicEvent.start_date.asc()).limit(limit)
    rows = (await db.execute(query)).scalars().unique().all()
    return [_event_to_dict(e) for e in rows]


@router.get("/academic-events/upcoming")
async def list_upcoming_events(
    department: Optional[str] = None,
    source: Optional[str] = None,
    months: int = Query(3, ge=1, le=12),
    db: AsyncSession = Depends(get_db),
):
    today = datetime.now().strftime("%Y-%m-%d")
    end = (datetime.now() + timedelta(days=30 * months)).strftime("%Y-%m-%d")

    query = (
        select(AcademicEvent)
        .options(selectinload(AcademicEvent.departments))
        .where(
            AcademicEvent.start_date >= today,
            AcademicEvent.start_date <= end,
        )
    )
    if department:
        query = query.join(AcademicEventDepartment).where(
            AcademicEventDepartment.department == department
        )
    if source:
        query = query.where(AcademicEvent.source == source)
    query = query.order_by(AcademicEvent.start_date.asc())

    rows = (await db.execute(query)).scalars().unique().all()
    return [_event_to_dict(e) for e in rows]


@router.get("/academic-events/unclassified")
async def list_unclassified_events(db: AsyncSession = Depends(get_db)):
    query = (
        select(AcademicEvent)
        .options(selectinload(AcademicEvent.departments))
        .where(AcademicEvent.classification_status == "unclassified")
        .order_by(AcademicEvent.start_date.asc())
    )
    rows = (await db.execute(query)).scalars().unique().all()
    return [_event_to_dict(e) for e in rows]


@router.post("/academic-events/sync")
async def sync_events():
    from app.tasks.academic_tasks import crawl_academic_events
    task = crawl_academic_events.delay()
    return {"task_id": task.id, "status": "dispatched"}


@router.patch("/academic-events/{event_id}/departments")
async def update_event_departments(
    event_id: int,
    payload: dict,
    db: AsyncSession = Depends(get_db),
):
    departments = payload.get("departments") or []
    event = (await db.execute(
        select(AcademicEvent)
        .options(selectinload(AcademicEvent.departments))
        .where(AcademicEvent.id == event_id)
    )).scalar_one_or_none()
    if not event:
        raise HTTPException(404, "event not found")

    event.departments.clear()
    for d in departments:
        event.departments.append(AcademicEventDepartment(department=d))
    event.classification_status = "mapped" if departments else "unclassified"
    event.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(event)
    return _event_to_dict(event)


# ============================================================
# Organizers
# ============================================================
@router.get("/academic-organizers/")
async def list_organizers(
    status: Optional[str] = None,
    domain: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(AcademicOrganizer)
    if status:
        query = query.where(AcademicOrganizer.classification_status == status)
    if domain:
        query = query.where(AcademicOrganizer.domain == domain)
    query = query.order_by(AcademicOrganizer.domain, AcademicOrganizer.name)
    rows = (await db.execute(query)).scalars().all()
    return [_organizer_to_dict(o) for o in rows]


@router.post("/academic-organizers/seed")
async def seed_organizers():
    from app.tasks.academic_tasks import seed_academic_organizers
    task = seed_academic_organizers.delay()
    return {"task_id": task.id, "status": "dispatched"}


@router.patch("/academic-organizers/{org_id}/departments")
async def update_organizer_departments(
    org_id: int,
    payload: dict,
    db: AsyncSession = Depends(get_db),
):
    departments = payload.get("departments") or []
    org = (await db.execute(
        select(AcademicOrganizer).where(AcademicOrganizer.id == org_id)
    )).scalar_one_or_none()
    if not org:
        raise HTTPException(404, "organizer not found")

    org.departments_json = departments_to_json(departments)
    org.classification_status = "mapped" if departments else "unclassified"
    org.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(org)
    return _organizer_to_dict(org)
