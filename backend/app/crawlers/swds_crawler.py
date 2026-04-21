"""수원덕산병원(SWDS) 크롤러

Nanum CMS 기반. 의료진 검색 페이지 `/main/site/doctor/search.do` 가 전체 의료진을
한 페이지에 렌더링하고, 각 의사의 주간 스케줄은 AJAX API
`POST /main/doctor_schedule/ajax_schedule.do` (form: part_idx, doctor_idx, sdate, edate)
가 JSON 배열(`[{yoil:'mon', am:'Y', pm:''}, ...]`) 로 반환한다.

external_id: `SWDS-{md_idx}` — Nanum 고유 의사 ID. doctor_code 는 비어있을 수 있어 md_idx 를 우선 사용.
"""
from __future__ import annotations

import re
import logging
import asyncio
from datetime import datetime, timedelta

import httpx
from bs4 import BeautifulSoup

from app.schemas.schemas import CrawlResult, CrawledDoctor

logger = logging.getLogger(__name__)

BASE_URL = "https://swdeoksanmc.com"
SEARCH_URL = f"{BASE_URL}/main/site/doctor/search.do"
DETAIL_URL = f"{BASE_URL}/main/doctor/view.do"
SCHEDULE_API = f"{BASE_URL}/main/doctor_schedule/ajax_schedule.do"

TIME_RANGES = {"morning": ("09:00", "12:30"), "afternoon": ("13:30", "17:30")}
YOIL_MAP = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


class SwdsCrawler:
    def __init__(self):
        self.hospital_code = "SWDS"
        self.hospital_name = "수원덕산병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        }
        self._cached_data: list[dict] | None = None

    async def _fetch_doctor_list(self, client: httpx.AsyncClient) -> list[dict]:
        resp = await client.get(SEARCH_URL)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        doctors: list[dict] = []
        seen_ids: set[str] = set()
        for box in soup.select("div.dlist_serch"):
            intro_link = box.select_one('a[href*="/main/doctor/view.do"]')
            if not intro_link:
                continue
            href = intro_link.get("href", "")
            m = re.search(r"md_idx=(\d+)", href)
            if not m:
                continue
            md_idx = m.group(1)
            if md_idx in seen_ids:
                continue
            seen_ids.add(md_idx)
            pm = re.search(r"mp_idx=(\d+)", href)
            part_code_m = re.search(r"part_code=([^&]*)", href)
            doctor_code_m = re.search(r"doctor_code=([^&]*)", href)
            mp_idx = pm.group(1) if pm else ""
            part_code = part_code_m.group(1) if part_code_m else ""
            doctor_code = doctor_code_m.group(1) if doctor_code_m else ""

            name_el = box.select_one("p.name")
            dept_el = box.select_one("span.part")
            name = name_el.get_text(strip=True) if name_el else ""
            dept = dept_el.get_text(strip=True) if dept_el else ""

            # specialty = ul.section 내 2번째 li
            specialty = ""
            section_lis = box.select("ul.section li")
            if len(section_lis) >= 2:
                specialty = section_lis[1].get_text(strip=True)

            if not name:
                continue

            doctors.append({
                "md_idx": md_idx,
                "mp_idx": mp_idx,
                "part_code": part_code,
                "doctor_code": doctor_code,
                "name": name,
                "department": dept,
                "position": "",
                "specialty": specialty,
                "external_id": f"SWDS-{md_idx}",
                "profile_url": f"{DETAIL_URL}?md_idx={md_idx}&doctor_code={doctor_code}&mp_idx={mp_idx}&part_code={part_code}",
            })

        return doctors

    async def _fetch_doctor_detail(self, client: httpx.AsyncClient, doc: dict) -> None:
        url = f"{DETAIL_URL}?md_idx={doc['md_idx']}&doctor_code={doc['doctor_code']}&mp_idx={doc['mp_idx']}&part_code={doc['part_code']}"
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[SWDS] detail 실패 md_idx={doc['md_idx']}: {e}")
            return

        soup = BeautifulSoup(resp.text, "html.parser")
        if not doc.get("name"):
            name_el = soup.select_one("h3, h4.name, .name")
            if name_el:
                doc["name"] = name_el.get_text(strip=True)
        if not doc.get("department"):
            dept_el = soup.select_one(".dept, .part")
            if dept_el:
                doc["department"] = dept_el.get_text(strip=True)
        clinic = soup.select_one("p.clinic")
        if clinic:
            txt = clinic.get_text(" ", strip=True)
            doc["specialty"] = txt.replace("전문진료분야", "").strip()

    async def _fetch_schedule(self, client: httpx.AsyncClient, doc: dict) -> list[dict]:
        part_idx = doc.get("mp_idx", "")
        doctor_idx = doc.get("md_idx", "")
        if not part_idx or not doctor_idx:
            return []
        today = datetime.now()
        # 월요일 찾기
        sdate = today - timedelta(days=today.weekday())
        edate = sdate + timedelta(days=5)
        try:
            resp = await client.post(
                SCHEDULE_API,
                data={
                    "part_idx": part_idx,
                    "doctor_idx": doctor_idx,
                    "sdate": sdate.strftime("%Y-%m-%d"),
                    "edate": edate.strftime("%Y-%m-%d"),
                },
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(f"[SWDS] schedule API 실패 md_idx={doctor_idx}: {e}")
            return []

        schedules = []
        if not isinstance(data, list):
            return []
        for item in data:
            yoil = item.get("yoil", "")
            day_idx = YOIL_MAP.get(yoil)
            if day_idx is None:
                continue
            if item.get("am") == "Y":
                s, e = TIME_RANGES["morning"]
                schedules.append({"day_of_week": day_idx, "time_slot": "morning",
                                  "start_time": s, "end_time": e, "location": ""})
            if item.get("pm") == "Y":
                s, e = TIME_RANGES["afternoon"]
                schedules.append({"day_of_week": day_idx, "time_slot": "afternoon",
                                  "start_time": s, "end_time": e, "location": ""})
        return schedules

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with httpx.AsyncClient(headers=self.headers, timeout=30, follow_redirects=True, verify=False) as client:
            try:
                doctors = await self._fetch_doctor_list(client)
            except Exception as e:
                logger.error(f"[SWDS] 목록 실패: {e}")
                self._cached_data = []
                return []

            sem = asyncio.Semaphore(6)

            async def enrich(d: dict):
                async with sem:
                    d["schedules"] = await self._fetch_schedule(client, d)
                    d["date_schedules"] = []
                    d["staff_id"] = d["external_id"]
                    d["notes"] = ""

            await asyncio.gather(*(enrich(d) for d in doctors), return_exceptions=True)

        self._cached_data = doctors
        logger.info(f"[SWDS] 크롤링 완료: {len(doctors)}명")
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
        """개별 교수 조회 — 해당 교수 1명만 네트워크 요청 (rule #7)."""
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

        # external_id 에서 md_idx 파싱
        prefix = f"{self.hospital_code}-"
        md_idx = staff_id.replace(prefix, "") if staff_id.startswith(prefix) else staff_id

        async with httpx.AsyncClient(headers=self.headers, timeout=30, follow_redirects=True, verify=False) as client:
            # 목록 페이지에서 해당 md_idx 의 mp_idx/part_code 를 찾는다 (목록 GET 1회)
            try:
                doctors = await self._fetch_doctor_list(client)
            except Exception as e:
                logger.error(f"[SWDS] 개별 조회 목록 실패 {staff_id}: {e}")
                return empty

            target = next((d for d in doctors if d["md_idx"] == md_idx), None)
            if not target:
                return empty

            target["staff_id"] = target["external_id"]
            target["notes"] = ""
            try:
                await self._fetch_doctor_detail(client, target)
                target["schedules"] = await self._fetch_schedule(client, target)
                target["date_schedules"] = []
            except Exception as e:
                logger.error(f"[SWDS] 개별 조회 상세 실패 {staff_id}: {e}")
                return empty

        return target

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
