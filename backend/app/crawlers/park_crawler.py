"""PMC박병원(PARK) 평택 크롤러

전체 진료스케줄을 `/information/schedule.asp` 단일 페이지에 테이블로 공개하고 있어
해당 페이지 한 번의 GET 으로 모든 의사와 주간 스케줄을 얻는다.

테이블 구조:
  진료과 | 의료진 | 20(월)오전 | 20(월)오후 | 21(화)오전 | 21(화)오후 | ... | 25(토)오전 | 25(토)오후
  셀: ○(진료) / ★(수술) / - (휴진)

external_id: `PARK-{md5(dept + name)[:10]}` — 병원 원내 고유 ID 가 없어 이름/진료과 해시 사용.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from app.schemas.schemas import CrawlResult, CrawledDoctor

logger = logging.getLogger(__name__)

BASE_URL = "https://www.parkmedical.co.kr"
SCHEDULE_URL = f"{BASE_URL}/information/schedule.asp"
TIME_RANGES = {"morning": ("09:00", "12:30"), "afternoon": ("13:30", "17:30")}


class ParkCrawler:
    """PMC박병원(PARK) 평택 크롤러."""

    def __init__(self):
        self.hospital_code = "PARK"
        self.hospital_name = "PMC박병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        }
        self._cached_data: list[dict] | None = None

    @staticmethod
    def _hash_id(dept: str, name: str) -> str:
        return hashlib.md5(f"{dept}|{name}".encode("utf-8")).hexdigest()[:10]

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with httpx.AsyncClient(headers=self.headers, timeout=30, follow_redirects=True, verify=False) as client:
            try:
                resp = await client.get(SCHEDULE_URL)
                resp.raise_for_status()
            except Exception as e:
                logger.error(f"[PARK] 스케줄 페이지 조회 실패: {e}")
                self._cached_data = []
                return []

        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.select_one("table")
        if not table:
            logger.warning("[PARK] 스케줄 테이블이 없음")
            self._cached_data = []
            return []

        rows = table.find_all("tr")
        doctors: dict[str, dict] = {}
        for row in rows:
            cells = row.find_all("td")
            if len(cells) != 14:
                continue
            dept = cells[0].get_text(strip=True)
            name = cells[1].get_text(strip=True)
            if not name or not dept:
                continue
            slot_cells = cells[2:]
            schedules: list[dict] = []
            for i, cell in enumerate(slot_cells[:12]):
                day_idx = i // 2
                is_morning = (i % 2 == 0)
                mark = cell.get_text(strip=True)
                if mark and mark not in ("-", "", "ⅹ", "X"):
                    # ★ 는 수술 — 외래 아님, 제외
                    if mark == "★":
                        continue
                    slot = "morning" if is_morning else "afternoon"
                    start, end = TIME_RANGES[slot]
                    schedules.append({
                        "day_of_week": day_idx,
                        "time_slot": slot,
                        "start_time": start,
                        "end_time": end,
                        "location": "",
                    })

            ext_id = f"PARK-{self._hash_id(dept, name)}"
            doctors[ext_id] = {
                "staff_id": ext_id,
                "external_id": ext_id,
                "name": name,
                "department": dept,
                "position": "",
                "specialty": "",
                "profile_url": SCHEDULE_URL,
                "notes": "",
                "schedules": schedules,
                "date_schedules": [],
            }

        result = list(doctors.values())
        self._cached_data = result
        logger.info(f"[PARK] 크롤링 완료: {len(result)}명")
        return result

    async def get_departments(self) -> list[dict]:
        data = await self._fetch_all()
        seen: set[str] = set()
        depts = []
        for d in data:
            if d["department"] not in seen:
                seen.add(d["department"])
                depts.append({"code": d["department"], "name": d["department"]})
        return depts

    async def crawl_doctor_list(self, department: str | None = None) -> list[dict]:
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]
        return [
            {k: v for k, v in d.items() if k not in ("schedules", "date_schedules")}
            for d in data
        ]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """단일 페이지 기반이라 전체 데이터에서 검색. 1회 GET 만 수행되므로 규칙 #7 준수."""
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "",
            "schedules": [], "date_schedules": [],
        }
        data = await self._fetch_all()
        for d in data:
            if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                return d
        return empty

    async def crawl_doctors(self, department: str | None = None) -> CrawlResult:
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]

        doctors = [
            CrawledDoctor(
                name=d["name"],
                department=d["department"],
                position=d.get("position", ""),
                specialty=d.get("specialty", ""),
                profile_url=d.get("profile_url", ""),
                external_id=d["external_id"],
                notes=d.get("notes", ""),
                schedules=d["schedules"],
                date_schedules=d.get("date_schedules", []),
            )
            for d in data
        ]

        return CrawlResult(
            hospital_code=self.hospital_code,
            hospital_name=self.hospital_name,
            status="success" if doctors else "partial",
            doctors=doctors,
            crawled_at=datetime.utcnow(),
        )
