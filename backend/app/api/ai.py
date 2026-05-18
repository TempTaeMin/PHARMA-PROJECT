"""AI 보조 도구 API.

방문 결과 form 입력 흐름에서 사용자가 한 필드에 거칠게 작성한 텍스트를
정돈하는 데 쓴다. 입력 자체를 결정하거나 필드를 채우지 않고, 사용자가
명시적으로 호출했을 때만 그 필드의 텍스트만 다듬는다.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.deps import get_current_user
from app.models.connection import get_db
from app.models.database import Doctor, User, VisitLog
from app.schemas.schemas import RefineFieldRequest
from app.services.ai_memo import refine_field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["AI"])


@router.post("/refine-field", summary="단일 필드 AI 다듬기")
async def refine_field_endpoint(
    payload: RefineFieldRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """사용자가 form 한 필드에 거칠게 쓴 텍스트를 정돈해서 반환.

    - 원문에 없는 사실 추가 금지 (system prompt 로 강제)
    - 단일 평문 string 반환, 호출자는 결과를 검토 후 적용/취소 결정
    - visit_id 를 같이 보내면 교수/병원/진료과 컨텍스트로 더 자연스러운 정돈 가능
    """
    if not payload.value or not payload.value.strip():
        raise HTTPException(status_code=400, detail="value 가 비어있습니다.")

    context = {}
    if payload.visit_id is not None:
        # visit 권한 확인 — 본인 또는 recipient
        from app.api.dashboard import _visit_user_filter
        user_filter = await _visit_user_filter(db, user.id)
        visit = (await db.execute(
            select(VisitLog)
            .options(selectinload(VisitLog.doctor).selectinload(Doctor.hospital))
            .where(VisitLog.id == payload.visit_id, user_filter)
        )).scalar_one_or_none()
        if visit and visit.doctor:
            doctor = visit.doctor
            context = {
                "doctor_name": doctor.name,
                "department": doctor.department,
                "hospital_name": doctor.hospital.name if doctor.hospital else None,
            }

    refined = await refine_field(
        value=payload.value,
        field_key=payload.field_key,
        context=context or None,
    )
    return {"refined_value": refined}
