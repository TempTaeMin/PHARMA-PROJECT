"""굿모닝병원(GOODM) 크롤러

도메인: https://www.goodmhospital.co.kr (경기 평택시)
- 진료과 페이지: /app/reservation/medicine.php?M_IDX={N} (1~32)
- 각 페이지에 <div class="doctor-box" doctor-idx="N"> 카드 반복
- 주간 시간표 <table class="doctor-table"> — 월~토 × 오전/오후
- 셀 값: 진료/검사/-/1시 등
external_id: GOODM-{doctor_idx}
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime

import httpx

from app.crawlers._schedule_rules import find_exclude_keyword

logger = logging.getLogger(__name__)

BASE_URL = "https://www.goodmhospital.co.kr"
# 7, 24번은 빈 페이지. 33+ 없음.
GOODM_DEPT_IDS = [i for i in range(1, 33) if i not in (7, 24)]

DAY_INDEX = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5}
TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}


class GoodmCrawler:
    def __init__(self):
        self.hospital_code = "GOODM"
        self.hospital_name = "굿모닝병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }
        self._cached_data: list[dict] | None = None

    async def get_departments(self) -> list[dict]:
        data = await self._fetch_all()
        names = {d["department"] for d in data}
        return [{"code": n, "name": n} for n in sorted(names)]

    def _parse_dept_name(self, html: str, m_idx: int) -> str:
        # active nav 항목에서 진료과명 추출
        m = re.search(
            rf'<li\s+class="active"\s*>\s*<a href="/app/reservation/medicine\.php\?M_IDX={m_idx}">\s*<p>([^<]+)</p>',
            html,
        )
        return m.group(1).strip() if m else ""

    def _parse_dept_page(self, html: str, m_idx: int) -> list[dict]:
        dept_name = self._parse_dept_name(html, m_idx) or f"medicine{m_idx}"

        doctors: list[dict] = []
        # 각 doctor-box 블록 단위로 추출
        for m in re.finditer(
            r'<div class="doctor-box"\s+doctor-idx="(\d+)">(.*?)(?=<div class="doctor-box"\s+doctor-idx|</article>)',
            html,
            re.DOTALL,
        ):
            doctor_idx = m.group(1)
            body = m.group(2)

            name_m = re.search(r'<div class="doctor-name pcOnly">([^<]+)</div>', body)
            if not name_m:
                continue
            raw = name_m.group(1).strip()
            parts = raw.rsplit(" ", 1)
            position = ""
            if len(parts) == 2 and parts[1] in (
                "과장", "원장", "부장", "진료원장", "병원장", "소장", "교수", "전문의"
            ):
                name = parts[0]
                position = parts[1]
            else:
                name = raw

            # 서브 진료과(예: 소화기내과1)
            sub_m = re.search(
                r'<p class="doctor-title">\s*<span class="color-blue">([^<]+)</span>',
                body,
            )
            sub_dept = sub_m.group(1).strip() if sub_m else ""

            # 전문분야 — <th class="color-blue">전문분야</th><td colspan="6"><p>...</p></td>
            specialty = ""
            spec_m = re.search(
                r'<th class="color-blue">전문분야</th>\s*<td[^>]*>\s*<p>(.*?)</p>',
                body,
                re.DOTALL,
            )
            if spec_m:
                specialty = re.sub(r"<[^>]+>", " ", spec_m.group(1))
                specialty = re.sub(r"\s+", " ", specialty).strip()

            schedules = self._parse_schedule(body)

            notes = sub_dept if sub_dept and sub_dept != dept_name else ""

            doctors.append({
                "staff_id": f"GOODM-{doctor_idx}",
                "external_id": f"GOODM-{doctor_idx}",
                "name": name,
                "department": dept_name,
                "position": position,
                "specialty": specialty,
                "profile_url": f"{BASE_URL}/app/reservation/medicine.php?M_IDX={m_idx}",
                "notes": notes,
                "schedules": schedules,
                "date_schedules": [],
            })
        return doctors

    def _parse_schedule(self, block: str) -> list[dict]:
        table_m = re.search(r'<table class="doctor-table">(.*?)</table>', block, re.DOTALL)
        if not table_m:
            return []
        tbody_m = re.search(r"<tbody>(.*?)</tbody>", table_m.group(1), re.DOTALL)
        if not tbody_m:
            return []
        # 오전/오후 두 행만 취급 (전문분야 행 제외)
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", tbody_m.group(1), re.DOTALL)
        data_rows = []
        for r in rows:
            # 전문분야 행은 th 안에 "전문분야" 포함
            if "전문분야" in r:
                continue
            data_rows.append(r)
            if len(data_rows) >= 2:
                break

        day_order = ["월", "화", "수", "목", "금", "토"]
        slot_order = ["morning", "afternoon"]
        schedules: list[dict] = []
        for idx, row in enumerate(data_rows):
            slot = slot_order[idx]
            tds = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
            for i, td in enumerate(tds[:6]):
                clean = re.sub(r"<[^>]+>", "", td).strip()
                if clean and clean not in ("-", "휴진", "휴무"):
                    if find_exclude_keyword(clean):
                        continue
                    s, e = TIME_RANGES[slot]
                    location = clean if clean not in ("진료", "") else ""
                    schedules.append({
                        "day_of_week": DAY_INDEX[day_order[i]],
                        "time_slot": slot,
                        "start_time": s,
                        "end_time": e,
                        "location": location,
                    })
        return schedules

    async def _fetch_dept(self, client: httpx.AsyncClient, m_idx: int) -> list[dict]:
        url = f"{BASE_URL}/app/reservation/medicine.php"
        try:
            resp = await client.get(url, params={"M_IDX": m_idx})
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[GOODM] M_IDX={m_idx} 실패: {e}")
            return []
        return self._parse_dept_page(resp.text, m_idx)

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        all_doctors: dict[str, dict] = {}
        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False
        ) as client:
            for m_idx in GOODM_DEPT_IDS:
                doctors = await self._fetch_dept(client, m_idx)
                for d in doctors:
                    all_doctors.setdefault(d["external_id"], d)
                await asyncio.sleep(0.15)

        result = list(all_doctors.values())
        logger.info(f"[GOODM] 총 {len(result)}명 수집")
        self._cached_data = result
        return result

    async def crawl_doctor_list(self, department: str = None) -> list[dict]:
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]
        return [
            {k: d[k] for k in ("staff_id", "external_id", "name", "department", "position",
                               "specialty", "profile_url", "notes")}
            for d in data
        ]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "",
            "schedules": [], "date_schedules": [],
        }

        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return {k: d[k] for k in ("staff_id", "name", "department", "position",
                                               "specialty", "profile_url", "notes",
                                               "schedules", "date_schedules")}

        # doctor-idx 만으로는 어느 M_IDX 에 있는지 알 수 없어 순회.
        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False
        ) as client:
            for m_idx in GOODM_DEPT_IDS:
                doctors = await self._fetch_dept(client, m_idx)
                for d in doctors:
                    if d["external_id"] == staff_id:
                        return {k: d[k] for k in ("staff_id", "name", "department", "position",
                                                   "specialty", "profile_url", "notes",
                                                   "schedules", "date_schedules")}
                await asyncio.sleep(0.1)
        return empty

    async def crawl_doctors(self, department: str = None):
        from app.schemas.schemas import CrawlResult, CrawledDoctor

        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]

        doctors = [
            CrawledDoctor(
                name=d["name"], department=d["department"], position=d["position"],
                specialty=d["specialty"], profile_url=d["profile_url"],
                external_id=d["external_id"], notes=d["notes"],
                schedules=d["schedules"], date_schedules=d["date_schedules"],
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
