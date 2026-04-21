"""오산한국병원(OSHANKOOK) 크롤러

도메인: http://www.oshankook.net (EUC-KR 인코딩)
- 진료과 페이지: /theme/grape/mobile/sub04_{NN}.php (01~24)
- 각 페이지에 <div class="sub04_docbox01"> 카드 반복 — 이미지/이름/직위/전문분야/주간시간표
- 의사 이미지 파일명(608_l)의 숫자 부분을 고유 ID 로 사용
- 주간 셀 값 — "진료"/"내시경검사"/"격주진료" 등
external_id: OSHANKOOK-{doctor_id}
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "http://www.oshankook.net"
DEPT_CODES = [f"{n:02d}" for n in range(1, 25)]

DAY_INDEX = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5}
TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}


class OshankookCrawler:
    def __init__(self):
        self.hospital_code = "OSHANKOOK"
        self.hospital_name = "오산한국병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }
        self._cached_data: list[dict] | None = None
        self._dept_name_cache: dict[str, str] = {}

    async def get_departments(self) -> list[dict]:
        data = await self._fetch_all()
        names = {d["department"] for d in data}
        return [{"code": n, "name": n} for n in sorted(names)]

    def _decode(self, content: bytes) -> str:
        try:
            return content.decode("euc-kr")
        except UnicodeDecodeError:
            return content.decode("euc-kr", errors="replace")

    def _parse_dept_name(self, html: str) -> str:
        m = re.search(r"<h3[^>]*>([^<]+)</h3>", html)
        return m.group(1).strip() if m else ""

    def _parse_dept_page(self, html: str, dept_code: str) -> list[dict]:
        dept_name = self._parse_dept_name(html) or f"sub04_{dept_code}"
        self._dept_name_cache[dept_code] = dept_name

        doctors: list[dict] = []
        for m in re.finditer(
            r'<div class="sub04_docbox01">(.*?)(?=<div class="sub04_docbox01"|<div class="sub04_docinfo01"|<div class="sub04_titlebox01")',
            html,
            re.DOTALL,
        ):
            body = m.group(1)
            img_m = re.search(r'<img src="[^"]*/dr_photo/(\d+)[^"]*"\s+alt="([^"]*)"', body)
            if not img_m:
                continue
            doctor_id = img_m.group(1)
            alt = img_m.group(2)

            lb_m = re.search(
                r'<div class="leftbox01"><strong>([^<]+)</strong>\s*([^<]*)</div>',
                body,
            )
            name = ""
            position = ""
            rest = ""
            if lb_m:
                raw_name = lb_m.group(1).strip()
                rest = lb_m.group(2).strip()
                # "김 대 호 과장" → 이름과 직위 분리
                parts = raw_name.rsplit(" ", 1)
                if len(parts) == 2 and parts[1] in ("과장", "원장", "부장", "진료원장", "병원장", "소장", "실장"):
                    name = parts[0].replace(" ", "")
                    position = parts[1]
                else:
                    name = raw_name.replace(" ", "")
            else:
                # alt 에서 이름 추출 — "김 대 호 (소 1 소화기내과)"
                alt_m = re.match(r"([^()]+?)\s*\(", alt)
                if alt_m:
                    name = alt_m.group(1).strip().replace(" ", "")

            specialty = ""
            spec_m = re.search(
                r'<strong class="strong_st01">[^<]*</strong>\s*<span>([^<]+)</span>',
                body,
            )
            if spec_m:
                specialty = spec_m.group(1).strip()

            schedules = self._parse_schedule(body)

            doctors.append({
                "staff_id": f"OSHANKOOK-{doctor_id}",
                "external_id": f"OSHANKOOK-{doctor_id}",
                "name": name,
                "department": dept_name,
                "position": position,
                "specialty": specialty,
                "profile_url": f"{BASE_URL}/theme/grape/mobile/sub04_{dept_code}.php",
                "notes": rest if rest and rest != dept_name else "",
                "schedules": schedules,
                "date_schedules": [],
            })
        return doctors

    def _parse_schedule(self, block: str) -> list[dict]:
        table_m = re.search(r'<table class="time_table01">(.*?)</table>', block, re.DOTALL)
        if not table_m:
            return []
        tbody_m = re.search(r"<tbody>(.*?)</tbody>", table_m.group(1), re.DOTALL)
        if not tbody_m:
            return []
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", tbody_m.group(1), re.DOTALL)

        day_order = ["월", "화", "수", "목", "금", "토"]
        slot_order = ["morning", "afternoon"]
        schedules: list[dict] = []
        for idx, row in enumerate(rows[:2]):
            slot = slot_order[idx]
            tds = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
            # 첫 td 는 "오전"/"오후" 라벨, 나머지 6개가 월-토
            day_tds = tds[1:7]
            for i, td in enumerate(day_tds):
                clean = re.sub(r"<[^>]+>", "", td).strip()
                if clean and clean not in ("-", "휴진", "휴무", "&nbsp;"):
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

    async def _fetch_dept(self, client: httpx.AsyncClient, dept_code: str) -> list[dict]:
        url = f"{BASE_URL}/theme/grape/mobile/sub04_{dept_code}.php"
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[OSHANKOOK] sub04_{dept_code} 실패: {e}")
            return []
        html = self._decode(resp.content)
        return self._parse_dept_page(html, dept_code)

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        all_doctors: dict[str, dict] = {}
        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True
        ) as client:
            for dept_code in DEPT_CODES:
                doctors = await self._fetch_dept(client, dept_code)
                for d in doctors:
                    all_doctors.setdefault(d["external_id"], d)
                await asyncio.sleep(0.15)

        result = list(all_doctors.values())
        logger.info(f"[OSHANKOOK] 총 {len(result)}명 수집")
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

        # 의사별 전용 URL 이 없으므로 모든 dept 페이지 순회. 찾으면 조기 종료.
        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True
        ) as client:
            for dept_code in DEPT_CODES:
                doctors = await self._fetch_dept(client, dept_code)
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
