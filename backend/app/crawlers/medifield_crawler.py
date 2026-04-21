"""메디필드한강병원(MEDIFIELD) 크롤러 — 스텁

병원 공식명: 메디필드한강병원 (경기 용인시 처인구 김량장동, 2026년 3월 개원)
홈페이지: hanganghospital.com

현 상태: 홈페이지의 진료과 상세 페이지(/sub/department/medical_detail.php?dp_idx=N)에
개별 의료진 정보가 아직 게시되어 있지 않음. 진료과 설명과 일반 진료시간표("월~금 오전/오후,
토 오전")만 안내됨. 2026년 4월 현재 공식 의료진 목록이 온라인에 미공개 상태.

→ 본 크롤러는 의료진 0명을 반환하는 스텁이다. 병원이 의료진 소개를 정식으로 공개하면
  실제 파싱 로직을 추가한다. factory/DB 에는 등록해서 병원 목록에는 노출되도록 한다.
"""
from __future__ import annotations

import logging
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://hanganghospital.com"
NOTES = (
    "※ 메디필드한강병원은 2026년 3월 개원한 신규 병원으로, 홈페이지에 개별 의료진/진료시간표가 "
    "아직 공개되어 있지 않습니다. 외래 진료 가능 시간은 병원에 직접 문의해 주세요."
)

PLACEHOLDER_ID = "MEDIFIELD-notice"
PLACEHOLDER = {
    "staff_id": PLACEHOLDER_ID,
    "external_id": PLACEHOLDER_ID,
    "name": "의료진 정보 미공개",
    "department": "안내",
    "position": "",
    "specialty": "",
    "profile_url": BASE_URL,
    "notes": NOTES,
    "schedules": [],
    "date_schedules": [],
}


class MedifieldCrawler:
    def __init__(self):
        self.hospital_code = "MEDIFIELD"
        self.hospital_name = "메디필드한강병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120",
        }

    async def get_departments(self) -> list[dict]:
        return [{"code": "안내", "name": "안내"}]

    async def crawl_doctor_list(self, department: str = None) -> list[dict]:
        return [{k: PLACEHOLDER[k] for k in ("staff_id", "external_id", "name", "department",
                                              "position", "specialty", "profile_url", "notes")}]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        if staff_id == PLACEHOLDER_ID:
            return {k: PLACEHOLDER[k] for k in ("staff_id", "name", "department", "position",
                                                 "specialty", "profile_url", "notes",
                                                 "schedules", "date_schedules")}
        return {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": BASE_URL, "notes": NOTES,
            "schedules": [], "date_schedules": [],
        }

    async def crawl_doctors(self, department: str = None):
        from app.schemas.schemas import CrawlResult, CrawledDoctor

        logger.info(f"[MEDIFIELD] 홈페이지에 의료진 미공개 — 안내 placeholder 1건 반환")
        return CrawlResult(
            hospital_code=self.hospital_code,
            hospital_name=self.hospital_name,
            status="partial",
            doctors=[CrawledDoctor(
                name=PLACEHOLDER["name"],
                department=PLACEHOLDER["department"],
                position=PLACEHOLDER["position"],
                specialty=PLACEHOLDER["specialty"],
                profile_url=PLACEHOLDER["profile_url"],
                external_id=PLACEHOLDER["external_id"],
                notes=PLACEHOLDER["notes"],
                schedules=[],
                date_schedules=[],
            )],
            crawled_at=datetime.utcnow(),
        )
