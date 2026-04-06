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
    """방문 기록"""
    __tablename__ = "visit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=False)
    visit_date = Column(DateTime, nullable=False)
    status = Column(String(20))  # "성공", "부재", "거절", "예정"
    product = Column(String(200))  # 디테일링 제품
    notes = Column(Text)  # 방문 메모
    next_action = Column(Text)  # 다음 액션
    created_at = Column(DateTime, default=datetime.utcnow)

    doctor = relationship("Doctor", back_populates="visit_logs")


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
