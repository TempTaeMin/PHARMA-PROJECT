"""병원 관리 API"""
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
    hospital = Hospital(**data.model_dump())
    db.add(hospital)
    await db.commit()
    await db.refresh(hospital)
    return hospital
