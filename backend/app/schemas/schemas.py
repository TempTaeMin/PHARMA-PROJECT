"""API Request/Response schemas"""
from pydantic import BaseModel
from typing import Optional, Any
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


# --- Date Schedule ---
class DateScheduleResponse(BaseModel):
    id: int
    doctor_id: int
    schedule_date: str
    time_slot: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    location: Optional[str] = None
    status: Optional[str] = "진료"
    crawled_at: Optional[datetime] = None
    class Config:
        from_attributes = True


# --- Doctor with Schedule ---
class DoctorWithSchedule(DoctorResponse):
    schedules: list[ScheduleResponse] = []
    date_schedules: list[DateScheduleResponse] = []
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
    date_schedules: list[dict] = []  # [{schedule_date, time_slot, start_time, end_time, location, status}]


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


class PersonalEventCreate(BaseModel):
    visit_date: datetime
    title: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = "예정"


# --- Academic Organizer ---
class AcademicOrganizerBase(BaseModel):
    name: str
    name_en: Optional[str] = None
    domain: Optional[str] = None
    membership_type: Optional[str] = None
    homepage: Optional[str] = None

class AcademicOrganizerResponse(AcademicOrganizerBase):
    id: int
    departments: list[str] = []
    classification_status: str
    class Config:
        from_attributes = True

class AcademicOrganizerDepartmentsUpdate(BaseModel):
    departments: list[str]


# --- Academic Event ---
class AcademicEventBase(BaseModel):
    name: str
    organizer_name: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    location: Optional[str] = None
    url: Optional[str] = None
    description: Optional[str] = None

class AcademicEventResponse(AcademicEventBase):
    id: int
    departments: list[str] = []
    classification_status: str
    source: Optional[str] = None
    kma_category: Optional[str] = None
    kma_eduidx: Optional[str] = None
    class Config:
        from_attributes = True

class AcademicEventDepartmentsUpdate(BaseModel):
    departments: list[str]


# --- Memo Template ---
class MemoTemplateBase(BaseModel):
    name: str
    fields: list[str]
    prompt_addon: Optional[str] = None
    is_default: Optional[bool] = False

class MemoTemplateCreate(MemoTemplateBase):
    pass

class MemoTemplateUpdate(BaseModel):
    name: Optional[str] = None
    fields: Optional[list[str]] = None
    prompt_addon: Optional[str] = None
    is_default: Optional[bool] = None

class MemoTemplateResponse(MemoTemplateBase):
    id: int
    user_id: int
    created_at: datetime
    class Config:
        from_attributes = True


# --- Visit Memo ---
class VisitMemoCreate(BaseModel):
    doctor_id: Optional[int] = None
    visit_log_id: Optional[int] = None
    template_id: Optional[int] = None
    visit_date: Optional[datetime] = None
    memo_type: Optional[str] = "visit"  # "visit" | "meeting" | "note"
    title: Optional[str] = None
    raw_memo: str

class VisitMemoUpdate(BaseModel):
    doctor_id: Optional[int] = None
    visit_log_id: Optional[int] = None
    template_id: Optional[int] = None
    visit_date: Optional[datetime] = None
    memo_type: Optional[str] = None
    title: Optional[str] = None
    raw_memo: Optional[str] = None
    ai_summary: Optional[Any] = None  # dict or JSON string

class VisitMemoResponse(BaseModel):
    id: int
    user_id: int
    doctor_id: Optional[int] = None
    doctor_name: Optional[str] = None
    hospital_name: Optional[str] = None
    department: Optional[str] = None
    visit_log_id: Optional[int] = None
    template_id: Optional[int] = None
    visit_date: Optional[datetime] = None
    memo_type: Optional[str] = None
    title: Optional[str] = None
    raw_memo: str
    ai_summary: Optional[Any] = None  # parsed JSON
    created_at: datetime
    updated_at: Optional[datetime] = None


class SummarizeRequest(BaseModel):
    template_id: Optional[int] = None
