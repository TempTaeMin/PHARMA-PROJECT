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
    "한림대학교강남성심병원": ["한림 강남성심", "강남성심", "한림대 강남성심"],
    "한림대학교한강성심병원": ["한림 한강성심", "한강성심", "한림대 한강성심"],
    "한림대학교동탄성심병원": ["한림 동탄성심", "동탄성심", "한림대 동탄성심"],
    "동국대학교일산병원": ["동국대학교 일산", "동국대일산", "동국의대 일산"],
    "부천순천향병원": ["부천순천향", "순천향대 부천", "순천향 부천"],
    "순천향대학교서울병원": ["서울순천향", "순천향 서울", "순천향대 서울"],
    "노원을지대학교병원": ["노원을지", "을지대 노원", "을지 노원"],
    "의정부을지대학교병원": ["의정부을지", "을지대 의정부", "을지 의정부"],
    "인제대학교 상계백병원": ["상계백병원", "상계백", "인제대 상계"],
    "인제대학교 일산백병원": ["일산백병원", "일산백", "인제대 일산"],
    "인제대학교 부산백병원": ["부산백병원", "부산백", "인제대 부산"],
    "의정부백병원": ["의정부백", "의정부 백병원"],
    "강동경희대학교병원": ["강동경희", "강동경희대"],
    "동아대학교병원": ["동아대병원", "동아대학교병원", "동아의대"],
    "고신대학교복음병원": ["고신복음", "복음병원", "고신대 복음"],
    "영남대학교병원": ["영남대병원", "영남대학교병원", "영남의대 병원"],
    "경북대학교병원": ["경북대병원", "경북대학교병원"],
    "칠곡경북대학교병원": ["칠곡경북대", "칠곡경북대병원"],
    "전남대학교병원": ["전남대병원", "전남대학교병원"],
    "화순전남대학교병원": ["화순전남대", "화순전남대병원"],
    "울산대학교병원": ["울산대병원", "울산대학교병원"],
    "충북대학교병원": ["충북대병원", "충북대학교병원"],
    "충남대학교병원": ["충남대병원", "충남대학교병원"],
    "단국대학교의과대학부속병원": ["단국대병원", "단국대학교병원", "단국의대 병원"],
    "전북대학교병원": ["전북대병원", "전북대학교병원"],
    "원광대학교병원": ["원광대병원", "원광대학교병원"],
    "부산대학교병원": ["부산대병원", "부산대학교병원"],
    "양산부산대학교병원": ["양산부산대", "양산부산대병원"],
    "대구가톨릭대학교병원": ["대구가톨릭", "대구가톨릭병원"],
    "계명대학교동산병원": ["계명대 동산", "계명동산", "계명대학교 동산"],
    "삼성창원병원": ["삼성창원"],
    "경상국립대학교병원": ["경상국립대", "경상대병원", "경상국립대병원"],
    "원주세브란스기독병원": ["원주세브란스", "원주기독병원"],
    "강릉아산병원": ["강릉아산"],
    "부천성모병원": ["부천성모"],
    "의정부성모병원": ["의정부성모"],
    "중앙대학교광명병원": ["중앙대 광명", "광명중앙대"],
    "조선대학교병원": ["조선대병원", "조선대학교병원"],
    "건양대학교병원": ["건양대병원", "건양대학교병원"],
    "국립암센터": ["국립암센터"],
    "한국원자력의학원": ["원자력의학원", "원자력병원"],
}


# 의대/대학 약칭 → 소속 병원 목록 (1:N).
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
    "울산의대":              ["서울아산병원"],
    "울산대학교 의과대학":   ["서울아산병원"],
    "울산대학교":            ["서울아산병원"],
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
    "한림의대":              ["한림성심병원", "한림대학교강남성심병원", "한림대학교한강성심병원", "한림대학교동탄성심병원"],
    "한림대학교 의과대학":   ["한림성심병원", "한림대학교강남성심병원", "한림대학교한강성심병원", "한림대학교동탄성심병원"],
    "한림대":                ["한림성심병원", "한림대학교강남성심병원", "한림대학교한강성심병원", "한림대학교동탄성심병원"],
    "인제의대":              ["인제대학교 상계백병원", "인제대학교 일산백병원", "인제대학교 부산백병원", "의정부백병원"],
    "인제대학교 의과대학":   ["인제대학교 상계백병원", "인제대학교 일산백병원", "인제대학교 부산백병원", "의정부백병원"],
    "인제대":                ["인제대학교 상계백병원", "인제대학교 일산백병원", "인제대학교 부산백병원", "의정부백병원"],
    "순천향의대":            ["순천향대학교서울병원", "부천순천향병원"],
    "순천향대학교 의과대학": ["순천향대학교서울병원", "부천순천향병원"],
    "순천향대":              ["순천향대학교서울병원", "부천순천향병원"],
    "을지의대":              ["노원을지대학교병원", "의정부을지대학교병원"],
    "을지대학교 의과대학":   ["노원을지대학교병원", "의정부을지대학교병원"],
    "을지대":                ["노원을지대학교병원", "의정부을지대학교병원"],
    "동국의대":              ["동국대학교일산병원"],
    "동국대학교 의과대학":   ["동국대학교일산병원"],
    "동국대":                ["동국대학교일산병원"],
    "동아의대":              ["동아대학교병원"],
    "동아대학교 의과대학":   ["동아대학교병원"],
    "동아대":                ["동아대학교병원"],
    "고신의대":              ["고신대학교복음병원"],
    "고신대학교 의과대학":   ["고신대학교복음병원"],
    "고신대":                ["고신대학교복음병원"],
    "영남의대":              ["영남대학교병원"],
    "영남대학교 의과대학":   ["영남대학교병원"],
    "영남대":                ["영남대학교병원"],
    "경북의대":              ["경북대학교병원", "칠곡경북대학교병원"],
    "경북대학교 의과대학":   ["경북대학교병원", "칠곡경북대학교병원"],
    "경북대":                ["경북대학교병원", "칠곡경북대학교병원"],
    "전남의대":              ["전남대학교병원", "화순전남대학교병원"],
    "전남대학교 의과대학":   ["전남대학교병원", "화순전남대학교병원"],
    "전남대":                ["전남대학교병원", "화순전남대학교병원"],
    "충남의대":              ["충남대학교병원"],
    "충남대학교 의과대학":   ["충남대학교병원"],
    "충남대":                ["충남대학교병원"],
    "충북의대":              ["충북대학교병원"],
    "충북대학교 의과대학":   ["충북대학교병원"],
    "충북대":                ["충북대학교병원"],
    "단국의대":              ["단국대학교의과대학부속병원"],
    "단국대학교 의과대학":   ["단국대학교의과대학부속병원"],
    "단국대":                ["단국대학교의과대학부속병원"],
    "전북의대":              ["전북대학교병원"],
    "전북대학교 의과대학":   ["전북대학교병원"],
    "전북대":                ["전북대학교병원"],
    "원광의대":              ["원광대학교병원"],
    "원광대학교 의과대학":   ["원광대학교병원"],
    "원광대":                ["원광대학교병원"],
    "부산의대":              ["부산대학교병원", "양산부산대학교병원"],
    "부산대학교 의과대학":   ["부산대학교병원", "양산부산대학교병원"],
    "부산대":                ["부산대학교병원", "양산부산대학교병원"],
    "대구가톨릭의대":        ["대구가톨릭대학교병원"],
    "대구가톨릭대학교 의과대학": ["대구가톨릭대학교병원"],
    "계명의대":              ["계명대학교동산병원"],
    "계명대학교 의과대학":   ["계명대학교동산병원"],
    "계명대":                ["계명대학교동산병원"],
    "조선의대":              ["조선대학교병원"],
    "조선대학교 의과대학":   ["조선대학교병원"],
    "조선대":                ["조선대학교병원"],
    "건양의대":              ["건양대학교병원"],
    "건양대학교 의과대학":   ["건양대학교병원"],
    "건양대":                ["건양대학교병원"],
    "경상의대":              ["경상국립대학교병원"],
    "경상국립대학교 의과대학": ["경상국립대학교병원"],
    "경상국립대":            ["경상국립대학교병원"],
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
        "is_pinned": bool(e.is_pinned),
        "departments": sorted({d.department for d in e.departments}),
        "lectures": _parse_lectures_json(e.lectures_json),
    }


async def _summarize_matched_lecturers(
    events: list[AcademicEvent], db: AsyncSession
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

    rows = (await db.execute(
        select(Doctor)
        .options(selectinload(Doctor.hospital))
        .where(
            Doctor.visit_grade.in_(["A", "B", "C"]),
            Doctor.name.in_(all_names),
        )
    )).scalars().all()

    by_name: dict[str, list[Doctor]] = {}
    for d in rows:
        by_name.setdefault(d.name, []).append(d)

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
    events: list[AcademicEvent], db: AsyncSession
) -> list[dict]:
    """list/upcoming/unclassified 공통 응답 빌더.
    각 event 에 matched_doctor_count/names, organizer_homepage 주입.
    """
    matched = await _summarize_matched_lecturers(events, db)
    homepages = await _organizer_homepages(
        {e.organizer_id for e in events if e.organizer_id}, db
    )
    result = []
    for e in events:
        d = _event_to_dict(e)
        m = matched.get(e.id, {"count": 0, "names": []})
        d["matched_doctor_count"] = m["count"]
        d["matched_doctor_names"] = m["names"]
        d["organizer_homepage"] = homepages.get(e.organizer_id) if e.organizer_id else None
        result.append(d)
    return result


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
        matched = _pick_candidate(candidates, lec.get("affiliation") or "")

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
    return await _enrich_events_with_summary(list(rows), db)


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
    return await _enrich_events_with_summary(list(rows), db)


@router.get("/academic-events/unclassified")
async def list_unclassified_events(db: AsyncSession = Depends(get_db)):
    query = (
        select(AcademicEvent)
        .options(selectinload(AcademicEvent.departments))
        .where(AcademicEvent.classification_status == "unclassified")
        .order_by(AcademicEvent.start_date.asc())
    )
    rows = (await db.execute(query)).scalars().unique().all()
    return await _enrich_events_with_summary(list(rows), db)


@router.get("/academic-events/my-schedule")
async def list_my_schedule_events(
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
):
    """Schedule.jsx 월간 아젠다용. source='manual' OR is_pinned=true 합집합."""
    query = (
        select(AcademicEvent)
        .options(selectinload(AcademicEvent.departments))
        .where(
            AcademicEvent.start_date >= start,
            AcademicEvent.start_date <= end,
            or_(
                AcademicEvent.source == "manual",
                AcademicEvent.is_pinned == True,  # noqa: E712
            ),
        )
        .order_by(AcademicEvent.start_date.asc())
    )
    rows = (await db.execute(query)).scalars().unique().all()
    return await _enrich_events_with_summary(list(rows), db)


@router.get("/academic-events/my-lecturers")
async def list_my_lecturer_events(
    months: int = Query(1, ge=1, le=12),
    db: AsyncSession = Depends(get_db),
):
    """향후 N개월 중 내 교수(visit_grade A/B/C) 가 강사로 참여하는 이벤트.

    NotificationPanel '스케줄 변경' 탭 요약 카드 소스.
    """
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
    matched = await _summarize_matched_lecturers(rows, db)
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
async def create_event(payload: dict, db: AsyncSession = Depends(get_db)):
    """사용자가 수동으로 학회 일정을 추가한다. source='manual' 고정."""
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

    # departments relationship 은 아직 로드되지 않았으므로 재로드
    event = (await db.execute(
        select(AcademicEvent)
        .options(selectinload(AcademicEvent.departments))
        .where(AcademicEvent.id == event.id)
    )).scalar_one()
    return _event_to_dict(event)


@router.post("/academic-events/{event_id}/pin")
async def pin_event(event_id: int, db: AsyncSession = Depends(get_db)):
    """학회 일정을 '내 일정'(Schedule.jsx) 에 노출하도록 pin.

    이미 종료된 학회(start_date < today)는 신규 pin 차단.
    이미 pinned 된 학회는 그대로 유지(unpin 으로만 해제 가능).
    """
    event = (await db.execute(
        select(AcademicEvent).where(AcademicEvent.id == event_id)
    )).scalar_one_or_none()
    if not event:
        raise HTTPException(404, "event not found")

    # 과거 학회 신규 pin 가드
    today_str = datetime.now().strftime("%Y-%m-%d")
    if event.start_date and event.start_date < today_str and not event.is_pinned:
        raise HTTPException(400, "이미 종료된 학회는 새로 등록할 수 없습니다.")

    event.is_pinned = True
    event.updated_at = datetime.utcnow()
    await db.commit()
    return {"status": "pinned", "id": event_id, "is_pinned": True}


@router.delete("/academic-events/{event_id}/pin")
async def unpin_event(event_id: int, db: AsyncSession = Depends(get_db)):
    event = (await db.execute(
        select(AcademicEvent).where(AcademicEvent.id == event_id)
    )).scalar_one_or_none()
    if not event:
        raise HTTPException(404, "event not found")
    event.is_pinned = False
    event.updated_at = datetime.utcnow()
    await db.commit()
    return {"status": "unpinned", "id": event_id, "is_pinned": False}


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
    # organizer_homepage 주입 (상세 모달 '주최단체 홈페이지' 보조 링크용)
    if event.organizer_id:
        hp_map = await _organizer_homepages({event.organizer_id}, db)
        payload["organizer_homepage"] = hp_map.get(event.organizer_id)
    else:
        payload["organizer_homepage"] = None
    return payload


@router.delete("/academic-events/{event_id}")
async def delete_event(event_id: int, db: AsyncSession = Depends(get_db)):
    """수동으로 추가한 학회(source='manual') 만 삭제 허용.
    크롤링 데이터는 동기화 시 재생성되므로 UI 삭제 의미가 없어 거부."""
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
