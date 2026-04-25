"""개인 일정/플랫 방문 로그 API"""
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.connection import get_db
from app.models.database import Doctor, MemoTemplate, VisitLog, VisitMemo
from app.schemas.schemas import AnnouncementCreate, PersonalEventCreate, SummarizeRequest
from app.services.ai_memo import organize_memo, summarize_freeform

router = APIRouter(prefix="/api/visits", tags=["방문 로그"])

DEFAULT_USER_ID = 1


def _visit_to_dict(visit: VisitLog) -> dict:
    return {
        "id": visit.id,
        "doctor_id": None,
        "visit_date": visit.visit_date.isoformat(),
        "status": visit.status,
        "notes": visit.notes,
        "post_notes": visit.post_notes,
        "title": visit.title,
        "category": visit.category,
    }


@router.post("/personal", summary="개인 일정 등록")
async def create_personal_event(
    data: PersonalEventCreate, db: AsyncSession = Depends(get_db)
):
    title = (data.title or "").strip() or "내 일정"
    visit = VisitLog(
        doctor_id=None,
        visit_date=data.visit_date,
        status=data.status or "예정",
        notes=data.notes,
        title=title,
        category="personal",
    )
    db.add(visit)
    await db.commit()
    await db.refresh(visit)
    return _visit_to_dict(visit)


@router.delete("/{visit_id}", summary="방문 로그 삭제 (개인/공지 포함)")
async def delete_visit(visit_id: int, db: AsyncSession = Depends(get_db)):
    visit = (await db.execute(select(VisitLog).where(VisitLog.id == visit_id))).scalar_one_or_none()
    if not visit:
        raise HTTPException(404, "visit not found")
    await db.delete(visit)
    await db.commit()
    return {"status": "deleted", "id": visit_id}


@router.patch("/{visit_id}", summary="방문 로그 수정 (개인/공지 · doctor_id 무관)")
async def update_visit_flat(visit_id: int, data: dict, db: AsyncSession = Depends(get_db)):
    """doctor_id 없이도 동작하는 플랫 PATCH — 개인 일정/공지에서 사용.
    교수 방문의 경우 기존 /api/doctors/{doctor_id}/visits/{visit_id} 를 계속 사용."""
    visit = (await db.execute(select(VisitLog).where(VisitLog.id == visit_id))).scalar_one_or_none()
    if not visit:
        raise HTTPException(404, "visit not found")
    allowed = {"status", "notes", "post_notes", "title", "visit_date"}
    for key, value in data.items():
        if key not in allowed:
            continue
        if key == "visit_date" and isinstance(value, str):
            from datetime import datetime as _dt
            value = _dt.fromisoformat(value.replace("Z", "+00:00"))
        setattr(visit, key, value)
    await db.commit()
    await db.refresh(visit)
    return _visit_to_dict(visit)


@router.post("/announcement", summary="업무공지 등록")
async def create_announcement(
    data: AnnouncementCreate, db: AsyncSession = Depends(get_db)
):
    """업무공지(category='announcement') 등록. 팀원 공유는 추후 확장."""
    title = (data.title or "").strip()
    if not title:
        raise HTTPException(400, "title is required")
    visit = VisitLog(
        doctor_id=None,
        visit_date=data.visit_date,
        status="예정",
        notes=data.notes,
        title=title,
        category="announcement",
    )
    db.add(visit)
    await db.commit()
    await db.refresh(visit)
    return _visit_to_dict(visit)


# ─────────── AI 정리 ───────────

def _parse_ai(raw: Optional[str]):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return raw


async def _load_default_template(db: AsyncSession) -> Optional[MemoTemplate]:
    query = (
        select(MemoTemplate)
        .where(MemoTemplate.user_id == DEFAULT_USER_ID, MemoTemplate.is_default == True)
        .limit(1)
    )
    return (await db.execute(query)).scalar_one_or_none()


@router.post("/{visit_id}/ai-summarize", summary="방문 메모 AI 정리 (Claude Haiku)")
async def ai_summarize_visit(
    visit_id: int,
    payload: SummarizeRequest = SummarizeRequest(),
    db: AsyncSession = Depends(get_db),
):
    """VisitLog 의 메모를 AI 로 정리하여 VisitMemo 에 저장.

    - 교수 방문(doctor_id 존재): post_notes 를 source 로 사용
    - 개인 일정/업무공지: notes 를 source 로 사용
    - 기존 VisitMemo(visit_log_id 링크)가 있으면 갱신, 없으면 생성
    """
    query = (
        select(VisitLog)
        .options(selectinload(VisitLog.doctor).selectinload(Doctor.hospital))
        .where(VisitLog.id == visit_id)
    )
    visit = (await db.execute(query)).scalar_one_or_none()
    if not visit:
        raise HTTPException(404, "방문 기록을 찾을 수 없습니다.")

    is_professor = visit.doctor_id is not None
    # 프론트가 아직 저장하지 않은 최신 원본을 넘길 수 있음 — 있으면 그걸 우선.
    override = (payload.raw_memo or "").strip() if payload.raw_memo is not None else ""
    if override:
        raw_source = override
        # DB 에도 반영 — 사전/사후/단일 구분에 따라 분기
        if is_professor:
            visit.post_notes = override
        else:
            visit.notes = override
    else:
        raw_source = ((visit.post_notes if is_professor else visit.notes) or "").strip()
    if not raw_source:
        label = "결과 메모" if is_professor else "메모"
        raise HTTPException(400, f"{label}가 비어 있어 AI 정리할 내용이 없습니다.")

    # 교수 방문: 템플릿 기반 구조화 요약
    # 개인/공지: 템플릿 없이 자유 문장 정리
    template = None
    if is_professor:
        if payload.template_id:
            template = (await db.execute(
                select(MemoTemplate).where(MemoTemplate.id == payload.template_id)
            )).scalar_one_or_none()
        if template is None:
            template = await _load_default_template(db)

        fields: list[str] = []
        prompt_addon: Optional[str] = None
        if template:
            try:
                fields = json.loads(template.fields) if template.fields else []
            except (TypeError, ValueError):
                fields = []
            prompt_addon = template.prompt_addon

        doctor = visit.doctor
        hospital = doctor.hospital if doctor else None
        context = {
            "doctor_name": doctor.name if doctor else None,
            "hospital_name": hospital.name if hospital else None,
            "department": doctor.department if doctor else None,
            "visit_date": visit.visit_date.isoformat() if visit.visit_date else None,
        }

        result = await organize_memo(
            raw_memo=raw_source,
            fields=fields,
            prompt_addon=prompt_addon,
            context=context,
        )
    else:
        kind = "announcement" if visit.category == "announcement" else "personal"
        result = await summarize_freeform(raw_memo=raw_source, kind=kind)

    memo = (await db.execute(
        select(VisitMemo).where(VisitMemo.visit_log_id == visit.id).limit(1)
    )).scalar_one_or_none()

    ai_json = json.dumps(result, ensure_ascii=False)
    memo_title = result.get("title") or visit.title

    if memo is None:
        memo_type = "visit" if is_professor else ("note" if visit.category == "announcement" else "note")
        # snapshot — 의사 record 가 사라져도 메모를 추적할 수 있도록
        doctor_obj = visit.doctor if is_professor else None
        hospital_obj = doctor_obj.hospital if doctor_obj else None
        memo = VisitMemo(
            user_id=DEFAULT_USER_ID,
            doctor_id=visit.doctor_id,
            visit_log_id=visit.id,
            template_id=template.id if template else None,
            visit_date=visit.visit_date,
            memo_type=memo_type,
            title=memo_title,
            raw_memo=raw_source,
            ai_summary=ai_json,
            doctor_name_snapshot=doctor_obj.name if doctor_obj else None,
            doctor_dept_snapshot=doctor_obj.department if doctor_obj else None,
            hospital_name_snapshot=hospital_obj.name if hospital_obj else None,
        )
        db.add(memo)
    else:
        memo.raw_memo = raw_source
        memo.ai_summary = ai_json
        memo.title = memo_title or memo.title
        if template and not memo.template_id:
            memo.template_id = template.id

    await db.commit()
    await db.refresh(memo)

    return {
        "memo_id": memo.id,
        "visit_id": visit.id,
        "ai_summary": result,
        "title": memo.title,
        "template_id": memo.template_id,
    }
