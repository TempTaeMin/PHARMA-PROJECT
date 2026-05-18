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
from app.models.database import Doctor, Hospital, MemoTemplate, Team, TeamMember, User, VisitLog, VisitMemo
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
from app.utils.timeutil import iso_utc

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


def _serialize(
    memo: VisitMemo,
    doctor: Optional[Doctor] = None,
    hospital: Optional[Hospital] = None,
    *,
    current_user_id: Optional[int] = None,
    author_name: Optional[str] = None,
    is_root: Optional[bool] = None,
) -> dict:
    doc = doctor or memo.doctor
    hosp = hospital or (doc.hospital if doc else None)
    is_mine = current_user_id is not None and memo.user_id == current_user_id
    return {
        "id": memo.id,
        "user_id": memo.user_id,
        "author_name": author_name,
        "is_mine": is_mine if current_user_id is not None else None,
        "is_root": is_root,
        "doctor_id": memo.doctor_id,
        "doctor_name": doc.name if doc else None,
        "hospital_name": hosp.name if hosp else None,
        "department": doc.department if doc else None,
        "visit_log_id": memo.visit_log_id,
        "template_id": memo.template_id,
        "visit_date": memo.visit_date.isoformat() if memo.visit_date else None,
        "memo_type": memo.memo_type,
        "title": memo.title,
        # raw_memo 는 본인 것만 노출 — current_user_id 가 주어지지 않은 경로(레거시)는 그대로
        "raw_memo": memo.raw_memo if (current_user_id is None or is_mine) else None,
        "ai_summary": _parse_ai(memo.ai_summary),
        "created_at": iso_utc(memo.created_at),
        "updated_at": iso_utc(memo.updated_at),
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
    """자유 메모 AI 정리용 템플릿 로드. 개인 + 본인 멤버 팀 양쪽 인식.

    template_id None → 본인 개인 default → 없으면 본인 소속 팀 default → 없으면 None.
    template_id 지정 → 본인 read 권한 있는 템플릿 (없으면 None).
    """
    if template_id is None:
        personal = (await db.execute(
            select(MemoTemplate).where(
                MemoTemplate.team_id.is_(None),
                MemoTemplate.user_id == user_id,
                MemoTemplate.is_default == True,
            ).limit(1)
        )).scalar_one_or_none()
        if personal:
            return personal
        team_id_rows = (await db.execute(
            select(TeamMember.team_id).where(TeamMember.user_id == user_id)
        )).all()
        team_ids = [r[0] for r in team_id_rows]
        if not team_ids:
            return None
        return (await db.execute(
            select(MemoTemplate).where(
                MemoTemplate.team_id.in_(team_ids),
                MemoTemplate.is_default == True,
            ).limit(1)
        )).scalar_one_or_none()
    # 지정 id — read 권한 검사
    t = (await db.execute(
        select(MemoTemplate).where(MemoTemplate.id == template_id)
    )).scalar_one_or_none()
    if not t:
        return None
    if t.team_id is None:
        return t if t.user_id == user_id else None
    team_id_rows = (await db.execute(
        select(TeamMember.team_id).where(TeamMember.user_id == user_id)
    )).all()
    team_ids = {r[0] for r in team_id_rows}
    return t if t.team_id in team_ids else None


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


@router.get("", summary="메모 목록 — 본인 + 공유 visit 의 다른 사람 댓글")
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
    """본인이 관계된 visit_log 의 모든 메모 노출. 다른 사람 메모는 raw_memo strip,
    ai_summary 만 노출. is_root 는 같은 visit_log_id 내 created_at 가장 빠른 것."""
    from app.api.dashboard import _visit_user_filter

    user_filter = await _visit_user_filter(db, user.id)
    accessible_visit_ids = (await db.execute(
        select(VisitLog.id).where(user_filter)
    )).scalars().all()
    accessible_set = set(accessible_visit_ids)

    # 본인 메모 OR 본인이 관계된 visit_log 의 모든 메모 (orphan 본인 메모 포함)
    where_visibility = or_(
        VisitMemo.user_id == user.id,
        VisitMemo.visit_log_id.in_(accessible_set) if accessible_set else False,
    )
    query = (
        select(VisitMemo, User.name)
        .options(selectinload(VisitMemo.doctor).selectinload(Doctor.hospital))
        .outerjoin(User, VisitMemo.user_id == User.id)
        .where(where_visibility)
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

    rows = (await db.execute(query)).all()

    # is_root 결정 — 같은 visit_log_id 안에서 created_at 가장 빠른 메모 한 개를 root 로
    visit_ids_seen = {m.visit_log_id for m, _ in rows if m.visit_log_id}
    root_ids: set[int] = set()
    if visit_ids_seen:
        root_rows = (await db.execute(
            select(VisitMemo.visit_log_id, func.min(VisitMemo.id))
            .where(VisitMemo.visit_log_id.in_(visit_ids_seen))
            .group_by(VisitMemo.visit_log_id)
        )).all()
        root_ids = {row[1] for row in root_rows if row[1] is not None}

    return [
        _serialize(
            m,
            current_user_id=user.id,
            author_name=author_name,
            is_root=(m.id in root_ids) if m.visit_log_id else None,
        )
        for m, author_name in rows
    ]


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
#
# 권한 모델:
#   - 개인 템플릿 (team_id IS NULL): user_id 본인만 read/write
#   - 팀 템플릿 (team_id IS NOT NULL): 같은 팀 멤버 read, 팀 owner 만 write
# is_default 는 row 단위 — 팀 템플릿의 default 는 팀 owner 가 정하고 모든 멤버에게
# 적용되며, 개인 default 가 팀 default 보다 우선 (프론트 select 우선순위로 처리).

async def _user_team_ids(db: AsyncSession, user_id: int) -> list[int]:
    rows = (await db.execute(
        select(TeamMember.team_id).where(TeamMember.user_id == user_id)
    )).all()
    return [r[0] for r in rows]


async def _user_owned_team_ids(db: AsyncSession, user_id: int) -> list[int]:
    rows = (await db.execute(
        select(Team.id).where(Team.owner_user_id == user_id)
    )).all()
    return [r[0] for r in rows]


def _template_to_dict(t: MemoTemplate, *, owned_team_ids: set[int]) -> dict:
    try:
        fields = json.loads(t.fields) if t.fields else []
    except (TypeError, ValueError):
        fields = []
    is_team = t.team_id is not None
    is_owner = (
        (is_team and t.team_id in owned_team_ids)
        or (not is_team)  # 개인 템플릿은 항상 본인 소유
    )
    return {
        "id": t.id,
        "user_id": t.user_id,
        "team_id": t.team_id,
        "is_team": is_team,
        "is_owner": is_owner,
        "name": t.name,
        "fields": fields,
        "prompt_addon": t.prompt_addon,
        "is_default": bool(t.is_default),
        "scope": t.scope or "memo",
        "default_report_type": t.default_report_type,
        "created_at": iso_utc(t.created_at),
    }


_VALID_SCOPES = {"memo", "report", "both"}
_VALID_REPORT_TYPES = {"daily", "weekly"}


def _normalize_scope(value: Optional[str]) -> str:
    return value if value in _VALID_SCOPES else "memo"


def _normalize_report_type(value: Optional[str]) -> Optional[str]:
    return value if value in _VALID_REPORT_TYPES else None


async def _load_template_for_read(
    db: AsyncSession, template_id: int, user: User
) -> MemoTemplate:
    """본인 개인 템플릿 또는 내가 멤버인 팀의 팀 템플릿. 그 외엔 404."""
    t = (await db.execute(
        select(MemoTemplate).where(MemoTemplate.id == template_id)
    )).scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="템플릿을 찾을 수 없습니다.")
    if t.team_id is None:
        if t.user_id != user.id:
            raise HTTPException(status_code=404, detail="템플릿을 찾을 수 없습니다.")
    else:
        team_ids = await _user_team_ids(db, user.id)
        if t.team_id not in team_ids:
            raise HTTPException(status_code=404, detail="템플릿을 찾을 수 없습니다.")
    return t


async def _load_template_for_write(
    db: AsyncSession, template_id: int, user: User
) -> MemoTemplate:
    """개인 템플릿이면 본인만, 팀 템플릿이면 팀 owner 만."""
    t = await _load_template_for_read(db, template_id, user)
    if t.team_id is None:
        if t.user_id != user.id:
            raise HTTPException(status_code=403, detail="권한이 없습니다.")
    else:
        owned = await _user_owned_team_ids(db, user.id)
        if t.team_id not in owned:
            raise HTTPException(status_code=403, detail="팀 리더만 팀 템플릿을 수정할 수 있습니다.")
    return t


@templates_router.get("", summary="템플릿 목록")
async def list_templates(
    scope: Optional[str] = Query(None, description="memo | report (생략 시 전체)"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    team_ids = await _user_team_ids(db, user.id)
    owned_set = set(await _user_owned_team_ids(db, user.id))
    cond = MemoTemplate.user_id == user.id
    if team_ids:
        cond = (
            (MemoTemplate.team_id.is_(None) & (MemoTemplate.user_id == user.id))
            | (MemoTemplate.team_id.in_(team_ids))
        )
    query = (
        select(MemoTemplate)
        .where(cond)
        .order_by(
            MemoTemplate.team_id.is_(None).asc(),  # 팀 템플릿 먼저, 개인 나중 — 그 안에서 default 가 위
            MemoTemplate.is_default.desc(),
            MemoTemplate.id.asc(),
        )
    )
    if scope == "memo":
        query = query.where(MemoTemplate.scope.in_(["memo", "both"]))
    elif scope == "report":
        query = query.where(MemoTemplate.scope.in_(["report", "both"]))
    rows = (await db.execute(query)).scalars().all()
    return [_template_to_dict(t, owned_team_ids=owned_set) for t in rows]


@templates_router.post("", summary="템플릿 생성")
async def create_template(
    payload: MemoTemplateCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    scope = _normalize_scope(payload.scope)
    default_report_type = _normalize_report_type(payload.default_report_type)

    # 팀 템플릿 권한 체크 — 본인이 그 팀 owner 여야
    target_team_id = payload.team_id
    if target_team_id is not None:
        owned = await _user_owned_team_ids(db, user.id)
        if target_team_id not in owned:
            raise HTTPException(status_code=403, detail="팀 리더만 팀 템플릿을 만들 수 있습니다.")

    # is_default 결정 — 같은 scope(팀 vs 개인) 내에서 첫 메모 템플릿이면 자동 true
    if scope == "report":
        is_default = False
    else:
        if target_team_id is not None:
            existing_count = (await db.execute(
                select(func.count()).select_from(MemoTemplate)
                .where(
                    MemoTemplate.team_id == target_team_id,
                    MemoTemplate.scope.in_(["memo", "both"]),
                )
            )).scalar() or 0
        else:
            existing_count = (await db.execute(
                select(func.count()).select_from(MemoTemplate)
                .where(
                    MemoTemplate.team_id.is_(None),
                    MemoTemplate.user_id == user.id,
                    MemoTemplate.scope.in_(["memo", "both"]),
                )
            )).scalar() or 0
        is_default = bool(payload.is_default) or existing_count == 0

    t = MemoTemplate(
        user_id=user.id,
        team_id=target_team_id,
        name=payload.name,
        fields=json.dumps(payload.fields, ensure_ascii=False),
        prompt_addon=payload.prompt_addon,
        is_default=is_default,
        scope=scope,
        default_report_type=default_report_type,
    )
    if is_default:
        await _unset_other_defaults(db, user_id=user.id, team_id=target_team_id)
    db.add(t)
    await db.commit()
    await db.refresh(t)
    owned_set = set(await _user_owned_team_ids(db, user.id))
    return _template_to_dict(t, owned_team_ids=owned_set)


@templates_router.put("/{template_id}", summary="템플릿 수정")
async def update_template(
    template_id: int,
    payload: MemoTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    t = await _load_template_for_write(db, template_id, user)
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
        await _unset_other_defaults(
            db, user_id=t.user_id, team_id=t.team_id, exclude_id=t.id,
        )
    for k, v in data.items():
        setattr(t, k, v)
    await db.commit()
    await db.refresh(t)
    owned_set = set(await _user_owned_team_ids(db, user.id))
    return _template_to_dict(t, owned_team_ids=owned_set)


@templates_router.delete("/{template_id}", summary="템플릿 삭제")
async def delete_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    t = await _load_template_for_write(db, template_id, user)
    if t.is_default:
        raise HTTPException(status_code=400, detail="기본 템플릿은 삭제할 수 없습니다.")
    await db.delete(t)
    await db.commit()
    return {"ok": True}


async def _unset_other_defaults(
    db: AsyncSession,
    *,
    user_id: int,
    team_id: Optional[int],
    exclude_id: Optional[int] = None,
):
    """같은 scope(개인 또는 같은 팀) 내 다른 is_default=true 행을 false 로."""
    if team_id is not None:
        query = select(MemoTemplate).where(
            MemoTemplate.team_id == team_id,
            MemoTemplate.is_default == True,
        )
    else:
        query = select(MemoTemplate).where(
            MemoTemplate.team_id.is_(None),
            MemoTemplate.user_id == user_id,
            MemoTemplate.is_default == True,
        )
    rows = (await db.execute(query)).scalars().all()
    for row in rows:
        if exclude_id and row.id == exclude_id:
            continue
        row.is_default = False
