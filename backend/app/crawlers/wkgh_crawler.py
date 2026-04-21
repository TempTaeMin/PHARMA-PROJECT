"""원광종합병원(WKGH) 크롤러 — 경기 화성시 송산동

도메인: http://wkgh.co.kr
- 의료진 페이지: /introduce/introduce03.asp (전체 의료진을 단일 페이지에 노출)
- 카드 구조: <div class="box clear ..."><div class="name">{이름 직위}</div>
            <div class="img">...</div><div class="info"><ul>...</ul></div></div>
- 주간 진료시간표는 홈페이지에 별도 공개되지 않음 — schedules 는 빈 배열
external_id: WKGH-{md5(name+department)[:10]}
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "http://wkgh.co.kr"
NOTE_TEXT = (
    "※ 원광종합병원(화성)은 홈페이지에 주간 진료시간표를 공개하지 않습니다. "
    "진료 가능 시간은 대표번호 031-8077-7200 으로 확인해 주세요."
)

POSITION_KEYWORDS = [
    "병원장", "부원장", "진료부장", "진료원장", "의료원장",
    "센터장", "내과진료센터장", "검진센터장", "마음건강센터장",
    "과장", "실장", "교수", "전문의",
]


class WkghCrawler:
    def __init__(self):
        self.hospital_code = "WKGH"
        self.hospital_name = "원광종합병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }
        self._cached_data: list[dict] | None = None

    async def get_departments(self) -> list[dict]:
        data = await self._fetch_all()
        names = {d["department"] for d in data if d["department"]}
        return [{"code": n, "name": n} for n in sorted(names)]

    def _split_name_position(self, raw: str) -> tuple[str, str]:
        raw = raw.strip()
        # 괄호 내부는 부가 직위로 처리 (e.g. "이형석 내과진료센터장 (감염관리위원장)")
        m = re.match(r"^([가-힣]{2,4})\s+(.+)$", raw)
        if not m:
            return raw, ""
        name = m.group(1)
        position = m.group(2).strip()
        return name, position

    def _ext_id(self, name: str, dept: str) -> str:
        key = hashlib.md5(f"{name}|{dept}".encode("utf-8")).hexdigest()[:10]
        return f"WKGH-{key}"

    def _parse_box(self, box_html: str) -> dict | None:
        name_m = re.search(r'<div class="name">([^<]+)</div>', box_html)
        if not name_m:
            return None
        name, position = self._split_name_position(name_m.group(1))
        if not name:
            return None

        # <div class="info"><ul>...</ul></div>
        info_m = re.search(r'<div class="info">(.*?)</div>\s*</div>', box_html, re.DOTALL)
        info_html = info_m.group(1) if info_m else box_html

        li_texts: list[str] = []
        for m in re.finditer(r'<li[^>]*>(.*?)</li>', info_html, re.DOTALL):
            inner = m.group(1)
            inner = re.sub(r"<br\s*/?>", "\n", inner)
            inner = re.sub(r"<[^>]+>", "", inner)
            li_texts.append(inner.strip())

        # ul 구조: [tt="진료과", 값, tt="전문분야", 값, tt="주요경력", 값, ...]
        department = ""
        specialty = ""
        for i, txt in enumerate(li_texts):
            if txt == "진료과" and i + 1 < len(li_texts):
                department = li_texts[i + 1].strip()
            elif txt == "전문분야" and i + 1 < len(li_texts):
                specialty = re.sub(r"\s+", " ", li_texts[i + 1]).strip()

        return {
            "name": name,
            "position": position,
            "department": department,
            "specialty": specialty,
        }

    def _parse_page(self, html: str) -> list[dict]:
        doctors: list[dict] = []
        # box clear ... 블록 단위 파싱 — <div class="box clear ...."> 부터 다음 box 또는 content 끝까지
        positions = [m.start() for m in re.finditer(r'<div class="box clear', html)]
        positions.append(len(html))
        for i in range(len(positions) - 1):
            block = html[positions[i]:positions[i + 1]]
            parsed = self._parse_box(block)
            if not parsed:
                continue
            ext = self._ext_id(parsed["name"], parsed["department"])
            doctors.append({
                "staff_id": ext,
                "external_id": ext,
                "name": parsed["name"],
                "department": parsed["department"] or "기타",
                "position": parsed["position"],
                "specialty": parsed["specialty"],
                "profile_url": f"{BASE_URL}/introduce/introduce03.asp",
                "notes": NOTE_TEXT,
                "schedules": [],
                "date_schedules": [],
            })
        return doctors

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        url = f"{BASE_URL}/introduce/introduce03.asp"
        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True
        ) as client:
            try:
                resp = await client.get(url)
                resp.raise_for_status()
            except Exception as e:
                logger.error(f"[WKGH] 의료진 페이지 수집 실패: {e}")
                self._cached_data = []
                return []
            html = resp.text

        doctors = self._parse_page(html)
        # 중복 제거
        unique = {d["external_id"]: d for d in doctors}
        result = list(unique.values())
        logger.info(f"[WKGH] 총 {len(result)}명 수집 (스케줄 미공개)")
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

        # 단일 페이지라 1번 GET 으로 전체 파싱. 부하 거의 없음.
        data = await self._fetch_all()
        for d in data:
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
