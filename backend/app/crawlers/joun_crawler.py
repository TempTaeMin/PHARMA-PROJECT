"""조은오산병원(JOUN) 크롤러

도메인: https://www.osanhospital.com
- 진료과별 페이지: /healthcare/healthcare{N}.php (N=1~21, 일부 결번)
  각 페이지에 <div class="doctor-detail"> 카드(이미지/소개/주간시간표) 반복
- 의사 이미지 파일명(…/doctor27.jpg)을 고유 키로 사용
- 셀: <span class="possible">진료</span>, <span class="possible1">수술</span>, "문의" 등
external_id: JOUN-{hc코드}_{image_key}
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime

import httpx

from app.crawlers._schedule_rules import find_exclude_keyword

logger = logging.getLogger(__name__)

BASE_URL = "https://www.osanhospital.com"

JOUN_DEPTS: list[tuple[str, str]] = [
    ("1", "신경외과"),
    ("2", "정형외과"),
    ("3", "외과"),
    ("4", "내과"),
    ("5", "성형외과"),
    ("6", "신경과"),
    ("7", "피부비뇨의학과"),
    ("9", "마취통증의학과"),
    ("10", "가정의학과"),
    ("11", "재활의학과"),
    ("12", "진단검사의학과"),
    ("14", "영상의학과"),
    ("15", "소아청소년과"),
    ("16", "부인과"),
    ("17", "직업환경의학과"),
    ("18", "신장내과"),
    ("21", "피부미용과"),
]

DAY_INDEX = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5}
TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}


class JounCrawler:
    def __init__(self):
        self.hospital_code = "JOUN"
        self.hospital_name = "조은오산병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }
        self._cached_data: list[dict] | None = None

    async def get_departments(self) -> list[dict]:
        return [{"code": code, "name": name} for code, name in JOUN_DEPTS]

    def _parse_dept_page(self, html: str, hc_code: str, dept_name: str) -> list[dict]:
        doctors: list[dict] = []

        for m in re.finditer(
            r'<div class="doctor-detail[^"]*">(.*?)(?=<div class="doctor-detail|<!--|</section)',
            html,
            re.DOTALL,
        ):
            body = m.group(1)
            img_m = re.search(r'<img src="([^"]+)"\s+alt="([^"]*)"', body)
            if not img_m:
                continue
            img_src = img_m.group(1)
            alt = img_m.group(2)

            # image 파일명 → 키
            key_m = re.search(r"/([A-Za-z0-9_\-]+)\.(?:jpg|png|jpeg|gif)", img_src, re.IGNORECASE)
            if not key_m:
                continue
            image_key = key_m.group(1)

            # alt 포맷: "김건우 - 병원장" 또는 "권기영 - 진료원장/신경외과 전문의"
            name = ""
            position = ""
            if " - " in alt:
                name, rest = alt.split(" - ", 1)
                name = name.strip()
                position = rest.strip()
            else:
                name = alt.strip()

            dept_sub = ""
            dept_m = re.search(r"<dt>진료과</dt>\s*<dd>([^<]+)</dd>", body)
            if dept_m:
                dept_sub = dept_m.group(1).strip()

            specialty = ""
            spec_m = re.search(r"<dt>전문분야</dt>\s*<dd>([^<]+)</dd>", body)
            if spec_m:
                specialty = spec_m.group(1).strip()

            schedules = self._parse_schedule(body)

            ext_id = f"JOUN-{hc_code}_{image_key}"
            doctors.append({
                "staff_id": ext_id,
                "external_id": ext_id,
                "name": name,
                "department": dept_name,
                "position": position,
                "specialty": specialty,
                "profile_url": f"{BASE_URL}/healthcare/healthcare{hc_code}.php",
                "notes": dept_sub if dept_sub and dept_sub != dept_name else "",
                "schedules": schedules,
                "date_schedules": [],
            })
        return doctors

    def _parse_schedule(self, block: str) -> list[dict]:
        table_m = re.search(r'<div class="time">\s*<table>(.*?)</table>', block, re.DOTALL)
        if not table_m:
            return []
        tbody_m = re.search(r"<tbody>(.*?)</tbody>", table_m.group(1), re.DOTALL)
        if not tbody_m:
            return []
        rows = re.findall(r"<tr>(.*?)</tr>", tbody_m.group(1), re.DOTALL)

        day_order = ["월", "화", "수", "목", "금", "토"]
        slot_order = ["morning", "afternoon"]
        schedules: list[dict] = []
        for idx, row in enumerate(rows[:2]):
            slot = slot_order[idx]
            tds = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
            for i, td in enumerate(tds[:6]):
                clean = re.sub(r"<[^>]+>", "", td).strip()
                has_possible = "possible" in td  # possible 또는 possible1
                has_content = clean and clean not in ("-", "")
                if has_possible or has_content:
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

    async def _fetch_dept(self, client: httpx.AsyncClient, hc_code: str, dept_name: str) -> list[dict]:
        url = f"{BASE_URL}/healthcare/healthcare{hc_code}.php"
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[JOUN] hc{hc_code}({dept_name}) 실패: {e}")
            return []
        return self._parse_dept_page(resp.text, hc_code, dept_name)

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        all_doctors: dict[str, dict] = {}
        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False
        ) as client:
            for hc_code, dept_name in JOUN_DEPTS:
                doctors = await self._fetch_dept(client, hc_code, dept_name)
                for d in doctors:
                    all_doctors.setdefault(d["external_id"], d)
                await asyncio.sleep(0.2)

        result = list(all_doctors.values())
        logger.info(f"[JOUN] 총 {len(result)}명 수집")
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

        raw = staff_id.replace("JOUN-", "") if staff_id.startswith("JOUN-") else staff_id
        if "_" not in raw:
            return empty
        hc_code, _ = raw.split("_", 1)
        dept_name = dict(JOUN_DEPTS).get(hc_code, "")

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False
        ) as client:
            doctors = await self._fetch_dept(client, hc_code, dept_name)
            for d in doctors:
                if d["external_id"] == staff_id:
                    return {k: d[k] for k in ("staff_id", "name", "department", "position",
                                               "specialty", "profile_url", "notes",
                                               "schedules", "date_schedules")}
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
