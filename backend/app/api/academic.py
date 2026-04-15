"""학회 일정 API — 회원학회 마스터 + 학술행사 이벤트."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.connection import get_db
from app.models.database import (
    AcademicEvent,
    AcademicEventDepartment,
    AcademicOrganizer,
    Doctor,
    Hospital,
)
from app.services.academic_mapping import (
    departments_from_json,
    departments_to_json,
)

router = APIRouter(prefix="/api", tags=["학회"])
logger = logging.getLogger(__name__)


_NAME_SUFFIX_RE = re.compile(
    r"\s*(교수|부교수|조교수|전임강사|임상강사|전문의|과장|원장|의사|선생님|센터장|실장|팀장|주임)\s*$"
)

# KMA affiliation 문자열이 학교명 약칭("울산의대", "고려의대", "연세의대")을 쓰는 경우가 많아
# Doctor.hospital.name 과 직접 substring 매칭이 안 된다. 병원 code 기준으로 별칭을 명시.
# 여러 병원을 가진 학교의 school-level 약칭("고려의대", "가톨릭의대" 등)은 flagship 본원에만 배정.
HOSPITAL_ALIASES: dict[str, list[str]] = {
    "서울아산병원": ["서울아산", "아산병원", "울산의대", "울산대학"],
    "고대안암병원": ["고대안암", "고려대안암", "안암병원", "고려의대", "고려대학교 의과대학"],
    "고대구로병원": ["고대구로", "고려대구로", "구로병원"],
    "고대안산병원": ["고대안산", "고려대안산", "안산병원"],
    "세브란스병원": ["세브란스병원", "신촌세브란스", "연세의대", "연세대학교 의과대학"],
    "강남세브란스병원": ["강남세브란스"],
    "서울대학교병원": ["서울대학교병원", "서울대병원", "서울의대", "서울대학교 의과대학"],
    "분당서울대병원": ["분당서울대"],
    "삼성서울병원": ["삼성서울", "성균관의대", "성균관대학교 의과대학", "삼성의료원"],
    "강북삼성병원": ["강북삼성"],
    "서울성모병원": ["서울성모", "가톨릭의대", "가톨릭대학교 의과대학"],
    "여의도성모병원": ["여의도성모"],
    "성빈센트병원": ["성빈센트"],
    "은평성모병원": ["은평성모"],
    "인천성모병원": ["인천성모"],
    "경희대병원": ["경희대학교병원", "경희의대", "경희대병원"],
    "건국대학교병원": ["건국대학교병원", "건국의대", "건국대병원", "건대병원"],
    "중앙대병원": ["중앙대학교병원", "중앙의대", "중앙대병원"],
    "한양대병원": ["한양대학교병원", "한양의대", "한양대병원"],
    "이대목동병원": ["이대목동", "목동병원"],
    "이대서울병원": ["이대서울"],
    "아주대병원": ["아주대학교병원", "아주의대", "아주대병원"],
    "인하대병원": ["인하대학교병원", "인하의대", "인하대병원"],
    "길병원": ["가천대 길", "가천의대", "길병원"],
    "한림성심병원": ["한림대학교 성심", "한림의대 성심", "한림성심"],
    "동국대학교일산병원": ["동국대학교 일산", "동국대일산", "동국의대 일산"],
    "부천순천향병원": ["부천순천향", "순천향대 부천", "순천향 부천"],
    "국립암센터": ["국립암센터"],
    "한국원자력의학원": ["원자력의학원", "원자력병원"],
}


def _alias_match(hospital_name: str, affiliation: str) -> Optional[tuple[int, int]]:
    """affiliation 안에서 hospital 에 해당하는 별칭 중 최장매치의 (pos, length) 반환.

    동점(같은 길이) 은 더 앞쪽 pos 우선. 매칭 없으면 None.
    """
    if not hospital_name or not affiliation:
        return None
    aliases = HOSPITAL_ALIASES.get(hospital_name, [])
    # 기본적으로 hospital_name 자체도 후보에 추가 (alias 없는 병원용 fallback)
    if hospital_name not in aliases:
        aliases = [hospital_name, *aliases]

    best: Optional[tuple[int, int]] = None  # (pos, length)
    for alias in aliases:
        if not alias:
            continue
        pos = affiliation.find(alias)
        if pos < 0:
            continue
        length = len(alias)
        if best is None or length > best[1] or (length == best[1] and pos < best[0]):
            best = (pos, length)
    return best


def _normalize_name(name: str) -> str:
    if not name:
        return ""
    stripped = _NAME_SUFFIX_RE.sub("", name.strip())
    return stripped.strip()


def _parse_lectures_json(raw: Optional[str]) -> list[dict]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


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
        "sub_organizer": e.sub_organizer,
        "region": e.region,
        "event_code": e.event_code,
        "detail_url_external": e.detail_url_external,
        "classification_status": e.classification_status,
        "departments": sorted({d.department for d in e.departments}),
        "lectures": _parse_lectures_json(e.lectures_json),
    }


async def _enrich_lectures_with_doctors(
    lectures: list[dict], db: AsyncSession
) -> list[dict]:
    """강의 리스트에 내 교수(visit_grade A/B/C) 매칭 정보 주입.

    - 이름 정규화(직위 suffix 제거) 후 visit_grade A/B/C 범위에서 완전일치 검색
    - 동명이인이 여러 명이면 affiliation 문자열에 Doctor.hospital.name 이
      substring 으로 포함되는 후보로 좁힘. 여전히 모호하면 매칭 포기.
    """
    if not lectures:
        return lectures

    normalized_names = {
        _normalize_name(lec.get("lecturer") or "") for lec in lectures
    }
    normalized_names.discard("")
    if not normalized_names:
        return lectures

    rows = (await db.execute(
        select(Doctor)
        .options(selectinload(Doctor.hospital))
        .where(
            Doctor.visit_grade.in_(["A", "B", "C"]),
            Doctor.name.in_(normalized_names),
        )
    )).scalars().all()

    by_name: dict[str, list[Doctor]] = {}
    for d in rows:
        by_name.setdefault(d.name, []).append(d)

    enriched: list[dict] = []
    for lec in lectures:
        item = dict(lec)
        name = _normalize_name(lec.get("lecturer") or "")
        candidates = by_name.get(name, [])

        matched: Optional[Doctor] = None
        if len(candidates) == 1:
            matched = candidates[0]
        elif len(candidates) > 1:
            aff = (lec.get("affiliation") or "")
            # 최장매치(길이 내림차순, 동점은 earlier pos) 로 승자 결정
            best_score: Optional[tuple[int, int]] = None  # (length, -pos)
            for c in candidates:
                h_name = (c.hospital.name if c.hospital else "") or ""
                m = _alias_match(h_name, aff)
                if m is None:
                    continue
                pos, length = m
                score = (length, -pos)
                if best_score is None or score > best_score:
                    best_score = score
                    matched = c

        if matched:
            item["matched_doctor_id"] = matched.id
            item["matched_doctor_name"] = matched.name
            item["matched_doctor_grade"] = matched.visit_grade
            item["matched_department"] = matched.department
            item["matched_hospital_name"] = (
                matched.hospital.name if matched.hospital else None
            )
        enriched.append(item)
    return enriched


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
async def sync_events(background: BackgroundTasks):
    """학회 일정 동기화.

    개발 환경(Celery worker 없음) 에서도 동작하도록 FastAPI BackgroundTasks 로
    인라인 실행. Celery beat 가 떠 있으면 매월 자동 스케줄도 별도로 동작.
    """
    from app.tasks.academic_tasks import _crawl_events_async

    async def _run():
        try:
            result = await _crawl_events_async(max_pages=3, kma_scan_back=1500)
            logger.info(f"academic sync done: {result}")
        except Exception as exc:  # pragma: no cover
            logger.exception(f"academic sync failed: {exc}")

    background.add_task(_run)
    return {"status": "dispatched"}


@router.get("/academic-events/{event_id}")
async def get_event(event_id: int, db: AsyncSession = Depends(get_db)):
    event = (await db.execute(
        select(AcademicEvent)
        .options(selectinload(AcademicEvent.departments))
        .where(AcademicEvent.id == event_id)
    )).scalar_one_or_none()
    if not event:
        raise HTTPException(404, "event not found")
    payload = _event_to_dict(event)
    payload["lectures"] = await _enrich_lectures_with_doctors(
        payload["lectures"], db
    )
    return payload


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
