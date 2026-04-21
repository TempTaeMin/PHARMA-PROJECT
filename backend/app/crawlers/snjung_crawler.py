"""성남정병원(SNJUNG) 크롤러 — 순천의료재단 성남정병원

도메인: https://chungos.co.kr
- 진료과 목록: /index.php/html/10?srchCenter=CENTERGB{XX} (15개)
- 각 페이지에 모든 진료과 카드 + 상세 정보가 렌더링되어 있으나,
  '응급의학과' 페이지만 진료과 필터가 적용된 의사 목록을 보여줌 (동일한 HTML).
- 의사 카드: <div class="res_drbox res_drboxN"> … <div class="drname">이건영<span>응급센터장</span></div>
- 의사 상세: 같은 페이지 내부 <div id="drviewN">
- external_id: SNJUNG-{seq}
- **주간 진료시간표 미공개** — notes 에 안내 메시지를 넣고 schedules=[]
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://chungos.co.kr"
NOTES_TEMPLATE = (
    "※ 성남정병원은 공식 홈페이지에 교수별 주간 진료시간표를 공개하지 않습니다. "
    "병원에 직접 문의해 주세요."
)

# 진료과(센터) → 한글명 (메인 페이지 ttle 로 수집)
SNJUNG_CENTERS: list[tuple[str, str]] = [
    ("CENTERGB31", "가정의학과"),
    ("CENTERGB32", "마취통증의학과"),
    ("CENTERGB33", "소아청소년과"),
    ("CENTERGB34", "소화기내과"),
    ("CENTERGB35", "순환기내과"),
    ("CENTERGB36", "신경과"),
    ("CENTERGB37", "신경외과"),
    ("CENTERGB38", "신장내과"),
    ("CENTERGB39", "영상의학과"),
    ("CENTERGB40", "외과"),
    ("CENTERGB41", "응급의학과"),
    ("CENTERGB42", "재활의학과"),
    ("CENTERGB43", "정형외과"),
    ("CENTERGB44", "진단검사의학과"),
    ("CENTERGB45", "호흡기내과"),
]


class SnjungCrawler:
    def __init__(self):
        self.hospital_code = "SNJUNG"
        self.hospital_name = "성남정병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        self._cached_data: list[dict] | None = None

    async def get_departments(self) -> list[dict]:
        return [{"code": code, "name": name} for code, name in SNJUNG_CENTERS]

    def _parse_center_page(self, html: str, center_cd: str, dept_name: str) -> list[dict]:
        doctors: list[dict] = []
        # .searcdrbox 에서 "진료과로 찾기" subtitle 직전까지가 센터 필터 결과
        start_m = re.search(r'<div class="searcdrbox">', html)
        end_m = re.search(r'<p class="subtitle1', html[start_m.end():]) if start_m else None
        if start_m and end_m:
            list_html = html[start_m.end(): start_m.end() + end_m.start()]
        else:
            list_html = html

        for m in re.finditer(
            r'<div class="res_drbox res_drbox(\d+)">(.*?)(?=<div class="res_drbox res_drbox|$)',
            list_html,
            re.DOTALL,
        ):
            seq = m.group(1)
            block = m.group(2)

            name_m = re.search(
                r'<div class="drname">\s*([^<]+?)\s*(?:<span>([^<]*)</span>)?\s*</div>',
                block,
            )
            if not name_m:
                continue
            name = name_m.group(1).strip()
            position = (name_m.group(2) or "").strip()
            if not name:
                continue

            specialty = ""
            spec_m = re.search(r"<span>전문분야</span>([^<]+)", block)
            if spec_m:
                specialty = spec_m.group(1).strip()

            # 상세 div 안의 약력
            career = ""
            detail_m = re.search(
                rf'id="drview{seq}"(.*?)(?:<p class="subtitle1|</div>\s*</div>\s*</div>)',
                html,
                re.DOTALL,
            )
            if detail_m:
                detail = detail_m.group(1)
                career_m = re.search(
                    r'<li class="t1">약력</li>\s*<li class="t2"[^>]*>(.*?)</li>',
                    detail,
                    re.DOTALL,
                )
                if career_m:
                    career = re.sub(r"<[^>]+>", "\n", career_m.group(1)).strip()

            doctors.append({
                "staff_id": f"SNJUNG-{seq}",
                "external_id": f"SNJUNG-{seq}",
                "name": name,
                "department": dept_name,
                "position": position,
                "specialty": specialty,
                "profile_url": f"{BASE_URL}/index.php/html/10?srchCenter={center_cd}#drview{seq}",
                "notes": NOTES_TEMPLATE if not career else f"{NOTES_TEMPLATE}\n\n[약력]\n{career}",
                "schedules": [],
                "date_schedules": [],
            })

        return doctors

    async def _fetch_center(self, client: httpx.AsyncClient, center_cd: str, dept_name: str) -> list[dict]:
        url = f"{BASE_URL}/index.php/html/10"
        try:
            resp = await client.get(url, params={"srchCenter": center_cd})
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[SNJUNG] {center_cd}({dept_name}) 실패: {e}")
            return []
        return self._parse_center_page(resp.text, center_cd, dept_name)

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        all_doctors: dict[str, dict] = {}
        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True
        ) as client:
            for center_cd, dept_name in SNJUNG_CENTERS:
                doctors = await self._fetch_center(client, center_cd, dept_name)
                for d in doctors:
                    all_doctors.setdefault(d["external_id"], d)
                await asyncio.sleep(0.2)

        result = list(all_doctors.values())
        logger.info(f"[SNJUNG] 총 {len(result)}명 수집 (주간 스케줄은 미공개)")
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
            "specialty": "", "profile_url": "", "notes": NOTES_TEMPLATE,
            "schedules": [], "date_schedules": [],
        }

        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return {k: d[k] for k in ("staff_id", "name", "department", "position",
                                               "specialty", "profile_url", "notes",
                                               "schedules", "date_schedules")}

        # SEQ 만으로는 어느 센터인지 알 수 없으므로 센터 순회
        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True
        ) as client:
            for center_cd, dept_name in SNJUNG_CENTERS:
                doctors = await self._fetch_center(client, center_cd, dept_name)
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
