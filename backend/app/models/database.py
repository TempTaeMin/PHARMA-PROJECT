"""Database models for PharmScheduler"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship, declarative_base
import enum

Base = declarative_base()


class VisitGrade(str, enum.Enum):
    A = "A"  # 주1회
    B = "B"  # 격주
    C = "C"  # 월1회


class Hospital(Base):
    __tablename__ = "hospitals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    code = Column(String(50), unique=True, nullable=False)  # 병원 고유 코드
    address = Column(String(500))
    phone = Column(String(50))
    website = Column(String(500))
    crawler_type = Column(String(50))  # 크롤러 어댑터 타입
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    doctors = relationship("Doctor", back_populates="hospital")


class Doctor(Base):
    __tablename__ = "doctors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    name = Column(String(100), nullable=False)
    department = Column(String(200))  # 진료과
    position = Column(String(100))  # 직위 (교수, 부교수 등)
    specialty = Column(Text)  # 전문 분야
    profile_url = Column(String(500))  # 병원 홈페이지 프로필 URL
    photo_url = Column(String(500))
    external_id = Column(String(100))  # 병원 시스템 내 의료진 ID
    visit_grade = Column(String(1), nullable=True, default=None)  # A/B/C=내교수, None=탐색용
    memo = Column(Text)  # MR 개인 메모
    notes = Column(Text)  # 크롤링 특이사항 (여러 병원 진료, 복수 소속 등)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    hospital = relationship("Hospital", back_populates="doctors")
    schedules = relationship("DoctorSchedule", back_populates="doctor")
    date_schedules = relationship("DoctorDateSchedule", back_populates="doctor")
    visit_logs = relationship("VisitLog", back_populates="doctor")


class DoctorSchedule(Base):
    """교수 진료 일정 (크롤링 데이터)"""
    __tablename__ = "doctor_schedules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=False)
    day_of_week = Column(Integer, nullable=False)  # 0=월 ~ 6=일
    time_slot = Column(String(20))  # "morning", "afternoon", "evening"
    start_time = Column(String(10))  # "09:00"
    end_time = Column(String(10))  # "12:00"
    location = Column(String(200))  # 진료실 위치
    is_active = Column(Boolean, default=True)
    crawled_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    doctor = relationship("Doctor", back_populates="schedules")


class DoctorDateSchedule(Base):
    """날짜별 진료 일정 (특정 날짜 데이터를 제공하는 병원용)"""
    __tablename__ = "doctor_date_schedules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=False)
    schedule_date = Column(String(10), nullable=False)  # "2026-04-08"
    time_slot = Column(String(20))  # "morning", "afternoon"
    start_time = Column(String(10))
    end_time = Column(String(10))
    location = Column(String(200))
    status = Column(String(20), default="진료")  # "진료", "휴진", "대진"
    crawled_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

    doctor = relationship("Doctor", back_populates="date_schedules")


class ScheduleChange(Base):
    """진료 일정 변경 이력 (휴진, 대진 등)"""
    __tablename__ = "schedule_changes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=False)
    change_type = Column(String(50))  # "휴진", "대진", "시간변경", "추가"
    original_day = Column(Integer)
    original_time_slot = Column(String(20))
    new_day = Column(Integer)
    new_time_slot = Column(String(20))
    start_date = Column(String(10))  # "2026-04-01"
    end_date = Column(String(10))  # "2026-04-05"
    reason = Column(Text)
    detected_at = Column(DateTime, default=datetime.utcnow)
    notified = Column(Boolean, default=False)


class VisitLog(Base):
    """방문 기록 / 개인 일정"""
    __tablename__ = "visit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=True)
    visit_date = Column(DateTime, nullable=False)
    status = Column(String(20))  # "성공", "부재", "거절", "예정"
    product = Column(String(200))  # 디테일링 제품
    notes = Column(Text)  # 방문 메모
    next_action = Column(Text)  # 다음 액션
    category = Column(String(20), default='professor')  # 'professor' | 'personal' | 'etc'
    title = Column(String(200))  # 개인 일정 제목 등
    created_at = Column(DateTime, default=datetime.utcnow)

    doctor = relationship("Doctor", back_populates="visit_logs")


class AcademicOrganizer(Base):
    """대한의학회 회원학회 마스터 리스트. 연 1회 KAMS 에서 seed."""
    __tablename__ = "academic_organizers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(300), unique=True, nullable=False, index=True)
    name_en = Column(String(300))
    domain = Column(String(20))  # KAMS 8개 영역 (I~VIII)
    membership_type = Column(String(20))  # "정회원" | "준회원" | "기간학회"
    homepage = Column(String(500))
    departments_json = Column(Text)  # JSON: ["비뇨의학과", ...]
    classification_status = Column(String(20), default="unclassified")  # "mapped" | "keyword" | "unclassified"
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AcademicEvent(Base):
    """월 1회 크롤링되는 학술행사 이벤트."""
    __tablename__ = "academic_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(500), nullable=False)
    organizer_name = Column(String(300), index=True)
    organizer_id = Column(Integer, ForeignKey("academic_organizers.id"), nullable=True)
    start_date = Column(String(10))  # "2026-05-10" ISO
    end_date = Column(String(10))  # "2026-05-12"
    location = Column(String(300))
    url = Column(String(500))
    description = Column(Text)
    source = Column(String(50), default="kma_edu")  # "kma_edu"
    classification_status = Column(String(20), default="unclassified")  # "kma" | "mapped" | "keyword" | "unclassified"
    external_key = Column(String(100), unique=True, index=True)
    kma_category = Column(String(200))  # KMA 임상의학 원본 (콤마 구분, 예: "정형외과, 마취통증의학과")
    kma_eduidx = Column(String(50), index=True)  # KMA 상세 페이지 ID
    sub_organizer = Column(String(300))  # 주관 (공동/하위 기관)
    region = Column(String(100))  # 지역 (예: 서울, 경기)
    event_code = Column(String(100))  # 교육코드 (KMA)
    detail_url_external = Column(String(500))  # 비고에 기재된 외부 상세 URL (학회 자체 페이지 등)
    lectures_json = Column(Text)  # 강의 프로그램 JSON: [{time,title,lecturer,affiliation}]
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    departments = relationship(
        "AcademicEventDepartment",
        back_populates="event",
        cascade="all, delete-orphan",
    )


class AcademicEventDepartment(Base):
    """이벤트-진료과 many-to-many 조인."""
    __tablename__ = "academic_event_departments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(Integer, ForeignKey("academic_events.id"), index=True)
    department = Column(String(100), nullable=False, index=True)

    event = relationship("AcademicEvent", back_populates="departments")


class MemoTemplate(Base):
    """메모/회의록 정리용 템플릿 (AI 프롬프트 구성)."""
    __tablename__ = "memo_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, default=1, nullable=False)  # 인증 도입 전까지 1
    name = Column(String(200), nullable=False)
    fields = Column(Text, nullable=False)  # JSON array of field names
    prompt_addon = Column(Text)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class VisitMemo(Base):
    """MR 방문 메모/회의록 (raw + AI 정리본)."""
    __tablename__ = "visits_memo"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, default=1, nullable=False)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=True)
    visit_log_id = Column(Integer, ForeignKey("visit_logs.id"), nullable=True)
    template_id = Column(Integer, ForeignKey("memo_templates.id"), nullable=True)
    visit_date = Column(DateTime)
    memo_type = Column(String(20), default="visit")  # "visit" | "meeting" | "note"
    title = Column(String(300))
    raw_memo = Column(Text, nullable=False)
    ai_summary = Column(Text)  # JSON string
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    doctor = relationship("Doctor")
    visit_log = relationship("VisitLog")
    template = relationship("MemoTemplate")


class CrawlLog(Base):
    """크롤링 실행 로그"""
    __tablename__ = "crawl_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    hospital_code = Column(String(50), nullable=False)
    status = Column(String(20))  # "success", "failed", "partial"
    doctors_crawled = Column(Integer, default=0)
    schedules_updated = Column(Integer, default=0)
    changes_detected = Column(Integer, default=0)
    error_message = Column(Text)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime)
