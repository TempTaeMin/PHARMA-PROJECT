"""평택성모병원(PTSM) 크롤러

gnuboard 기반 Gn글로벌 쇼핑몰 CMS. 진료과 목록은 `/main.php` 사이드 메뉴에서 추출
(하드코딩 폴백 있음). 진료과별 의사 목록: `/product/list.php?ca_id={CODE}`.
의사 상세: `/product/item_new.php?it_id={ID}&ca_id={CODE}`.
진료과별 주간 스케줄표: `/product/schedule.php?ca_id={CODE}` (표 한 장에 해당
진료과 전체 의사의 주간 스케줄 포함).

external_id: `PTSM-{it_id}`
"""
from __future__ import annotations

import re
import logging
import asyncio
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from app.schemas.schemas import CrawlResult, CrawledDoctor

logger = logging.getLogger(__name__)

BASE_URL = "https://www.ptsm.co.kr"
MAIN_URL = f"{BASE_URL}/main.php"
LIST_URL = f"{BASE_URL}/product/list.php"
DETAIL_URL = f"{BASE_URL}/product/item_new.php"
SCHEDULE_URL = f"{BASE_URL}/product/schedule.php"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}
ACTIVE_CELL_TEXTS = {"진료", "검사", "수술", "외진", "수술일", "검진"}


class PtsmCrawler:
    def __init__(self):
        self.hospital_code = "PTSM"
        self.hospital_name = "평택성모병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        }
        self._cached_data: list[dict] | None = None

    async def _fetch_departments(self, client: httpx.AsyncClient) -> list[tuple[str, str]]:
        """main.php 상단 메뉴에서 진료과 (ca_id, 이름) 추출."""
        try:
            resp = await client.get(MAIN_URL)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[PTSM] main 조회 실패: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        depts: list[tuple[str, str]] = []
        seen: set[str] = set()

        # 최상위 진료과 <li><a href="/product/list.php?ca_id=XX">진료과명</a>
        for a in soup.select('a[href*="/product/list.php?ca_id="]'):
            href = a.get("href", "")
            m = re.search(r"ca_id=([^&\s]+)", href)
            if not m:
                continue
            ca_id = m.group(1)
            name = a.get_text(strip=True)
            if not name or ca_id in seen:
                continue
            # "의료진" 링크는 제외 (같은 URL 의 내부 링크)
            if name in ("의료진", "진료시간", "진료안내"):
                continue
            seen.add(ca_id)
            depts.append((ca_id, name))

        return depts

    async def _fetch_dept_doctors(self, client: httpx.AsyncClient, ca_id: str, dept_name: str) -> list[dict]:
        url = f"{LIST_URL}?ca_id={ca_id}"
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[PTSM] list {ca_id} 실패: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        doctors = []
        seen_ids: set[str] = set()
        current_sub_dept = dept_name  # 섹션별 h5.tit01 내 하위 진료과명

        for el in soup.select_one("div.sub0201_list_wrap, body").descendants if soup.select_one("div.sub0201_list_wrap") else []:
            if getattr(el, "name", None) == "h5" and "tit01" in (el.get("class") or []):
                current_sub_dept = el.get_text(strip=True) or dept_name
            elif getattr(el, "name", None) == "li":
                a = el.find("a", href=re.compile(r"item_new\.php\?it_id="))
                if not a:
                    continue
                m = re.search(r"it_id=(\w+)", a.get("href", ""))
                if not m:
                    continue
                it_id = m.group(1)
                if it_id in seen_ids:
                    continue
                seen_ids.add(it_id)

                name_el = el.find("em")
                p_el = el.find("p")
                raw_name = name_el.get_text(strip=True) if name_el else ""
                specialty = p_el.get_text("\n", strip=True) if p_el else ""
                if not raw_name:
                    continue
                # em 내부에 "이름 직책" 이 함께 들어있으면 첫 공백으로 분리
                parts = raw_name.split(None, 1)
                name = parts[0]
                position = parts[1] if len(parts) > 1 else ""

                doctors.append({
                    "it_id": it_id,
                    "ca_id": ca_id,
                    "name": name,
                    "department": current_sub_dept,
                    "position": position,
                    "specialty": specialty,
                    "external_id": f"PTSM-{it_id}",
                    "profile_url": f"{DETAIL_URL}?it_id={it_id}&ca_id={ca_id}",
                })
        return doctors

    def _parse_schedule_table(self, soup: BeautifulSoup, doctors_by_name: dict[str, dict]) -> None:
        """schedule.php 테이블을 파싱해 해당 진료과 의사들에게 schedules 를 주입."""
        table = soup.select_one("div.con02_table table")
        if not table:
            return

        tbody = table.find("tbody")
        if not tbody:
            return
        rows = tbody.find_all("tr", recursive=False)
        if not rows:
            rows = tbody.find_all("tr")

        # 의사 1명당 2행(오전/오후) 구성. 첫 행에 rowspan=2 td (이름)
        idx = 0
        while idx < len(rows):
            row = rows[idx]
            tds = row.find_all("td", recursive=False)
            if not tds:
                idx += 1
                continue
            name_td = tds[0]
            if not name_td.has_attr("rowspan"):
                idx += 1
                continue
            name = name_td.get_text(strip=True)
            if name not in doctors_by_name:
                idx += 2
                continue

            doc = doctors_by_name[name]
            schedules = doc.setdefault("schedules", [])

            for slot_idx, slot in enumerate(("morning", "afternoon")):
                r = rows[idx + slot_idx] if idx + slot_idx < len(rows) else None
                if r is None:
                    continue
                cells = r.find_all("td", recursive=False)
                # 첫 행: [name_td(rowspan), slot_td, 월~일(7)] = 9
                # 둘째 행: [slot_td, 월~일(7)] = 8
                day_cells = cells[2:] if slot_idx == 0 else cells[1:]
                start, end = TIME_RANGES[slot]
                for day_idx, cell in enumerate(day_cells[:7]):
                    if day_idx >= 7:
                        break
                    text = cell.get_text(strip=True)
                    if text and text not in ("-", "", "휴진"):
                        schedules.append({
                            "day_of_week": day_idx,
                            "time_slot": slot,
                            "start_time": start,
                            "end_time": end,
                            "location": text if text not in ACTIVE_CELL_TEXTS else "",
                        })

            idx += 2

    async def _fetch_dept_schedules(self, client: httpx.AsyncClient, ca_id: str, dept_doctors: list[dict]) -> None:
        url = f"{SCHEDULE_URL}?ca_id={ca_id}"
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[PTSM] schedule {ca_id} 실패: {e}")
            return

        soup = BeautifulSoup(resp.text, "html.parser")
        by_name = {d["name"]: d for d in dept_doctors}
        self._parse_schedule_table(soup, by_name)

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with httpx.AsyncClient(headers=self.headers, timeout=30, follow_redirects=True, verify=False) as client:
            depts = await self._fetch_departments(client)
            if not depts:
                self._cached_data = []
                return []

            sem = asyncio.Semaphore(4)
            all_doctors: list[dict] = []
            seen_ids: set[str] = set()

            async def process_dept(ca_id: str, name: str):
                async with sem:
                    dept_docs = await self._fetch_dept_doctors(client, ca_id, name)
                    if dept_docs:
                        await self._fetch_dept_schedules(client, ca_id, dept_docs)
                    return dept_docs

            results = await asyncio.gather(*(process_dept(c, n) for c, n in depts), return_exceptions=True)

            for res in results:
                if isinstance(res, Exception):
                    continue
                for d in res:
                    if d["it_id"] in seen_ids:
                        continue
                    seen_ids.add(d["it_id"])
                    d.setdefault("schedules", [])
                    d["date_schedules"] = []
                    d["staff_id"] = d["external_id"]
                    d["notes"] = ""
                    all_doctors.append(d)

        self._cached_data = all_doctors
        logger.info(f"[PTSM] 크롤링 완료: {len(all_doctors)}명")
        return all_doctors

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
        """개별 조회 — 해당 의사의 ca_id 가 필요하므로 먼저 main.php 로 진료과 리스트를
        얻고, 해당 it_id 를 포함한 ca_id 하나만 찾아 list + schedule 2회만 GET 한다.
        전체 fetch 는 하지 않아 규칙 #7 준수.
        """
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
        it_id = staff_id.replace(prefix, "") if staff_id.startswith(prefix) else staff_id

        async with httpx.AsyncClient(headers=self.headers, timeout=30, follow_redirects=True, verify=False) as client:
            depts = await self._fetch_departments(client)
            # 여러 진료과를 순회하며 it_id 매칭 — 단, 발견 즉시 중단
            for ca_id, dept_name in depts:
                dept_docs = await self._fetch_dept_doctors(client, ca_id, dept_name)
                match = next((d for d in dept_docs if d["it_id"] == it_id), None)
                if match:
                    await self._fetch_dept_schedules(client, ca_id, dept_docs)
                    match.setdefault("schedules", [])
                    match["date_schedules"] = []
                    match["staff_id"] = match["external_id"]
                    match["notes"] = ""
                    return match

        return empty

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
