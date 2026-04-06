"""DB 초기 시드 데이터"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.database import Hospital, Doctor, DoctorSchedule, VisitLog
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

SEED_HOSPITALS = [
    {"name": "서울아산병원", "code": "AMC", "address": "서울 송파구 올림픽로 43길 88", "phone": "1688-7575", "website": "https://www.amc.seoul.kr", "crawler_type": "asan_medical"},
    {"name": "서울대학교병원", "code": "SNUH", "address": "서울 종로구 대학로 101", "phone": "1588-5700", "website": "https://www.snuh.org", "crawler_type": "snuh"},
    {"name": "삼성서울병원", "code": "SMC", "address": "서울 강남구 일원로 81", "phone": "1599-3114", "website": "https://www.samsunghospital.com", "crawler_type": "samsung_medical"},
    {"name": "세브란스병원", "code": "SEVERANCE", "address": "서울 서대문구 연세로 50-1", "phone": "1599-1004", "website": "https://sev.severance.healthcare", "crawler_type": "severance"},
    {"name": "서울성모병원", "code": "CMCSEOUL", "address": "서울 서초구 반포대로 222", "phone": "1588-1511", "website": "https://www.cmcseoul.or.kr", "crawler_type": "seoul_st_mary"},
]

SEED_DOCTORS = [
    {"name": "김정형", "department": "정형외과", "position": "교수", "specialty": "슬관절, 인공관절 치환술", "hospital_code": "AMC", "external_id": "AMC-001", "visit_grade": "A", "memo": "오전 진료 후 12시쯤 선호, 골프 좋아하심",
     "schedules": [{"day_of_week": 0, "time_slot": "morning"}, {"day_of_week": 2, "time_slot": "morning"}, {"day_of_week": 4, "time_slot": "afternoon"}],
     "visits": [{"days_ago": 7, "status": "성공", "product": "관절주사A", "notes": "처방 의향 긍정적, 다음 주 샘플 전달", "next_action": "샘플 전달"}]},
    {"name": "이척추", "department": "정형외과", "position": "교수", "specialty": "척추외과, 척추변형", "hospital_code": "AMC", "external_id": "AMC-002", "visit_grade": "B", "memo": "목요일 오후 선호",
     "schedules": [{"day_of_week": 1, "time_slot": "morning"}, {"day_of_week": 3, "time_slot": "morning"}, {"day_of_week": 3, "time_slot": "afternoon"}],
     "visits": [{"days_ago": 26, "status": "성공", "product": "진통제B", "notes": "경쟁사 제품 사용 중, 전환 가능성"}]},
    {"name": "박관절", "department": "정형외과", "position": "부교수", "specialty": "어깨관절, 스포츠의학", "hospital_code": "AMC", "external_id": "AMC-003", "visit_grade": "A",
     "schedules": [{"day_of_week": 0, "time_slot": "afternoon"}, {"day_of_week": 2, "time_slot": "afternoon"}, {"day_of_week": 4, "time_slot": "morning"}],
     "visits": [{"days_ago": 2, "status": "성공", "product": "관절주사A", "notes": "신규 임상 데이터에 관심"}]},
    {"name": "최신경", "department": "신경외과", "position": "교수", "specialty": "뇌종양, 뇌혈관", "hospital_code": "SNUH", "external_id": "SNUH-001", "visit_grade": "A", "memo": "월요일만 가능",
     "schedules": [{"day_of_week": 0, "time_slot": "morning"}, {"day_of_week": 3, "time_slot": "afternoon"}],
     "visits": [{"days_ago": 9, "status": "부재", "product": "-", "notes": "수술 중"}]},
    {"name": "정순환", "department": "순환기내과", "position": "교수", "specialty": "관상동맥, 심부전", "hospital_code": "SMC", "external_id": "SMC-001", "visit_grade": "B",
     "schedules": [{"day_of_week": 1, "time_slot": "morning"}, {"day_of_week": 4, "time_slot": "morning"}],
     "visits": [{"days_ago": 5, "status": "성공", "product": "심부전신약C", "notes": "처방 전환 검토 중"}]},
    {"name": "한소화", "department": "소화기내과", "position": "부교수", "specialty": "위장관, 내시경", "hospital_code": "SEVERANCE", "external_id": "SEV-001", "visit_grade": "C",
     "schedules": [{"day_of_week": 2, "time_slot": "morning"}, {"day_of_week": 4, "time_slot": "afternoon"}],
     "visits": []},
    {"name": "윤호흡", "department": "호흡기내과", "position": "교수", "specialty": "폐암, COPD", "hospital_code": "CMCSEOUL", "external_id": "CMC-001", "visit_grade": "B",
     "schedules": [{"day_of_week": 1, "time_slot": "afternoon"}, {"day_of_week": 3, "time_slot": "morning"}],
     "visits": [{"days_ago": 15, "status": "성공", "product": "흡입제D", "notes": "COPD 환자에 적용 예정"}]},
]


async def seed_database(db: AsyncSession):
    """DB에 초기 데이터가 없으면 시드 데이터를 삽입합니다."""
    result = await db.execute(select(Hospital))
    if result.scalars().first():
        logger.info("시드 데이터 이미 존재 — 건너뜀")
        return

    logger.info("시드 데이터 삽입 시작…")

    # 병원 생성
    hospital_map = {}
    for h_data in SEED_HOSPITALS:
        hospital = Hospital(**h_data)
        db.add(hospital)
        await db.flush()
        hospital_map[h_data["code"]] = hospital.id

    # 교수 + 일정 + 방문기록 생성
    for d_data in SEED_DOCTORS:
        h_code = d_data.pop("hospital_code")
        schedules_data = d_data.pop("schedules", [])
        visits_data = d_data.pop("visits", [])

        doctor = Doctor(hospital_id=hospital_map[h_code], **d_data)
        db.add(doctor)
        await db.flush()

        for s in schedules_data:
            time_ranges = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}
            start, end = time_ranges.get(s["time_slot"], ("", ""))
            schedule = DoctorSchedule(
                doctor_id=doctor.id,
                day_of_week=s["day_of_week"],
                time_slot=s["time_slot"],
                start_time=start,
                end_time=end,
            )
            db.add(schedule)

        for v in visits_data:
            visit = VisitLog(
                doctor_id=doctor.id,
                visit_date=datetime.utcnow() - timedelta(days=v["days_ago"]),
                status=v["status"],
                product=v.get("product"),
                notes=v.get("notes"),
                next_action=v.get("next_action"),
            )
            db.add(visit)

    await db.commit()
    logger.info(f"시드 데이터 삽입 완료: {len(SEED_HOSPITALS)}개 병원, {len(SEED_DOCTORS)}명 교수")
