"""개인 일정/플랫 방문 로그 API"""
import json
import logging
from typing import Iterable, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)

from app.auth.deps import get_current_user, get_my_team_id, get_team_member_ids
from app.models.connection import get_db
from app.models.database import (
    Doctor, MemoTemplate, User, VisitLog, VisitMemo, visit_log_recipients,
)
from app.notifications.manager import notification_manager
from app.schemas.schemas import AnnouncementCreate, PersonalEventCreate, SummarizeRequest
from app.services.ai_memo import organize_memo, summarize_freeform

router = APIRouter(prefix="/api/visits", tags=["방문 로그"])


CATEGORY_LABEL = {
    "personal": "개인 일정",
    "announcement": "공지",
    "professor": "교수 방문",
    "etc": "일정",
}


def _format_visit_date(visit) -> str:
    if not visit.visit_date:
        return ""
    d = visit.visit_date
    return f"{d.month}/{d.day} {d.hour:02d}:{d.minute:02d}" if visit.category != "announcement" else f"{d.month}/{d.day}"


async def _broadcast_visit_shared(
    db: AsyncSession,
    visit: VisitLog,
    owner: User,
    action: str = "created",
    recipient_ids: Optional[Iterable[int]] = None,
) -> None:
    """visibility='team' 인 visit 가 생성/변경될 때 선택된 수신자들에게 알림 push.

    recipient_ids 미지정 시 visit.recipients 에서 추출.
    """
    if (visit.visibility or "private") != "team":
        return
    if recipient_ids is None:
        recipient_ids = [u.id for u in (visit.recipients or [])]
    targets = [uid for uid in recipient_ids if uid != owner.id]
    if not targets:
        return

    cat_label = CATEGORY_LABEL.get(visit.category, "일정")
    title = visit.title or (visit.doctor_name_snapshot or cat_label)
    date_label = _format_visit_date(visit)
    owner_name = owner.name or owner.email
    action_word = "공유했어요" if action == "created" else "팀 공유로 변경했어요"
    message = f"{owner_name} 님이 {cat_label}을(를) {action_word}: {title}" + (f" ({date_label})" if date_label else "")

    payload = {
        "type": "team_visit_shared",
        "data": {
            "visit_id": visit.id,
            "owner_user_id": owner.id,
            "owner_name": owner_name,
            "title": title,
            "visit_date": visit.visit_date.isoformat() if visit.visit_date else None,
            "category": visit.category,
            "action": action,
            "message": message,
        },
    }
    for uid in targets:
        try:
            await notification_manager.send_to_user(str(uid), payload)
        except Exception as e:
            logger.warning(f"team_visit_shared 알림 발송 실패 (user={uid}): {e}")


async def _broadcast_visit_removed(
    db: AsyncSession,
    visit: VisitLog,
    owner: User,
    recipient_ids: Iterable[int],
) -> None:
    """visit 삭제/팀공유 해제/수신자 제거 시 대상에게 알림 push.

    cascade 후엔 visit.recipients 가 비므로 caller 가 ids 스냅샷을 미리 넘김.
    """
    targets = [uid for uid in recipient_ids if uid != owner.id]
    if not targets:
        return

    cat_label = CATEGORY_LABEL.get(visit.category, "일정")
    title = visit.title or (visit.doctor_name_snapshot or cat_label)
    owner_name = owner.name or owner.email
    message = f"{owner_name} 님이 공유했던 {cat_label} '{title}' 을 삭제했습니다"

    payload = {
        "type": "team_visit_removed",
        "data": {
            "visit_id": visit.id,
            "owner_user_id": owner.id,
            "owner_name": owner_name,
            "title": title,
            "category": visit.category,
            "message": message,
        },
    }
    for uid in targets:
        try:
            await notification_manager.send_to_user(str(uid), payload)
        except Exception as e:
            logger.warning(f"team_visit_removed 알림 발송 실패 (user={uid}): {e}")


async def _broadcast_visit_diff(
    db: AsyncSession,
    visit: VisitLog,
    owner: User,
    old_ids: Iterable[int],
    new_ids: Iterable[int],
) -> None:
    """수신자 리스트 변경 시 added 에는 shared, removed 에는 removed 알림."""
    old_set = set(old_ids)
    new_set = set(new_ids)
    added = list(new_set - old_set)
    removed = list(old_set - new_set)
    if added:
        await _broadcast_visit_shared(db, visit, owner, action="updated", recipient_ids=added)
    if removed:
        await _broadcast_visit_removed(db, visit, owner, removed)


async def _validate_recipients(
    db: AsyncSession, owner: User, ids: Optional[list[int]]
) -> list[int]:
    """수신자 리스트 검증. 같은 팀의 본인 외 멤버여야 함. 빈 리스트는 거부."""
    cleaned = [uid for uid in dict.fromkeys(ids or []) if uid != owner.id]
    if not cleaned:
        raise HTTPException(400, "팀 공유 일정은 1명 이상의 수신자를 선택해야 합니다.")
    my_team_id = await get_my_team_id(db, owner.id)
    if not my_team_id:
        raise HTTPException(400, "팀에 속해있지 않아 팀 공유 일정을 만들 수 없습니다.")
    member_ids = set(await get_team_member_ids(db, my_team_id))
    invalid = [uid for uid in cleaned if uid not in member_ids]
    if invalid:
        raise HTTPException(400, f"같은 팀이 아닌 사용자가 포함됐습니다: {invalid}")
    return cleaned


async def _apply_recipients(
    db: AsyncSession, visit: VisitLog, ids: list[int]
) -> None:
    """visit_log_recipients 행을 ids 와 일치하도록 교체. 기존 행은 모두 지우고 다시 삽입."""
    await db.execute(
        visit_log_recipients.delete().where(
            visit_log_recipients.c.visit_log_id == visit.id
        )
    )
    if ids:
        await db.execute(
            visit_log_recipients.insert(),
            [{"visit_log_id": visit.id, "recipient_user_id": uid} for uid in ids],
        )


_VALID_VISIBILITIES = {"private", "team"}


async def _resolve_visibility(
    raw: Optional[str], db: AsyncSession, user: User, default: str = "private"
) -> str:
    """visibility 검증 + 팀 미소속 시 'team' 거부."""
    value = raw or default
    if value not in _VALID_VISIBILITIES:
        raise HTTPException(status_code=400, detail="visibility 는 'private' 또는 'team' 이어야 합니다.")
    if value == "team":
        my_team_id = await get_my_team_id(db, user.id)
        if not my_team_id:
            raise HTTPException(
                status_code=400,
                detail="팀에 속해있지 않아 팀 공유 일정을 만들 수 없습니다. 먼저 팀을 만들거나 초대받으세요.",
            )
    return value


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
        "visibility": visit.visibility or "private",
        "recipient_user_ids": [u.id for u in (visit.recipients or [])],
    }


@router.post("/personal", summary="개인 일정 등록")
async def create_personal_event(
    data: PersonalEventCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    title = (data.title or "").strip() or "내 일정"
    visibility = await _resolve_visibility(data.visibility, db, user, default="private")
    recipient_ids: list[int] = []
    if visibility == "team":
        recipient_ids = await _validate_recipients(db, user, data.recipient_user_ids)
    visit = VisitLog(
        user_id=user.id,
        doctor_id=None,
        visit_date=data.visit_date,
        status=data.status or "예정",
        notes=data.notes,
        title=title,
        category="personal",
        visibility=visibility,
    )
    db.add(visit)
    await db.flush()
    if recipient_ids:
        await _apply_recipients(db, visit, recipient_ids)
    await db.commit()
    await db.refresh(visit)
    await _broadcast_visit_shared(db, visit, user, action="created", recipient_ids=recipient_ids)
    return _visit_to_dict(visit)


@router.delete("/{visit_id}", summary="방문 로그 삭제 (개인/공지 포함)")
async def delete_visit(
    visit_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    visit = (await db.execute(
        select(VisitLog).where(VisitLog.id == visit_id, VisitLog.user_id == user.id)
    )).scalar_one_or_none()
    if not visit:
        raise HTTPException(404, "visit not found")
    is_team = (visit.visibility or "private") == "team"
    old_ids = [u.id for u in (visit.recipients or [])] if is_team else []
    await db.delete(visit)
    await db.commit()
    if is_team and old_ids:
        await _broadcast_visit_removed(db, visit, user, old_ids)
    return {"status": "deleted", "id": visit_id}


@router.patch("/{visit_id}", summary="방문 로그 수정 (개인/공지 · doctor_id 무관)")
async def update_visit_flat(
    visit_id: int,
    data: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """doctor_id 없이도 동작하는 플랫 PATCH — 개인 일정/공지에서 사용.
    교수 방문의 경우 기존 /api/doctors/{doctor_id}/visits/{visit_id} 를 계속 사용."""
    visit = (await db.execute(
        select(VisitLog).where(VisitLog.id == visit_id, VisitLog.user_id == user.id)
    )).scalar_one_or_none()
    if not visit:
        raise HTTPException(404, "visit not found")
    prev_visibility = visit.visibility or "private"
    prev_recipient_ids = [u.id for u in (visit.recipients or [])]
    allowed = {"status", "notes", "post_notes", "title", "visit_date", "visibility"}
    if "visibility" in data:
        data["visibility"] = await _resolve_visibility(
            data.get("visibility"), db, user, default="private"
        )
    for key, value in data.items():
        if key not in allowed:
            continue
        if key == "visit_date" and isinstance(value, str):
            from datetime import datetime as _dt
            value = _dt.fromisoformat(value.replace("Z", "+00:00"))
        setattr(visit, key, value)

    new_visibility = visit.visibility or "private"
    new_recipient_ids = list(prev_recipient_ids)
    recipients_provided = "recipient_user_ids" in data

    if new_visibility == "team":
        if recipients_provided:
            new_recipient_ids = await _validate_recipients(db, user, data.get("recipient_user_ids"))
            await _apply_recipients(db, visit, new_recipient_ids)
        elif prev_visibility != "team":
            raise HTTPException(400, "팀 공유로 변경할 때는 recipient_user_ids 가 필요합니다.")
        # else: 기존 'team' 의 비공유 필드만 수정 — recipients 그대로
    elif prev_visibility == "team":
        # team → private 강등 — recipients 비움
        await _apply_recipients(db, visit, [])
        new_recipient_ids = []

    await db.commit()
    await db.refresh(visit)

    if prev_visibility != "team" and new_visibility == "team":
        await _broadcast_visit_shared(db, visit, user, action="updated_to_team", recipient_ids=new_recipient_ids)
    elif prev_visibility == "team" and new_visibility != "team":
        await _broadcast_visit_removed(db, visit, user, prev_recipient_ids)
    elif prev_visibility == "team" and new_visibility == "team":
        await _broadcast_visit_diff(db, visit, user, prev_recipient_ids, new_recipient_ids)
    return _visit_to_dict(visit)


@router.post("/announcement", summary="업무공지 등록")
async def create_announcement(
    data: AnnouncementCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """업무공지(category='announcement') 등록. 'team' 시 수신자 리스트 필수."""
    title = (data.title or "").strip()
    if not title:
        raise HTTPException(400, "title is required")
    # 팀 미소속이면 자동으로 'private' 으로 떨어지게
    my_team_id = await get_my_team_id(db, user.id)
    desired = data.visibility or ("team" if my_team_id else "private")
    visibility = await _resolve_visibility(desired, db, user, default="private")
    recipient_ids: list[int] = []
    if visibility == "team":
        recipient_ids = await _validate_recipients(db, user, data.recipient_user_ids)
    visit = VisitLog(
        user_id=user.id,
        doctor_id=None,
        visit_date=data.visit_date,
        status="예정",
        notes=data.notes,
        title=title,
        category="announcement",
        visibility=visibility,
    )
    db.add(visit)
    await db.flush()
    if recipient_ids:
        await _apply_recipients(db, visit, recipient_ids)
    await db.commit()
    await db.refresh(visit)
    await _broadcast_visit_shared(db, visit, user, action="created", recipient_ids=recipient_ids)
    return _visit_to_dict(visit)


# ─────────── AI 정리 ───────────

def _parse_ai(raw: Optional[str]):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return raw


async def _load_default_template(db: AsyncSession, user_id: int) -> Optional[MemoTemplate]:
    query = (
        select(MemoTemplate)
        .where(MemoTemplate.user_id == user_id, MemoTemplate.is_default == True)
        .limit(1)
    )
    return (await db.execute(query)).scalar_one_or_none()


@router.post("/{visit_id}/ai-summarize", summary="방문 메모 AI 정리 (Claude Haiku)")
async def ai_summarize_visit(
    visit_id: int,
    payload: SummarizeRequest = SummarizeRequest(),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """VisitLog 의 메모를 AI 로 정리하여 VisitMemo 에 저장.

    - 교수 방문(doctor_id 존재): post_notes 를 source 로 사용
    - 개인 일정/업무공지: notes 를 source 로 사용
    - 기존 VisitMemo(visit_log_id 링크)가 있으면 갱신, 없으면 생성
    - 공유받은 visit (recipient) 도 호출 가능 — VisitMemo 는 user_id 로 분리되어
      각자의 메모로 저장됨.
    """
    from app.api.dashboard import _visit_user_filter

    user_filter = await _visit_user_filter(db, user.id)
    query = (
        select(VisitLog)
        .options(selectinload(VisitLog.doctor).selectinload(Doctor.hospital))
        .where(VisitLog.id == visit_id, user_filter)
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
            template = await _load_default_template(db, user.id)

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
            user_id=user.id,
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
