"""메트로병원(METRO) 크롤러

홈페이지: http://www.metrohospital.co.kr (안양 메트로병원, Happy CMS)

※ 메트로병원은 의료진 페이지(sub.php?menu_number=382)와 진료시간표를
  모두 단일 JPG 이미지로만 제공한다 (예: upload/file_attach/2025/10/28/1761616678_78326.jpg).
  HTML 내 구조화된 의사/스케줄 데이터가 존재하지 않아 httpx + BeautifulSoup 로는
  파싱이 불가능하다.

현재 구현은 빈 리스트를 반환하는 skeleton 이며, 추후 이미지 OCR 또는 병원 측
데이터 공개 시 실제 파싱 로직으로 교체해야 한다.
"""
from __future__ import annotations

import logging
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "http://www.metrohospital.co.kr"

NOTE_TEXT = (
    "※ 메트로병원은 홈페이지에 의료진 및 진료시간표를 텍스트가 아닌 이미지로만 제공합니다. "
    "의료진 정보와 요일별 진료 가능 시간은 메트로병원 홈페이지 또는 대표번호를 통해 확인해 주세요."
)


class MetroCrawler:
    def __init__(self):
        self.hospital_code = "METRO"
        self.hospital_name = "메트로병원"

    async def get_departments(self) -> list[dict]:
        return []

    async def crawl_doctor_list(self, department: str = None) -> list[dict]:
        return []

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        return {
            "staff_id": staff_id,
            "name": "",
            "department": "",
            "position": "",
            "specialty": "",
            "profile_url": "",
            "notes": NOTE_TEXT,
            "schedules": [],
            "date_schedules": [],
        }

    async def crawl_doctors(self, department: str = None):
        from app.schemas.schemas import CrawlResult

        logger.info(f"[METRO] 이미지 기반 페이지 — 구조화된 의사 데이터 없음")
        return CrawlResult(
            hospital_code=self.hospital_code,
            hospital_name=self.hospital_name,
            status="partial",
            doctors=[],
            crawled_at=datetime.utcnow(),
        )
