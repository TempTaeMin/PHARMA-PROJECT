"""MR 메모/회의록 API — raw_memo 저장 + Claude Haiku 정리."""
import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.deps import get_current_user
from app.models.connection import get_db
from app.models.database import Doctor, Hospital, MemoTemplate, User, VisitLog, VisitMemo
from app.schemas.schemas import (
    MemoTemplateCreate,
    MemoTemplateResponse,
    MemoTemplateUpdate,
    SummarizeRequest,
    VisitMemoCreate,
    VisitMemoResponse,
    VisitMemoUpdate,
)
from app.services.ai_memo import organize_memo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/memos", tags=["메모/회의록"])
templates_router = APIRouter(prefix="/api/memo-templates", tags=["메모 템플릿"])


def _parse_ai(raw: Optional[str]):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return raw


def _serialize(memo: VisitMemo, doctor: Optional[Doctor] = None, hospital: Optional[Hospital] = None) -> dict:
    doc = doctor or memo.doctor
    hosp = hospital or (doc.hospital if doc else None)
    return {
        "id": memo.id,
        "user_id": memo.user_id,
        "doctor_id": memo.doctor_id,
        "doctor_name": doc.name if doc else None,
        "hospital_name": hosp.name if hosp else None,
        "department": doc.department if doc else None,
        "visit_log_id": memo.visit_log_id,
        "template_id": memo.template_id,
        "visit_date": memo.visit_date.isoformat() if memo.visit_date else None,
        "memo_type": memo.memo_type,
        "title": memo.title,
        "raw_memo": memo.raw_memo,
        "ai_summary": _parse_ai(memo.ai_summary),
        "created_at": memo.created_at.isoformat() if memo.created_at else None,
        "updated_at": memo.updated_at.isoformat() if memo.updated_at else None,
    }


async def _load_memo(db: AsyncSession, memo_id: int, user_id: int) -> VisitMemo:
    query = (
        select(VisitMemo)
        .options(selectinload(VisitMemo.doctor).selectinload(Doctor.hospital))
        .where(VisitMemo.id == memo_id, VisitMemo.user_id == user_id)
    )
    memo = (await db.execute(query)).scalar_one_or_none()
    if not memo:
        raise HTTPException(status_code=404, detail="메모를 찾을 수 없습니다.")
    return memo


async def _load_template(
    db: AsyncSession, template_id: Optional[int], user_id: int
) -> Optional[MemoTemplate]:
    if template_id is None:
        query = (
            select(MemoTemplate)
            .where(MemoTemplate.user_id == user_id, MemoTemplate.is_default == True)
            .limit(1)
        )
    else:
        query = select(MemoTemplate).where(
            MemoTemplate.id == template_id, MemoTemplate.user_id == user_id
        )
    return (await db.execute(query)).scalar_one_or_none()


# ─────────── Memo CRUD ───────────

@router.post("", summary="메모 생성 (원본만)")
async def create_memo(
    payload: VisitMemoCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    memo = VisitMemo(
        user_id=user.id,
        doctor_id=payload.doctor_id,
        visit_log_id=payload.visit_log_id,
        template_id=payload.template_id,
        visit_date=payload.visit_date or datetime.utcnow(),
        memo_type=payload.memo_type or "visit",
        title=payload.title,
        raw_memo=payload.raw_memo,
    )
    db.add(memo)
    await db.commit()
    await db.refresh(memo)
    memo = await _load_memo(db, memo.id, user.id)
    return _serialize(memo)


@router.get("", summary="메모 목록")
async def list_memos(
    doctor_id: Optional[int] = None,
    hospital_id: Optional[int] = None,
    memo_type: Optional[str] = None,
    q: Optional[str] = None,
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = (
        select(VisitMemo)
        .options(selectinload(VisitMemo.doctor).selectinload(Doctor.hospital))
        .where(VisitMemo.user_id == user.id)
    )
    if doctor_id:
        query = query.where(VisitMemo.doctor_id == doctor_id)
    if hospital_id:
        query = query.join(Doctor, VisitMemo.doctor_id == Doctor.id).where(
            Doctor.hospital_id == hospital_id
        )
    if memo_type:
        query = query.where(VisitMemo.memo_type == memo_type)
    if from_date:
        try:
            query = query.where(VisitMemo.visit_date >= datetime.fromisoformat(from_date))
        except ValueError:
            pass
    if to_date:
        try:
            query = query.where(VisitMemo.visit_date <= datetime.fromisoformat(to_date + "T23:59:59"))
        except ValueError:
            pass
    if q:
        like = f"%{q}%"
        query = query.where(
            or_(
                VisitMemo.title.ilike(like),
                VisitMemo.raw_memo.ilike(like),
                VisitMemo.ai_summary.ilike(like),
            )
        )
    query = query.order_by(VisitMemo.visit_date.desc().nullslast(), VisitMemo.id.desc())
    query = query.offset(offset).limit(limit)

    rows = (await db.execute(query)).scalars().all()
    return [_serialize(m) for m in rows]


@router.get("/{memo_id}", summary="메모 상세")
async def get_memo(
    memo_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    memo = await _load_memo(db, memo_id, user.id)
    return _serialize(memo)


@router.put("/{memo_id}", summary="메모 수정")
async def update_memo(
    memo_id: int,
    payload: VisitMemoUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    memo = await _load_memo(db, memo_id, user.id)
    data = payload.model_dump(exclude_unset=True)
    if "ai_summary" in data and data["ai_summary"] is not None:
        val = data["ai_summary"]
        data["ai_summary"] = json.dumps(val, ensure_ascii=False) if not isinstance(val, str) else val
    for k, v in data.items():
        setattr(memo, k, v)
    await db.commit()
    memo = await _load_memo(db, memo.id, user.id)
    return _serialize(memo)


@router.delete("/{memo_id}", summary="메모 삭제")
async def delete_memo(
    memo_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    memo = await _load_memo(db, memo_id, user.id)
    await db.delete(memo)
    await db.commit()
    return {"ok": True}


# ─────────── AI 정리 ───────────

@router.post("/{memo_id}/summarize", summary="AI 정리 (Claude Haiku)")
async def summarize_memo(
    memo_id: int,
    payload: SummarizeRequest = SummarizeRequest(),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    memo = await _load_memo(db, memo_id, user.id)
    template = await _load_template(db, payload.template_id or memo.template_id, user.id)
    fields: list[str] = []
    prompt_addon: Optional[str] = None
    if template:
        try:
            fields = json.loads(template.fields) if template.fields else []
        except (TypeError, ValueError):
            fields = []
        prompt_addon = template.prompt_addon

    context = {
        "doctor_name": memo.doctor.name if memo.doctor else None,
        "hospital_name": memo.doctor.hospital.name if memo.doctor and memo.doctor.hospital else None,
        "department": memo.doctor.department if memo.doctor else None,
        "visit_date": memo.visit_date.isoformat() if memo.visit_date else None,
    }

    result = await organize_memo(
        raw_memo=memo.raw_memo,
        fields=fields,
        prompt_addon=prompt_addon,
        context=context,
    )

    memo.title = result.get("title") or memo.title
    memo.ai_summary = json.dumps(result, ensure_ascii=False)
    if template and not memo.template_id:
        memo.template_id = template.id
    await db.commit()
    memo = await _load_memo(db, memo.id, user.id)
    return _serialize(memo)


# ─────────── 교수별 메모 조회 ───────────

doctor_memos_router = APIRouter(prefix="/api/doctors", tags=["메모/회의록"])


@doctor_memos_router.get("/{doctor_id}/memos", summary="교수별 메모 목록")
async def list_memos_by_doctor(
    doctor_id: int,
    limit: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = (
        select(VisitMemo)
        .options(selectinload(VisitMemo.doctor).selectinload(Doctor.hospital))
        .where(VisitMemo.doctor_id == doctor_id, VisitMemo.user_id == user.id)
        .order_by(VisitMemo.visit_date.desc().nullslast(), VisitMemo.id.desc())
        .limit(limit)
    )
    rows = (await db.execute(query)).scalars().all()
    return [_serialize(m) for m in rows]


# ─────────── 템플릿 CRUD ───────────

def _template_to_dict(t: MemoTemplate) -> dict:
    try:
        fields = json.loads(t.fields) if t.fields else []
    except (TypeError, ValueError):
        fields = []
    return {
        "id": t.id,
        "user_id": t.user_id,
        "name": t.name,
        "fields": fields,
        "prompt_addon": t.prompt_addon,
        "is_default": bool(t.is_default),
        "scope": t.scope or "memo",
        "default_report_type": t.default_report_type,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


_VALID_SCOPES = {"memo", "report", "both"}
_VALID_REPORT_TYPES = {"daily", "weekly"}


def _normalize_scope(value: Optional[str]) -> str:
    return value if value in _VALID_SCOPES else "memo"


def _normalize_report_type(value: Optional[str]) -> Optional[str]:
    return value if value in _VALID_REPORT_TYPES else None


async def _load_user_template(
    db: AsyncSession, template_id: int, user_id: int
) -> MemoTemplate:
    t = (await db.execute(
        select(MemoTemplate).where(
            MemoTemplate.id == template_id, MemoTemplate.user_id == user_id
        )
    )).scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="템플릿을 찾을 수 없습니다.")
    return t


@templates_router.get("", summary="템플릿 목록")
async def list_templates(
    scope: Optional[str] = Query(None, description="memo | report (생략 시 전체)"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = (
        select(MemoTemplate)
        .where(MemoTemplate.user_id == user.id)
        .order_by(MemoTemplate.is_default.desc(), MemoTemplate.id.asc())
    )
    if scope == "memo":
        query = query.where(MemoTemplate.scope.in_(["memo", "both"]))
    elif scope == "report":
        query = query.where(MemoTemplate.scope.in_(["report", "both"]))
    rows = (await db.execute(query)).scalars().all()
    return [_template_to_dict(t) for t in rows]


@templates_router.post("", summary="템플릿 생성")
async def create_template(
    payload: MemoTemplateCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    scope = _normalize_scope(payload.scope)
    default_report_type = _normalize_report_type(payload.default_report_type)
    # is_default 는 메모 풀 안에서만 의미 — 보고서 전용 템플릿은 강제 False
    if scope == "report":
        is_default = False
    else:
        existing_count = (await db.execute(
            select(func.count()).select_from(MemoTemplate)
            .where(
                MemoTemplate.user_id == user.id,
                MemoTemplate.scope.in_(["memo", "both"]),
            )
        )).scalar() or 0
        is_default = bool(payload.is_default) or existing_count == 0
    t = MemoTemplate(
        user_id=user.id,
        name=payload.name,
        fields=json.dumps(payload.fields, ensure_ascii=False),
        prompt_addon=payload.prompt_addon,
        is_default=is_default,
        scope=scope,
        default_report_type=default_report_type,
    )
    if is_default:
        await _unset_other_defaults(db, user.id)
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return _template_to_dict(t)


@templates_router.put("/{template_id}", summary="템플릿 수정")
async def update_template(
    template_id: int,
    payload: MemoTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    t = await _load_user_template(db, template_id, user.id)
    data = payload.model_dump(exclude_unset=True)
    if "fields" in data and data["fields"] is not None:
        data["fields"] = json.dumps(data["fields"], ensure_ascii=False)
    if "scope" in data:
        data["scope"] = _normalize_scope(data["scope"])
    if "default_report_type" in data:
        data["default_report_type"] = _normalize_report_type(data["default_report_type"])
    # 보고서 전용 템플릿은 is_default 무시
    final_scope = data.get("scope", t.scope or "memo")
    if final_scope == "report":
        data["is_default"] = False
    if data.get("is_default"):
        await _unset_other_defaults(db, user.id, exclude_id=t.id)
    for k, v in data.items():
        setattr(t, k, v)
    await db.commit()
    await db.refresh(t)
    return _template_to_dict(t)


@templates_router.delete("/{template_id}", summary="템플릿 삭제")
async def delete_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    t = await _load_user_template(db, template_id, user.id)
    if t.is_default:
        raise HTTPException(status_code=400, detail="기본 템플릿은 삭제할 수 없습니다.")
    await db.delete(t)
    await db.commit()
    return {"ok": True}


async def _unset_other_defaults(
    db: AsyncSession, user_id: int, exclude_id: Optional[int] = None
):
    query = select(MemoTemplate).where(
        MemoTemplate.user_id == user_id, MemoTemplate.is_default == True
    )
    rows = (await db.execute(query)).scalars().all()
    for row in rows:
        if exclude_id and row.id == exclude_id:
            continue
        row.is_default = False
