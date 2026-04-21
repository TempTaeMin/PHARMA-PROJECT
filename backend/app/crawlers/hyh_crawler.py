"""남양주한양병원(HYH) 크롤러

도메인: https://hynyj.co.kr
- 세션 필요: 최초 /ny/ GET 으로 PHPSESSID 발급 후 /medical/ 접근 가능
- 진료과 목록: /medical/introduce.php?wr_id={N} (21개)
- 진료과 페이지 안에 의료진 카드 + 주간 진료시간표가 함께 렌더링됨
- 의사 카드: <div class='cs_border'>…<p><strong>과명</strong><span>이름 직위</span></p>
- 상세 URL: detail.php?staff_idx={N}&wr_id={dept}
- 진료시간 셀 class: t1=진료 가능, t7=빈 칸
external_id: HYH-{wr_id}_{staff_idx}
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://hynyj.co.kr"

HYH_DEPTS: list[tuple[str, str]] = [
    ("10", "소화기내과"),
    ("12", "이비인후과"),
    ("13", "성인병내과"),
    ("14", "비뇨기과"),
    ("15", "부인과"),
    ("16", "성형외과"),
    ("17", "순환기내과"),
    ("18", "신경외과"),
    ("19", "신장내과"),
    ("20", "외과"),
    ("21", "흉부혈관외과"),
    ("22", "정형외과"),
    ("23", "호흡기내과"),
    ("24", "신경과"),
    ("25", "마취통증의학과"),
    ("26", "진단검사의학과"),
    ("27", "영상의학과"),
    ("28", "응급의학과"),
    ("29", "치과"),
    ("40", "혈액종양내과"),
    ("41", "감염내과"),
]

DAY_INDEX = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5}
TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}


class HyhCrawler:
    def __init__(self):
        self.hospital_code = "HYH"
        self.hospital_name = "남양주한양병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        self._cached_data: list[dict] | None = None

    async def get_departments(self) -> list[dict]:
        return [{"code": code, "name": name} for code, name in HYH_DEPTS]

    async def _ensure_session(self, client: httpx.AsyncClient) -> None:
        """최초 /ny/ 접근으로 세션 쿠키 발급"""
        try:
            await client.get(f"{BASE_URL}/ny/")
        except Exception as e:
            logger.warning(f"[HYH] 세션 초기화 실패: {e}")

    def _parse_dept_page(self, html: str, wr_id: str, dept_name: str) -> list[dict]:
        doctors: list[dict] = []
        # cs_introduce 이후 영역만 사용
        intro_m = re.search(r"cs_introduce", html)
        if not intro_m:
            return []
        section = html[intro_m.end():]

        positions = [m.start() for m in re.finditer(r"<div class='cs_border'>", section)]
        positions.append(len(section))
        for i, start in enumerate(positions[:-1]):
            block = section[start:positions[i + 1]]
            doc = self._parse_doctor_block(block, wr_id, dept_name)
            if doc:
                doctors.append(doc)
        return doctors

    def _parse_doctor_block(self, block: str, wr_id: str, dept_name: str) -> dict | None:
        # 이름/직위: <p><strong>소화기내과</strong><span>임규성  진료과장</span></p>
        name_m = re.search(
            r"<p>\s*<strong>[^<]*</strong>\s*<span>([^<]+)</span>",
            block,
        )
        if not name_m:
            return None
        raw = name_m.group(1).strip()
        tokens = raw.split()
        if len(tokens) >= 2:
            name, position = tokens[0], " ".join(tokens[1:])
        else:
            name, position = raw, ""
        if not name:
            return None

        # staff_idx
        idx_m = re.search(r"staff_idx=(\d+)", block)
        staff_idx = idx_m.group(1) if idx_m else f"x{re.sub(r'[^0-9A-Za-z]', '', name)}"

        schedules = self._parse_schedule_block(block)
        return {
            "staff_id": f"HYH-{wr_id}_{staff_idx}",
            "external_id": f"HYH-{wr_id}_{staff_idx}",
            "name": name,
            "department": dept_name,
            "position": position,
            "specialty": "",
            "profile_url": f"{BASE_URL}/medical/detail.php?staff_idx={staff_idx}&wr_id={wr_id}",
            "notes": "",
            "schedules": schedules,
            "date_schedules": [],
        }

    def _parse_schedule_block(self, block: str) -> list[dict]:
        # PC용 table 만 사용 (csic_table ' 이지만 mo 가 없는 것)
        table_m = re.search(
            r"<div class='csic_table '>.*?<table>(.*?)</table>",
            block,
            re.DOTALL,
        )
        if not table_m:
            return []
        tbody = table_m.group(1)
        rows = re.findall(r"<tr>(.*?)</tr>", tbody, re.DOTALL)

        day_order = ["월", "화", "수", "목", "금", "토"]
        slot_order = ["morning", "afternoon"]
        schedules: list[dict] = []
        # rows[0]=헤더(월-토), rows[1]=오전, rows[2]=오후
        data_rows = rows[1:3]
        for idx, row in enumerate(data_rows):
            slot = slot_order[idx]
            tds = re.findall(r"<td[^>]*class='([^']+)'[^>]*>([^<]*(?:<[^/][^>]*>[^<]*</[^>]+>)*)</td>", row)
            # 단순화: class 속성만 추출
            tds_cls = re.findall(r"<td[^>]*class='([^']+)'", row)
            for i, cls in enumerate(tds_cls[:6]):
                if "t1" in cls:
                    s, e = TIME_RANGES[slot]
                    schedules.append({
                        "day_of_week": DAY_INDEX[day_order[i]],
                        "time_slot": slot,
                        "start_time": s,
                        "end_time": e,
                        "location": "",
                    })
        return schedules

    async def _fetch_dept(self, client: httpx.AsyncClient, wr_id: str, dept_name: str) -> list[dict]:
        url = f"{BASE_URL}/medical/introduce.php"
        try:
            resp = await client.get(url, params={"wr_id": wr_id})
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[HYH] {wr_id}({dept_name}) 실패: {e}")
            return []
        return self._parse_dept_page(resp.text, wr_id, dept_name)

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        all_doctors: dict[str, dict] = {}
        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True
        ) as client:
            await self._ensure_session(client)
            for wr_id, dept_name in HYH_DEPTS:
                doctors = await self._fetch_dept(client, wr_id, dept_name)
                for d in doctors:
                    all_doctors.setdefault(d["external_id"], d)
                await asyncio.sleep(0.2)

        result = list(all_doctors.values())
        logger.info(f"[HYH] 총 {len(result)}명 수집")
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

        raw = staff_id.replace("HYH-", "") if staff_id.startswith("HYH-") else staff_id
        if "_" not in raw:
            return empty
        wr_id, _ = raw.split("_", 1)
        dept_name = dict(HYH_DEPTS).get(wr_id, "")

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True
        ) as client:
            await self._ensure_session(client)
            doctors = await self._fetch_dept(client, wr_id, dept_name)
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
