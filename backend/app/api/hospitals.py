"""병원 관리 API"""
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.connection import get_db
from app.models.database import Hospital
from app.schemas.schemas import HospitalBase, HospitalResponse

router = APIRouter(prefix="/api/hospitals", tags=["병원 관리"])


@router.get("/", summary="병원 목록", response_model=list[HospitalResponse])
async def list_hospitals(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Hospital).where(Hospital.is_active == True))
    return result.scalars().all()


@router.get("/{hospital_id}", summary="병원 상세", response_model=HospitalResponse)
async def get_hospital(hospital_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Hospital).where(Hospital.id == hospital_id))
    hospital = result.scalar_one_or_none()
    if not hospital:
        raise HTTPException(status_code=404, detail="병원을 찾을 수 없습니다.")
    return hospital


@router.post("/", summary="병원 등록", response_model=HospitalResponse)
async def create_hospital(data: HospitalBase, db: AsyncSession = Depends(get_db)):
    """병원을 등록합니다. body 에 source 가 없으면 'manual' 기본
    (크롤러가 등록하는 병원은 factory 기반 seed 또는 source='crawler' 명시).
    code 가 비어 있으면 MANUAL_{8자리} 자동 발급.
    """
    payload = data.model_dump(exclude_unset=True)
    if not payload.get("source"):
        payload["source"] = "manual"
    if not payload.get("code"):
        payload["code"] = f"MANUAL_{uuid.uuid4().hex[:8].upper()}"

    # 중복 code 체크
    existing = (await db.execute(
        select(Hospital).where(Hospital.code == payload["code"])
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail=f"병원 코드 {payload['code']} 이미 존재")

    hospital = Hospital(**payload)
    db.add(hospital)
    await db.commit()
    await db.refresh(hospital)
    return hospital
