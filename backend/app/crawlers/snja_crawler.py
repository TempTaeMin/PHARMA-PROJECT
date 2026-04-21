"""성남중앙병원(SNJA) 크롤러 — 스텁

병원 공식명: 성남중앙병원 (경기 성남시 수정구)
홈페이지: snja.co.kr

현 상태: 홈페이지의 의료진 소개 페이지(/sub/sub04_member.php 및 모바일
/m/page/p0201_members.php)에서 모든 진료과가 "등록된 의료진이 없습니다" 를 반환한다.
개별 의사 프로필과 주간 진료시간표가 온라인에 공개되지 않은 상태.

→ 본 크롤러는 의료진 0명을 반환하는 스텁이다. 병원이 의료진을 등록하면 실제 파싱
  로직을 추가한다. factory/DB 에는 등록해서 병원 목록에는 노출되도록 한다.
"""
from __future__ import annotations

import logging
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://www.snja.co.kr"
NOTES = (
    "※ 성남중앙병원 홈페이지에는 개별 의료진/주간 진료시간표가 공개되어 있지 않습니다. "
    "외래 진료 가능 시간은 병원에 직접 문의해 주세요."
)


class SnjaCrawler:
    def __init__(self):
        self.hospital_code = "SNJA"
        self.hospital_name = "성남중앙병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120",
        }
        self._cached_data: list[dict] = []

    async def get_departments(self) -> list[dict]:
        return []

    async def crawl_doctor_list(self, department: str = None) -> list[dict]:
        return []

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        return {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": BASE_URL, "notes": NOTES,
            "schedules": [], "date_schedules": [],
        }

    async def crawl_doctors(self, department: str = None):
        from app.schemas.schemas import CrawlResult

        logger.info(f"[SNJA] 홈페이지에 의료진 미공개 — 0명 반환")
        return CrawlResult(
            hospital_code=self.hospital_code,
            hospital_name=self.hospital_name,
            status="partial",
            doctors=[],
            crawled_at=datetime.utcnow(),
        )
