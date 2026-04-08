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
    {"name": "은평성모병원", "code": "CMCEP", "address": "서울 은평구 통일로 1021", "phone": "1811-7755", "website": "https://www.cmcep.or.kr", "crawler_type": "cmcep"},
    {"name": "여의도성모병원", "code": "CMCYD", "address": "서울 영등포구 63로 10", "phone": "1661-7575", "website": "https://www.cmcsungmo.or.kr", "crawler_type": "cmcyd"},
    {"name": "강남세브란스병원", "code": "GANSEV", "address": "서울 강남구 언주로 211", "phone": "1599-6114", "website": "https://gs.severance.healthcare", "crawler_type": "gangnam_severance"},
    {"name": "이대목동병원", "code": "EUMCMK", "address": "서울 양천구 안양천로 1071", "phone": "1666-5000", "website": "https://mokdong.eumc.ac.kr", "crawler_type": "eumc_mokdong"},
    {"name": "이대서울병원", "code": "EUMCSL", "address": "서울 강서구 공항대로 260", "phone": "1555-2500", "website": "https://seoul.eumc.ac.kr", "crawler_type": "eumc_seoul"},
    {"name": "고대안암병원", "code": "KUANAM", "address": "서울 성북구 인촌로 73", "phone": "1577-0083", "website": "https://anam.kumc.or.kr", "crawler_type": "kumc_anam"},
    {"name": "고대구로병원", "code": "KUGURO", "address": "서울 구로구 구로동로 148", "phone": "1577-0083", "website": "https://guro.kumc.or.kr", "crawler_type": "kumc_guro"},
    {"name": "고대안산병원", "code": "KUANSAN", "address": "경기 안산시 단원구 적금로 123", "phone": "1577-0083", "website": "https://ansan.kumc.or.kr", "crawler_type": "kumc_ansan"},
    {"name": "한국원자력의학원", "code": "KCCH", "address": "서울 노원구 노원로 75", "phone": "02-970-1234", "website": "https://www.kcch.re.kr", "crawler_type": "kcch"},
    {"name": "국립암센터", "code": "NCC", "address": "경기 고양시 일산동구 일산로 323", "phone": "1588-8110", "website": "https://www.ncc.re.kr", "crawler_type": "ncc"},
    {"name": "건국대학교병원", "code": "KUH", "address": "서울 광진구 능동로 120-1", "phone": "1588-1533", "website": "https://www.kuh.ac.kr", "crawler_type": "kuh"},
    {"name": "한양대병원", "code": "HYUMC", "address": "서울 성동구 왕십리로 222-1", "phone": "1577-2299", "website": "https://seoul.hyumc.com", "crawler_type": "hyumc"},
    {"name": "동국대학교일산병원", "code": "DUIH", "address": "경기 고양시 일산동구 동국로 27", "phone": "031-961-7114", "website": "http://www.dumc.or.kr", "crawler_type": "duih"},
    {"name": "분당서울대병원", "code": "SNUBH", "address": "경기 성남시 분당구 구미로 173번길 82", "phone": "1588-3369", "website": "https://www.snubh.org", "crawler_type": "snubh"},
    {"name": "경희대병원", "code": "KHU", "address": "서울 동대문구 경희대로 23", "phone": "02-958-8114", "website": "https://www.khuh.or.kr", "crawler_type": "khu"},
    {"name": "강북삼성병원", "code": "KBSMC", "address": "서울 종로구 새문안로 29", "phone": "1599-8114", "website": "https://www.kbsmc.co.kr", "crawler_type": "kbsmc"},
    {"name": "중앙대병원", "code": "CAU", "address": "서울 동작구 흑석로 102", "phone": "1800-1114", "website": "https://ch.cauhs.or.kr", "crawler_type": "cau"},
    {"name": "성빈센트병원", "code": "CMCSV", "address": "경기 수원시 팔달구 중부대로 93", "phone": "031-249-7114", "website": "https://www.cmcvincent.or.kr", "crawler_type": "cmcsv"},
    {"name": "부천순천향병원", "code": "SCHBC", "address": "경기 부천시 조마루로 170", "phone": "032-621-5114", "website": "https://www.schmc.ac.kr/bucheon", "crawler_type": "schbc"},
    {"name": "아주대병원", "code": "AJOUMC", "address": "경기 수원시 영통구 월드컵로 164", "phone": "1688-6114", "website": "https://www.ajoumc.or.kr", "crawler_type": "ajoumc"},
    {"name": "한림성심병원", "code": "HALLYM", "address": "경기 안양시 동안구 관평로 170번길 22", "phone": "031-380-3114", "website": "https://hallym.or.kr/sacred_heart", "crawler_type": "hallym"},
    {"name": "길병원", "code": "GIL", "address": "인천 남동구 남동대로 774번길 21", "phone": "1577-2299", "website": "https://www.gilhospital.com", "crawler_type": "gil"},
    {"name": "인천성모병원", "code": "CMCIC", "address": "인천 부평구 동수로 56", "phone": "1544-9004", "website": "https://www.cmcincheon.or.kr", "crawler_type": "cmcic"},
    {"name": "인하대병원", "code": "INHA", "address": "인천 중구 인항로 27", "phone": "032-890-2114", "website": "https://www.inha.com", "crawler_type": "inha"},
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
    existing = result.scalars().all()
    existing_codes = {h.code for h in existing}

    # 누락된 병원 추가
    missing = [h for h in SEED_HOSPITALS if h["code"] not in existing_codes]
    if missing:
        logger.info(f"누락된 병원 {len(missing)}개 추가: {[h['code'] for h in missing]}")
        hospital_map = {}
        for h_data in missing:
            hospital = Hospital(**h_data)
            db.add(hospital)
            await db.flush()
            hospital_map[h_data["code"]] = hospital.id
        await db.commit()
        logger.info(f"병원 추가 완료: {len(missing)}개")

    if existing:
        # 이미 시드 데이터가 있으면 교수 데이터는 건너뜀
        if not missing:
            logger.info("시드 데이터 이미 존재 — 건너뜀")
        return

    logger.info("시드 데이터 삽입 시작…")

    # 병원 ID 맵 구성
    result = await db.execute(select(Hospital))
    all_hospitals = result.scalars().all()
    hospital_map = {h.code: h.id for h in all_hospitals}

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
