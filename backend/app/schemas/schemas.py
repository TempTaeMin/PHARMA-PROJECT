"""API Request/Response schemas"""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


# --- Hospital ---
class HospitalBase(BaseModel):
    name: str
    code: str
    address: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None

class HospitalResponse(HospitalBase):
    id: int
    crawler_type: Optional[str] = None
    is_active: bool
    class Config:
        from_attributes = True


# --- Doctor ---
class DoctorBase(BaseModel):
    name: str
    hospital_id: int
    department: Optional[str] = None
    position: Optional[str] = None
    specialty: Optional[str] = None
    visit_grade: Optional[str] = None
    memo: Optional[str] = None

class DoctorResponse(DoctorBase):
    id: int
    profile_url: Optional[str] = None
    photo_url: Optional[str] = None
    notes: Optional[str] = None
    is_active: bool
    class Config:
        from_attributes = True


# --- Schedule ---
class ScheduleResponse(BaseModel):
    id: int
    doctor_id: int
    day_of_week: int
    time_slot: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    location: Optional[str] = None
    is_active: bool
    crawled_at: Optional[datetime] = None
    class Config:
        from_attributes = True


# --- Doctor with Schedule ---
class DoctorWithSchedule(DoctorResponse):
    schedules: list[ScheduleResponse] = []
    hospital_name: Optional[str] = None


# --- Crawl Result ---
class CrawledDoctor(BaseModel):
    name: str
    department: str
    position: Optional[str] = None
    specialty: Optional[str] = None
    profile_url: Optional[str] = None
    photo_url: Optional[str] = None
    external_id: Optional[str] = None
    notes: Optional[str] = None  # 특이사항 (여러 병원 진료, 복수 소속 등)
    schedules: list[dict] = []  # [{day_of_week, time_slot, start_time, end_time, location}]


class CrawlResult(BaseModel):
    hospital_code: str
    hospital_name: str
    status: str  # "success", "failed", "partial"
    doctors: list[CrawledDoctor] = []
    error_message: Optional[str] = None
    crawled_at: datetime = datetime.utcnow()


# --- Visit Log ---
class VisitLogCreate(BaseModel):
    doctor_id: int
    visit_date: datetime
    status: str
    product: Optional[str] = None
    notes: Optional[str] = None
    next_action: Optional[str] = None

class VisitLogResponse(VisitLogCreate):
    id: int
    created_at: datetime
    class Config:
        from_attributes = True
