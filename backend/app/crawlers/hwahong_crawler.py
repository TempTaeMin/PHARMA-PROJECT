"""화홍병원(HWAHONG) 수원 크롤러

정적 HTML. `/page/medical/doctor/` 페이지 한 장에 모든 의사 카드가 렌더되고,
각 카드의 `<a href="/page/medical/doctor/doctor_view.php?d_idx=N">의료진 소개</a>` 가 상세 URL.

상세 페이지에 주간 스케줄 테이블이 있다. 진료 셀은 `<p class="default">...</p>` 에
레이블(초진/재진/시술 등) 이 들어가고, 휴진 셀은 `<p class=""></p>` (빈 class).
전체 셀이 "-" 또는 "별도의 진료 스케줄이 없습니다." 알림이 있으면 스케줄 없음.

external_id: `HWAHONG-{d_idx}`
"""
from __future__ import annotations

import re
import logging
import asyncio
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from app.crawlers._schedule_rules import find_exclude_keyword
from app.schemas.schemas import CrawlResult, CrawledDoctor

logger = logging.getLogger(__name__)

BASE_URL = "https://www.hwahonghospital.com"
LIST_URL = f"{BASE_URL}/page/medical/doctor/"
DETAIL_URL = f"{BASE_URL}/page/medical/doctor/doctor_view.php"

TIME_RANGES = {"morning": ("08:40", "12:30"), "afternoon": ("13:30", "17:30")}
NO_SCHEDULE_MARKER = "해당 진료과는 별도의 진료 스케줄이 없습니다"


class HwahongCrawler:
    def __init__(self):
        self.hospital_code = "HWAHONG"
        self.hospital_name = "화홍병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        }
        self._cached_data: list[dict] | None = None

    async def _fetch_doctor_list(self, client: httpx.AsyncClient) -> list[dict]:
        resp = await client.get(LIST_URL)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        doctors = []
        seen: set[str] = set()
        for a in soup.select('a.btn-doctor-view[href*="d_idx="]'):
            href = a.get("href", "")
            m = re.search(r"d_idx=(\d+)", href)
            if not m:
                continue
            d_idx = m.group(1)
            if d_idx in seen:
                continue
            seen.add(d_idx)
            doctors.append({
                "d_idx": d_idx,
                "external_id": f"HWAHONG-{d_idx}",
                "profile_url": f"{DETAIL_URL}?d_idx={d_idx}",
            })
        return doctors

    async def _fetch_doctor_detail(self, client: httpx.AsyncClient, d_idx: str) -> dict:
        url = f"{DETAIL_URL}?d_idx={d_idx}"
        info: dict = {
            "name": "", "department": "", "position": "", "specialty": "",
            "schedules": [], "notes": "",
        }
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[HWAHONG] detail 실패 d_idx={d_idx}: {e}")
            return info

        soup = BeautifulSoup(resp.text, "html.parser")
        name_wrap = soup.select_one("div.name-wrap")
        if name_wrap:
            dept_el = name_wrap.select_one("p.dp")
            name_el = name_wrap.select_one("p.name")
            if dept_el:
                info["department"] = dept_el.get_text(strip=True)
            if name_el:
                # name has trailing <span>position</span>
                pos_span = name_el.find("span")
                if pos_span:
                    info["position"] = pos_span.get_text(strip=True)
                    pos_span.extract()
                info["name"] = name_el.get_text(strip=True)

        field_sec = soup.select_one("section.field p.cont")
        if field_sec:
            info["specialty"] = field_sec.get_text("\n", strip=True)

        schedule_sec = soup.select_one("section.schedule")
        if not schedule_sec:
            return info

        page_text = schedule_sec.get_text(" ", strip=True)
        if NO_SCHEDULE_MARKER in page_text:
            return info

        table = schedule_sec.select_one("table")
        if not table:
            return info

        rows = table.select("tbody tr")
        if len(rows) < 2:
            return info

        for row_idx, row in enumerate(rows[:2]):  # 0: 오전, 1: 오후
            slot = "morning" if row_idx == 0 else "afternoon"
            start, end = TIME_RANGES[slot]
            tds = row.find_all("td")
            # 월화수목금토 = 6개 td
            for day_idx, td in enumerate(tds[:6]):
                p = td.find("p")
                if not p:
                    continue
                cls = p.get("class") or []
                text = p.get_text(strip=True)
                is_default = "default" in cls
                if is_default and text and text != "-":
                    if find_exclude_keyword(text):
                        continue
                    info["schedules"].append({
                        "day_of_week": day_idx,
                        "time_slot": slot,
                        "start_time": start,
                        "end_time": end,
                        "location": text,
                    })

        return info

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with httpx.AsyncClient(headers=self.headers, timeout=30, follow_redirects=True, verify=False) as client:
            try:
                doctors = await self._fetch_doctor_list(client)
            except Exception as e:
                logger.error(f"[HWAHONG] 목록 실패: {e}")
                self._cached_data = []
                return []

            sem = asyncio.Semaphore(6)

            async def enrich(d: dict):
                async with sem:
                    info = await self._fetch_doctor_detail(client, d["d_idx"])
                    d.update(info)
                    d["staff_id"] = d["external_id"]
                    d["date_schedules"] = []

            await asyncio.gather(*(enrich(d) for d in doctors), return_exceptions=True)

        self._cached_data = doctors
        logger.info(f"[HWAHONG] 크롤링 완료: {len(doctors)}명")
        return doctors

    async def get_departments(self) -> list[dict]:
        data = await self._fetch_all()
        seen, depts = set(), []
        for d in data:
            key = d.get("department") or ""
            if key and key not in seen:
                seen.add(key)
                depts.append({"code": key, "name": key})
        return depts

    async def crawl_doctor_list(self, department: str | None = None) -> list[dict]:
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d.get("department") == department]
        return [
            {k: v for k, v in d.items() if k not in ("schedules", "date_schedules")}
            for d in data
        ]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 조회 — 해당 의사 상세 페이지 1회 GET."""
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "",
            "schedules": [], "date_schedules": [],
        }
        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return d
            return empty

        prefix = f"{self.hospital_code}-"
        d_idx = staff_id.replace(prefix, "") if staff_id.startswith(prefix) else staff_id

        async with httpx.AsyncClient(headers=self.headers, timeout=30, follow_redirects=True, verify=False) as client:
            info = await self._fetch_doctor_detail(client, d_idx)

        return {
            "staff_id": staff_id,
            "external_id": staff_id,
            "name": info["name"],
            "department": info["department"],
            "position": info["position"],
            "specialty": info["specialty"],
            "profile_url": f"{DETAIL_URL}?d_idx={d_idx}",
            "notes": info["notes"],
            "schedules": info["schedules"],
            "date_schedules": [],
        }

    async def crawl_doctors(self, department: str | None = None) -> CrawlResult:
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d.get("department") == department]

        doctors = [
            CrawledDoctor(
                name=d.get("name", ""),
                department=d.get("department", ""),
                position=d.get("position", ""),
                specialty=d.get("specialty", ""),
                profile_url=d.get("profile_url", ""),
                external_id=d["external_id"],
                notes=d.get("notes", ""),
                schedules=d.get("schedules", []),
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
