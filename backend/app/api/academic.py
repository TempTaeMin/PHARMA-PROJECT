"""학회 일정 API — 회원학회 마스터 + 학술행사 이벤트."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.deps import get_current_user, get_my_team_id
from app.models.connection import get_db
from app.models.database import (
    AcademicEvent,
    AcademicEventDepartment,
    AcademicOrganizer,
    Doctor,
    Hospital,
    TeamAcademicPin,
    User,
    UserAcademicPin,
    UserDoctorGrade,
)
from app.services.academic_mapping import (
    departments_from_json,
    departments_to_json,
    resolve_event,
)

router = APIRouter(prefix="/api", tags=["학회"])
logger = logging.getLogger(__name__)


_NAME_SUFFIX_RE = re.compile(
    r"\s*(교수|부교수|조교수|전임강사|임상강사|전문의|과장|원장|의사|선생님|센터장|실장|팀장|주임)\s*$"
)

# 병원 고유 별칭 — 병원 자체의 통용명/축약형. 학교명 약칭은 MEDICAL_SCHOOL_GROUPS 참조.
HOSPITAL_ALIASES: dict[str, list[str]] = {
    "서울아산병원": ["서울아산", "아산병원"],
    "고대안암병원": ["고대안암", "고려대안암", "안암병원"],
    "고대구로병원": ["고대구로", "고려대구로", "구로병원"],
    "고대안산병원": ["고대안산", "고려대안산", "안산병원"],
    "세브란스병원": ["세브란스병원", "신촌세브란스"],
    "강남세브란스병원": ["강남세브란스"],
    "서울대학교병원": ["서울대학교병원", "서울대병원"],
    "분당서울대병원": ["분당서울대"],
    "삼성서울병원": ["삼성서울", "삼성의료원"],
    "강북삼성병원": ["강북삼성"],
    "서울성모병원": ["서울성모"],
    "여의도성모병원": ["여의도성모"],
    "성빈센트병원": ["성빈센트"],
    "은평성모병원": ["은평성모"],
    "인천성모병원": ["인천성모"],
    "경희대병원": ["경희대학교병원", "경희대병원"],
    "건국대학교병원": ["건국대학교병원", "건국대병원", "건대병원"],
    "중앙대병원": ["중앙대학교병원", "중앙대병원"],
    "한양대병원": ["한양대학교병원", "한양대병원"],
    "이대목동병원": ["이대목동", "목동병원"],
    "이대서울병원": ["이대서울"],
    "아주대병원": ["아주대학교병원", "아주대병원"],
    "인하대병원": ["인하대학교병원", "인하대병원"],
    "길병원": ["가천대 길", "길병원"],
    "한림성심병원": ["한림대학교 성심", "한림의대 성심", "한림성심"],
    "동국대학교일산병원": ["동국대학교 일산", "동국대일산", "동국의대 일산"],
    "부천순천향병원": ["부천순천향", "순천향대 부천", "순천향 부천"],
    "국립암센터": ["국립암센터"],
    "한국원자력의학원": ["원자력의학원", "원자력병원"],
}


#  
# affiliation 에 학교 약칭이 포함되면 해당 그룹의 **모든 병원**이 후보로 간주된다.
# (ex) "고려의대 내과 이OO" → 고대안암/고대구로/고대안산 교수 모두 매칭 가능.
MEDICAL_SCHOOL_GROUPS: dict[str, list[str]] = {
    "고려의대":              ["고대안암병원", "고대구로병원", "고대안산병원"],
    "고려대학교 의과대학":   ["고대안암병원", "고대구로병원", "고대안산병원"],
    "고려대학교":            ["고대안암병원", "고대구로병원", "고대안산병원"],
    "가톨릭의대":            ["서울성모병원", "여의도성모병원", "성빈센트병원", "은평성모병원", "인천성모병원"],
    "가톨릭대학교 의과대학": ["서울성모병원", "여의도성모병원", "성빈센트병원", "은평성모병원", "인천성모병원"],
    "연세의대":              ["세브란스병원", "강남세브란스병원"],
    "연세대학교 의과대학":   ["세브란스병원", "강남세브란스병원"],
    "연세대학교":            ["세브란스병원", "강남세브란스병원"],
    "서울의대":              ["서울대학교병원", "분당서울대병원"],
    "서울대학교 의과대학":   ["서울대학교병원", "분당서울대병원"],
    "성균관의대":            ["삼성서울병원", "강북삼성병원"],
    "성균관대학교 의과대학": ["삼성서울병원", "강북삼성병원"],
    "울산의대":              ["서울아산병원", "강릉아산병원"],
    "울산대학교 의과대학":   ["서울아산병원", "강릉아산병원"],
    "울산대학교":            ["서울아산병원", "강릉아산병원"],
    "경희의대":              ["경희대병원"],
    "경희대학교 의과대학":   ["경희대병원"],
    "건국의대":              ["건국대학교병원"],
    "건국대학교 의과대학":   ["건국대학교병원"],
    "중앙의대":              ["중앙대병원"],
    "중앙대학교 의과대학":   ["중앙대병원"],
    "한양의대":              ["한양대병원"],
    "한양대학교 의과대학":   ["한양대병원"],
    "아주의대":              ["아주대병원"],
    "아주대학교 의과대학":   ["아주대병원"],
    "인하의대":              ["인하대병원"],
    "인하대학교 의과대학":   ["인하대병원"],
    "가천의대":              ["길병원"],
    "가천대학교 의과대학":   ["길병원"],
}


def _school_aliases_for(hospital_name: str) -> list[str]:
    """hospital_name 이 속한 학교 그룹의 모든 약칭 키를 반환."""
    if not hospital_name:
        return []
    return [alias for alias, hospitals in MEDICAL_SCHOOL_GROUPS.items() if hospital_name in hospitals]


def _alias_match(hospital_name: str, affiliation: str) -> Optional[tuple[int, int]]:
    """affiliation 안에서 hospital 에 해당하는 별칭 중 최장매치의 (pos, length) 반환.

    동점(같은 길이) 은 더 앞쪽 pos 우선. 매칭 없으면 None.

    매칭 후보: 병원 자체 이름 + HOSPITAL_ALIASES 고유 별칭 + 소속 의대 그룹 약칭.
    """
    if not hospital_name or not affiliation:
        return None
    aliases: list[str] = list(HOSPITAL_ALIASES.get(hospital_name, []))
    # 기본적으로 hospital_name 자체도 후보에 추가 (alias 없는 병원용 fallback)
    if hospital_name not in aliases:
        aliases.insert(0, hospital_name)
    # 학교 그룹 약칭 병합
    aliases.extend(_school_aliases_for(hospital_name))

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


def _event_to_dict(
    e: AcademicEvent,
    pinned_event_ids: Optional[set[int]] = None,
    team_pinned_event_ids: Optional[set[int]] = None,
    team_pin_owner_map: Optional[dict[int, dict]] = None,
) -> dict:
    """is_pinned 는 사용자 핀 OR 팀 핀. 별도 플래그도 함께 반환."""
    pinned_by_user = bool(pinned_event_ids and e.id in pinned_event_ids)
    pinned_by_team = bool(team_pinned_event_ids and e.id in team_pinned_event_ids)
    owner = (team_pin_owner_map or {}).get(e.id) if pinned_by_team else None
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
        "is_pinned": pinned_by_user or pinned_by_team,
        "is_pinned_by_user": pinned_by_user,
        "is_pinned_by_team": pinned_by_team,
        "team_pinned_by_user_id": owner.get("user_id") if owner else None,
        "team_pinned_by_name": owner.get("user_name") if owner else None,
        "departments": sorted({d.department for d in e.departments}),
        "lectures": _parse_lectures_json(e.lectures_json),
        "updated_at": e.updated_at.isoformat() if e.updated_at else None,
        "created_at": e.created_at.isoformat() if getattr(e, "created_at", None) else None,
    }


async def _user_pinned_event_ids(
    db: AsyncSession, user_id: int, event_ids: Optional[list[int]] = None
) -> set[int]:
    q = select(UserAcademicPin.event_id).where(UserAcademicPin.user_id == user_id)
    if event_ids:
        q = q.where(UserAcademicPin.event_id.in_(event_ids))
    rows = (await db.execute(q)).scalars().all()
    return set(rows)


async def _team_pin_owner_map(
    db: AsyncSession, team_id: Optional[int], event_ids: Optional[list[int]] = None
) -> dict[int, dict]:
    """팀 핀된 event_id → {user_id, user_name} 매핑. 카드/상세에서 '누가 공유했나' 표시용."""
    if not team_id or not event_ids:
        return {}
    q = (
        select(TeamAcademicPin.event_id, TeamAcademicPin.pinned_by_user_id, User.name)
        .outerjoin(User, User.id == TeamAcademicPin.pinned_by_user_id)
        .where(TeamAcademicPin.team_id == team_id, TeamAcademicPin.event_id.in_(event_ids))
    )
    rows = (await db.execute(q)).all()
    return {ev_id: {"user_id": uid, "user_name": uname} for ev_id, uid, uname in rows}


async def _team_pinned_event_ids(
    db: AsyncSession, team_id: Optional[int], event_ids: Optional[list[int]] = None
) -> set[int]:
    if not team_id:
        return set()
    q = select(TeamAcademicPin.event_id).where(TeamAcademicPin.team_id == team_id)
    if event_ids:
        q = q.where(TeamAcademicPin.event_id.in_(event_ids))
    rows = (await db.execute(q)).scalars().all()
    return set(rows)


async def _user_graded_doctor_ids_in_names(
    db: AsyncSession, user_id: int, names: set[str]
) -> dict[str, list[Doctor]]:
    """현재 사용자가 등급 매긴 의사 중 이름이 names 에 포함되는 후보 dict.
    Doctor.visit_grade 글로벌 컬럼 사용을 UserDoctorGrade 로 대체."""
    if not names:
        return {}
    sub = select(UserDoctorGrade.doctor_id).where(UserDoctorGrade.user_id == user_id)
    rows = (await db.execute(
        select(Doctor)
        .options(selectinload(Doctor.hospital))
        .where(Doctor.id.in_(sub), Doctor.name.in_(names))
    )).scalars().all()
    by_name: dict[str, list[Doctor]] = {}
    for d in rows:
        by_name.setdefault(d.name, []).append(d)
    return by_name


async def _summarize_matched_lecturers(
    events: list[AcademicEvent], db: AsyncSession, user_id: int
) -> dict[int, dict]:
    """여러 event 의 lectures_json 을 일괄 파싱 + Doctor 테이블 1회 SELECT 로
    {event_id: {count, names}} 맵 반환. N+1 회피.
    """
    if not events:
        return {}

    per_event: dict[int, list[dict]] = {}
    all_names: set[str] = set()
    for e in events:
        lectures = _parse_lectures_json(e.lectures_json)
        per_event[e.id] = lectures
        for lec in lectures:
            n = _normalize_name(lec.get("lecturer") or "")
            if n:
                all_names.add(n)

    if not all_names:
        return {e.id: {"count": 0, "names": []} for e in events}

    by_name = await _user_graded_doctor_ids_in_names(db, user_id, all_names)

    summary: dict[int, dict] = {}
    for e in events:
        matched_ids: set[int] = set()
        matched_names_ordered: list[str] = []
        for lec in per_event.get(e.id, []):
            name = _normalize_name(lec.get("lecturer") or "")
            candidates = by_name.get(name, [])
            matched = _pick_candidate(candidates, lec.get("affiliation") or "")
            if matched and matched.id not in matched_ids:
                matched_ids.add(matched.id)
                matched_names_ordered.append(matched.name)
        summary[e.id] = {
            "count": len(matched_ids),
            "names": matched_names_ordered,
        }
    return summary


def _pick_candidate(candidates: list[Doctor], affiliation: str) -> Optional[Doctor]:
    """이름 일치 후보 중에서 affiliation 으로 유일 매칭을 결정.

    - 후보 0명 → None
    - affiliation 이 비어 있으면:
        · 후보 1명 → 그대로 채택 (크롤러가 affiliation 을 놓친 경우 기존 동작 유지)
        · 후보 2명↑ → 변별 불가, None
    - affiliation 이 있으면:
        · 각 후보에 대해 _alias_match 시도 → 최장매치 후보 채택
        · 아무도 매치되지 않으면 None (동명이인 오매칭 방지 — 단일 후보라도 버린다)
    """
    if not candidates:
        return None
    aff = (affiliation or "").strip()
    if not aff:
        return candidates[0] if len(candidates) == 1 else None

    best: Optional[Doctor] = None
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
            best = c
    return best


async def _organizer_homepages(
    organizer_ids: set[int], db: AsyncSession
) -> dict[int, str]:
    """organizer_id → homepage 맵. 빈 입력이면 {}."""
    ids = {oid for oid in organizer_ids if oid}
    if not ids:
        return {}
    rows = (await db.execute(
        select(AcademicOrganizer.id, AcademicOrganizer.homepage)
        .where(AcademicOrganizer.id.in_(ids))
    )).all()
    return {row[0]: row[1] for row in rows if row[1]}


async def _enrich_events_with_summary(
    events: list[AcademicEvent], db: AsyncSession, user_id: int
) -> list[dict]:
    """list/upcoming/unclassified 공통 응답 빌더.
    각 event 에 matched_doctor_count/names, organizer_homepage, is_pinned(user/team),
    team_pinned_by_name 주입.
    """
    event_ids = [e.id for e in events]
    pinned = await _user_pinned_event_ids(db, user_id, event_ids)
    team_id = await get_my_team_id(db, user_id)
    team_pinned = await _team_pinned_event_ids(db, team_id, event_ids)
    team_pin_owners = await _team_pin_owner_map(db, team_id, event_ids)
    matched = await _summarize_matched_lecturers(events, db, user_id)
    homepages = await _organizer_homepages(
        {e.organizer_id for e in events if e.organizer_id}, db
    )
    result = []
    for e in events:
        d = _event_to_dict(
            e,
            pinned_event_ids=pinned,
            team_pinned_event_ids=team_pinned,
            team_pin_owner_map=team_pin_owners,
        )
        m = matched.get(e.id, {"count": 0, "names": []})
        d["matched_doctor_count"] = m["count"]
        d["matched_doctor_names"] = m["names"]
        d["organizer_homepage"] = homepages.get(e.organizer_id) if e.organizer_id else None
        result.append(d)
    return result


async def _enrich_lectures_with_doctors(
    lectures: list[dict], db: AsyncSession, user_id: int
) -> list[dict]:
    """강의 리스트에 내 교수(UserDoctorGrade A/B/C, 현재 사용자) 매칭 정보 주입."""
    if not lectures:
        return lectures

    normalized_names = {
        _normalize_name(lec.get("lecturer") or "") for lec in lectures
    }
    normalized_names.discard("")
    if not normalized_names:
        return lectures

    by_name = await _user_graded_doctor_ids_in_names(db, user_id, normalized_names)

    # matched_doctor_grade 도 사용자별 — 한 번에 조회
    all_doctor_ids = [d.id for ds in by_name.values() for d in ds]
    grade_rows = (await db.execute(
        select(UserDoctorGrade).where(
            UserDoctorGrade.user_id == user_id,
            UserDoctorGrade.doctor_id.in_(all_doctor_ids) if all_doctor_ids else False,
        )
    )).scalars().all() if all_doctor_ids else []
    grade_map = {g.doctor_id: g.grade for g in grade_rows}

    enriched: list[dict] = []
    for lec in lectures:
        item = dict(lec)
        name = _normalize_name(lec.get("lecturer") or "")
        candidates = by_name.get(name, [])
        matched = _pick_candidate(candidates, lec.get("affiliation") or "")

        if matched:
            item["matched_doctor_id"] = matched.id
            item["matched_doctor_name"] = matched.name
            item["matched_doctor_grade"] = grade_map.get(matched.id)
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
    user: User = Depends(get_current_user),
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
    return await _enrich_events_with_summary(list(rows), db, user.id)


@router.get("/academic-events/upcoming")
async def list_upcoming_events(
    department: Optional[str] = None,
    source: Optional[str] = None,
    months: int = Query(3, ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
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
    return await _enrich_events_with_summary(list(rows), db, user.id)


@router.get("/academic-events/unclassified")
async def list_unclassified_events(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = (
        select(AcademicEvent)
        .options(selectinload(AcademicEvent.departments))
        .where(AcademicEvent.classification_status == "unclassified")
        .order_by(AcademicEvent.start_date.asc())
    )
    rows = (await db.execute(query)).scalars().unique().all()
    return await _enrich_events_with_summary(list(rows), db, user.id)


@router.get("/academic-events/my-schedule")
async def list_my_schedule_events(
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Schedule.jsx 월간 아젠다용. source='manual' OR 사용자/팀 pin 합집합."""
    pinned_sub = select(UserAcademicPin.event_id).where(UserAcademicPin.user_id == user.id)
    team_id = await get_my_team_id(db, user.id)
    pin_conditions = [
        AcademicEvent.source == "manual",
        AcademicEvent.id.in_(pinned_sub),
    ]
    if team_id:
        team_pinned_sub = select(TeamAcademicPin.event_id).where(TeamAcademicPin.team_id == team_id)
        pin_conditions.append(AcademicEvent.id.in_(team_pinned_sub))
    query = (
        select(AcademicEvent)
        .options(selectinload(AcademicEvent.departments))
        .where(
            AcademicEvent.start_date >= start,
            AcademicEvent.start_date <= end,
            or_(*pin_conditions),
        )
        .order_by(AcademicEvent.start_date.asc())
    )
    rows = (await db.execute(query)).scalars().unique().all()
    return await _enrich_events_with_summary(list(rows), db, user.id)


@router.get("/academic-events/my-lecturers")
async def list_my_lecturer_events(
    months: int = Query(1, ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """향후 N개월 중 내 교수(현재 사용자가 등급 매긴 의사) 가 강사로 참여하는 이벤트."""
    today = datetime.now().strftime("%Y-%m-%d")
    end = (datetime.now() + timedelta(days=30 * months)).strftime("%Y-%m-%d")
    query = (
        select(AcademicEvent)
        .options(selectinload(AcademicEvent.departments))
        .where(
            AcademicEvent.start_date >= today,
            AcademicEvent.start_date <= end,
        )
        .order_by(AcademicEvent.start_date.asc())
    )
    rows = list((await db.execute(query)).scalars().unique().all())
    matched = await _summarize_matched_lecturers(rows, db, user.id)
    out: list[dict] = []
    for e in rows:
        m = matched.get(e.id, {"count": 0, "names": []})
        if m["count"] <= 0:
            continue
        out.append({
            "id": e.id,
            "name": e.name,
            "start_date": e.start_date,
            "end_date": e.end_date,
            "location": e.location,
            "source": e.source,
            "matched_doctor_count": m["count"],
            "matched_doctor_names": m["names"],
        })
    return out


@router.get("/academic-events/for-doctor/{doctor_id}")
async def list_events_for_doctor(
    doctor_id: int,
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """[start, end] 구간 학회 중 doctor 가 강사로 매칭되거나 doctor.department 가
    이벤트 departments 에 포함되는 이벤트. DoctorScheduleHintPopup 힌트 소스.
    """
    doctor = (await db.execute(
        select(Doctor)
        .options(selectinload(Doctor.hospital))
        .where(Doctor.id == doctor_id)
    )).scalar_one_or_none()
    if not doctor:
        raise HTTPException(404, "doctor not found")

    query = (
        select(AcademicEvent)
        .options(selectinload(AcademicEvent.departments))
        .where(
            AcademicEvent.start_date >= start,
            AcademicEvent.start_date <= end,
        )
        .order_by(AcademicEvent.start_date.asc())
    )
    rows = list((await db.execute(query)).scalars().unique().all())
    doctor_dept = (doctor.department or "").strip()
    doctor_hosp = doctor.hospital.name if doctor.hospital else ""

    out: list[dict] = []
    for e in rows:
        matched_as: Optional[str] = None
        matched_title: Optional[str] = None

        for lec in _parse_lectures_json(e.lectures_json):
            if _normalize_name(lec.get("lecturer") or "") != doctor.name:
                continue
            aff = (lec.get("affiliation") or "").strip()
            # aff 있으면 alias_match 로 병원 일치 확인, 없으면 이름만으로 채택
            if aff and _alias_match(doctor_hosp, aff) is None:
                continue
            matched_as = "lecturer"
            matched_title = lec.get("title")
            break

        if matched_as is None and doctor_dept:
            event_depts = {d.department for d in e.departments}
            if doctor_dept in event_depts:
                matched_as = "department"

        if matched_as:
            out.append({
                "id": e.id,
                "name": e.name,
                "start_date": e.start_date,
                "end_date": e.end_date,
                "location": e.location,
                "source": e.source,
                "matched_as": matched_as,
                "matched_lecture_title": matched_title,
            })
    return out


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


@router.post("/academic-events")
async def create_event(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """수동 학회 일정 추가 (글로벌 마스터). source='manual' 고정."""
    name = (payload.get("name") or "").strip()
    start_date = (payload.get("start_date") or "").strip()
    if not name:
        raise HTTPException(400, "name is required")
    if not start_date:
        raise HTTPException(400, "start_date is required")

    event = AcademicEvent(
        name=name,
        start_date=start_date,
        end_date=(payload.get("end_date") or "").strip() or None,
        location=(payload.get("location") or "").strip() or None,
        organizer_name=(payload.get("organizer_name") or "").strip() or None,
        url=(payload.get("url") or "").strip() or None,
        description=(payload.get("description") or "").strip() or None,
        source="manual",
        classification_status="unclassified",
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)

    event = (await db.execute(
        select(AcademicEvent)
        .options(selectinload(AcademicEvent.departments))
        .where(AcademicEvent.id == event.id)
    )).scalar_one()
    pinned = await _user_pinned_event_ids(db, user.id, [event.id])
    team_id = await get_my_team_id(db, user.id)
    team_pinned = await _team_pinned_event_ids(db, team_id, [event.id])
    owners = await _team_pin_owner_map(db, team_id, [event.id])
    return _event_to_dict(event, pinned_event_ids=pinned, team_pinned_event_ids=team_pinned, team_pin_owner_map=owners)


@router.post("/academic-events/{event_id}/pin")
async def pin_event(
    event_id: int,
    scope: str = Query("user", description="user | team"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """학회 일정 핀. scope=user(기본) 는 본인 일정, scope=team 은 팀 전체 공유."""
    event = (await db.execute(
        select(AcademicEvent).where(AcademicEvent.id == event_id)
    )).scalar_one_or_none()
    if not event:
        raise HTTPException(404, "event not found")

    today_str = datetime.now().strftime("%Y-%m-%d")
    if event.start_date and event.start_date < today_str:
        # 과거 학회 신규 핀 방지 (이미 핀이면 그대로)
        pass

    if scope == "team":
        team_id = await get_my_team_id(db, user.id)
        if not team_id:
            raise HTTPException(400, "팀에 속해있지 않아 팀 핀을 할 수 없습니다.")
        existing = (await db.execute(
            select(TeamAcademicPin).where(
                TeamAcademicPin.team_id == team_id,
                TeamAcademicPin.event_id == event_id,
            )
        )).scalar_one_or_none()
        if event.start_date and event.start_date < today_str and not existing:
            raise HTTPException(400, "이미 종료된 학회는 새로 등록할 수 없습니다.")
        if not existing:
            db.add(TeamAcademicPin(
                team_id=team_id, event_id=event_id, pinned_by_user_id=user.id
            ))
            await db.commit()
        return {"status": "pinned", "id": event_id, "scope": "team", "is_pinned": True}

    # 기본: 사용자 핀
    existing = (await db.execute(
        select(UserAcademicPin).where(
            UserAcademicPin.user_id == user.id, UserAcademicPin.event_id == event_id
        )
    )).scalar_one_or_none()
    if event.start_date and event.start_date < today_str and not existing:
        raise HTTPException(400, "이미 종료된 학회는 새로 등록할 수 없습니다.")
    if not existing:
        db.add(UserAcademicPin(user_id=user.id, event_id=event_id))
        await db.commit()
    return {"status": "pinned", "id": event_id, "scope": "user", "is_pinned": True}


@router.delete("/academic-events/{event_id}/pin")
async def unpin_event(
    event_id: int,
    scope: str = Query("user", description="user | team"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if scope == "team":
        team_id = await get_my_team_id(db, user.id)
        if not team_id:
            raise HTTPException(400, "팀에 속해있지 않습니다.")
        existing = (await db.execute(
            select(TeamAcademicPin).where(
                TeamAcademicPin.team_id == team_id,
                TeamAcademicPin.event_id == event_id,
            )
        )).scalar_one_or_none()
        if existing:
            # 공유한 본인만 팀 핀 해제 가능. 다른 팀원은 본인 일정에서만 핀 해제.
            if existing.pinned_by_user_id != user.id:
                raise HTTPException(403, "팀 일정 공유는 처음 등록한 사용자만 해제할 수 있습니다. 본인 일정에서 빼려면 '내 일정 해제' 를 사용하세요.")
            await db.delete(existing)
            await db.commit()
        return {"status": "unpinned", "id": event_id, "scope": "team", "is_pinned": False}

    existing = (await db.execute(
        select(UserAcademicPin).where(
            UserAcademicPin.user_id == user.id, UserAcademicPin.event_id == event_id
        )
    )).scalar_one_or_none()
    if existing:
        await db.delete(existing)
        await db.commit()
    return {"status": "unpinned", "id": event_id, "scope": "user", "is_pinned": False}


@router.get("/academic-events/{event_id}")
async def get_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    event = (await db.execute(
        select(AcademicEvent)
        .options(selectinload(AcademicEvent.departments))
        .where(AcademicEvent.id == event_id)
    )).scalar_one_or_none()
    if not event:
        raise HTTPException(404, "event not found")
    pinned = await _user_pinned_event_ids(db, user.id, [event.id])
    team_id = await get_my_team_id(db, user.id)
    team_pinned = await _team_pinned_event_ids(db, team_id, [event.id])
    owners = await _team_pin_owner_map(db, team_id, [event.id])
    payload = _event_to_dict(event, pinned_event_ids=pinned, team_pinned_event_ids=team_pinned, team_pin_owner_map=owners)
    payload["lectures"] = await _enrich_lectures_with_doctors(
        payload["lectures"], db, user.id
    )
    if event.organizer_id:
        hp_map = await _organizer_homepages({event.organizer_id}, db)
        payload["organizer_homepage"] = hp_map.get(event.organizer_id)
    else:
        payload["organizer_homepage"] = None
    return payload


@router.delete("/academic-events/{event_id}")
async def delete_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """수동으로 추가한 학회(source='manual') 만 삭제 허용 (글로벌 마스터)."""
    event = (await db.execute(
        select(AcademicEvent).where(AcademicEvent.id == event_id)
    )).scalar_one_or_none()
    if not event:
        raise HTTPException(404, "event not found")
    if event.source != "manual":
        raise HTTPException(403, "only manual events can be deleted")
    await db.delete(event)
    await db.commit()
    return {"status": "deleted", "id": event_id}


@router.patch("/academic-events/{event_id}/departments")
async def update_event_departments(
    event_id: int,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
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
    pinned = await _user_pinned_event_ids(db, user.id, [event.id])
    team_id = await get_my_team_id(db, user.id)
    team_pinned = await _team_pinned_event_ids(db, team_id, [event.id])
    owners = await _team_pin_owner_map(db, team_id, [event.id])
    return _event_to_dict(event, pinned_event_ids=pinned, team_pinned_event_ids=team_pinned, team_pin_owner_map=owners)


@router.post("/academic-events/reclassify")
async def reclassify_events(db: AsyncSession = Depends(get_db)):
    """DB의 모든 학회 이벤트 진료과를 현재 사전/로직으로 재계산.

    - 수동 지정(`classification_status == 'mapped'`) 이벤트는 보호 (skip).
    - 그 외는 `resolve_event` 재호출 → departments 교체 + status 갱신.
    - 외부 크롤링 없이 빠르게 재분류.
    """
    organizers = (await db.execute(select(AcademicOrganizer))).scalars().all()
    organizers_lookup: dict[str, list[str]] = {}
    for org in organizers:
        depts = departments_from_json(org.departments_json)
        if depts:
            organizers_lookup[org.name] = depts

    events = (await db.execute(
        select(AcademicEvent)
        .options(selectinload(AcademicEvent.departments))
    )).scalars().all()

    stats = {
        "total": len(events),
        "reclassified": 0,
        "skipped_mapped": 0,
        "unclassified": 0,
    }

    for event in events:
        if event.classification_status == "mapped":
            stats["skipped_mapped"] += 1
            continue

        depts, status = resolve_event(
            event.organizer_name,
            event.name,
            organizers_lookup,
            kma_category=event.kma_category,
        )

        event.departments.clear()
        for d in depts:
            event.departments.append(AcademicEventDepartment(department=d))
        event.classification_status = status
        event.updated_at = datetime.utcnow()

        if status == "unclassified":
            stats["unclassified"] += 1
        else:
            stats["reclassified"] += 1

    await db.commit()
    logger.info(f"reclassify_events: {stats}")
    return {"status": "ok", **stats}


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
