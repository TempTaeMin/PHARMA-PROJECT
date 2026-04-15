"""개인 일정/플랫 방문 로그 API"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.connection import get_db
from app.models.database import VisitLog
from app.schemas.schemas import PersonalEventCreate

router = APIRouter(prefix="/api/visits", tags=["방문 로그"])


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
    return {
        "id": visit.id,
        "doctor_id": None,
        "visit_date": visit.visit_date.isoformat(),
        "status": visit.status,
        "notes": visit.notes,
        "title": visit.title,
        "category": visit.category,
    }
