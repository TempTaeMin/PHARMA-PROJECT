"""강남병원(GNHOSP) 크롤러 — 용인시 기흥구 소재, knmc.or.kr

도메인: https://www.knmc.or.kr
- 진료과 목록: 좌측 메뉴의 medi.php?M_IDX={ID} (21개)
- 진료과별 의료진 + 주간 진료시간표: /clin/medi.php?M_IDX={ID}
- 의사 카드: <div class="doctor"> … <span class="part">부서</span> <span class="name">직위 이름</span>
- 이미지/프로필 id: data-id="{N}" — 의사 고유 식별자
- 진료시간 table: 오전/오후 × 월-토, 셀 class color_A(진료)/color_C(검사)/color_D(-)
external_id: GNHOSP-{M_IDX}_{data-id}
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime

import httpx

from app.crawlers._schedule_rules import find_exclude_keyword

logger = logging.getLogger(__name__)

BASE_URL = "https://www.knmc.or.kr"

GNHOSP_DEPTS: list[tuple[str, str]] = [
    ("1", "소화기내과"),
    ("2", "순환기내과"),
    ("3", "신장내과"),
    ("4", "소아청소년과"),
    ("5", "내분비내과"),
    ("6", "호흡기내과"),
    ("7", "신경과"),
    ("8", "가정의학과"),
    ("9", "정신건강의학과"),
    ("10", "정형외과"),
    ("11", "외과"),
    ("12", "산부인과"),
    ("13", "마취통증의학과"),
    ("15", "신경외과"),
    ("17", "비뇨의학과"),
    ("19", "응급의학과"),
    ("20", "영상의학과"),
    ("21", "진단검사의학과"),
    ("22", "내과"),
    ("23", "건강증진센터"),
    ("24", "달빛어린이병원"),
]

DAY_INDEX = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5}
TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}


class GnhospCrawler:
    def __init__(self):
        self.hospital_code = "GNHOSP"
        self.hospital_name = "강남병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        self._cached_data: list[dict] | None = None

    async def get_departments(self) -> list[dict]:
        return [{"code": code, "name": name} for code, name in GNHOSP_DEPTS]

    def _parse_dept_page(self, html: str, m_idx: str, dept_name: str) -> list[dict]:
        doctors: list[dict] = []
        # medi_outer 안의 doctor 블록만
        outer_m = re.search(r'<div id="outer1"[^>]*class="medi_outer"[^>]*>(.*?)<div id="outer2"', html, re.DOTALL)
        list_html = outer_m.group(1) if outer_m else html

        # doctor block은 <div class="doctor"> ~ 다음 doctor 또는 medi_outer 끝
        positions = [m.start() for m in re.finditer(r'<div class="doctor">', list_html)]
        positions.append(len(list_html))
        for i, start in enumerate(positions[:-1]):
            block = list_html[start:positions[i + 1]]
            doc = self._parse_doctor_block(block, m_idx, dept_name)
            if doc:
                doctors.append(doc)
        return doctors

    def _parse_doctor_block(self, block: str, m_idx: str, dept_name: str) -> dict | None:
        # <span class="name">직위 이름</span>
        pair_m = re.search(
            r'<span class="part">([^<]+)</span>\s*<span class="name">([^<]+)</span>',
            block,
        )
        if not pair_m:
            return None
        part = pair_m.group(1).strip()
        name_raw = pair_m.group(2).strip()
        tokens = name_raw.split()
        if len(tokens) >= 2:
            position, name = tokens[0], " ".join(tokens[1:])
        else:
            position, name = "", name_raw
        if not name:
            return None

        # data-id="3247"
        id_m = re.search(r'data-id="(\d+)"', block)
        doc_id = id_m.group(1) if id_m else f"{m_idx}x{re.sub(r'[^0-9A-Za-z]', '', name)}"

        schedules = self._parse_schedule_block(block)
        return {
            "staff_id": f"GNHOSP-{m_idx}_{doc_id}",
            "external_id": f"GNHOSP-{m_idx}_{doc_id}",
            "name": name,
            "department": dept_name,
            "position": position,
            "specialty": part if part != dept_name else "",
            "profile_url": f"{BASE_URL}/clin/medi.php?M_IDX={m_idx}",
            "notes": "",
            "schedules": schedules,
            "date_schedules": [],
        }

    def _parse_schedule_block(self, block: str) -> list[dict]:
        # 데스크탑용 table.t_plan.pc 만 사용
        table_m = re.search(r'<table[^>]*class="t_plan pc"[^>]*>(.*?)</table>', block, re.DOTALL)
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
            tds = re.findall(r'<td[^>]*class="([^"]*)"[^>]*>([^<]*)</td>', row)
            for i, (cls, content) in enumerate(tds[:6]):
                clean = content.strip()
                if clean and clean != "-" and "color_D" not in cls:
                    if find_exclude_keyword(clean):
                        continue
                    s, e = TIME_RANGES[slot]
                    schedules.append({
                        "day_of_week": DAY_INDEX[day_order[i]],
                        "time_slot": slot,
                        "start_time": s,
                        "end_time": e,
                        "location": clean if clean != "진료" else "",
                    })
        return schedules

    async def _fetch_dept(self, client: httpx.AsyncClient, m_idx: str, dept_name: str) -> list[dict]:
        url = f"{BASE_URL}/clin/medi.php"
        try:
            resp = await client.get(url, params={"M_IDX": m_idx})
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[GNHOSP] {m_idx}({dept_name}) 실패: {e}")
            return []
        return self._parse_dept_page(resp.text, m_idx, dept_name)

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        all_doctors: dict[str, dict] = {}
        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True
        ) as client:
            for m_idx, dept_name in GNHOSP_DEPTS:
                doctors = await self._fetch_dept(client, m_idx, dept_name)
                for d in doctors:
                    all_doctors.setdefault(d["external_id"], d)
                await asyncio.sleep(0.2)

        result = list(all_doctors.values())
        logger.info(f"[GNHOSP] 총 {len(result)}명 수집")
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

        raw = staff_id.replace("GNHOSP-", "") if staff_id.startswith("GNHOSP-") else staff_id
        if "_" not in raw:
            return empty
        m_idx, _ = raw.split("_", 1)
        dept_name = dict(GNHOSP_DEPTS).get(m_idx, "")

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True
        ) as client:
            doctors = await self._fetch_dept(client, m_idx, dept_name)
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
