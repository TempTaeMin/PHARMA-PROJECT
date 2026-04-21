"""동수원병원(DSWHOSP) 크롤러 — 의료법인 녹산의료재단

도메인: http://www.dswhosp.co.kr
- 진료과별 페이지: /medical/medical{NN}.php (01~30) — 의사 카드 + 주간 시간표 포함
- 의사 개별 상세: ?ptype=view&docid={ID}&doctor_code={진료과}
- docid 는 전역 유일한 정수 ID
- 셀 class: pca=진료, pcc=검사, pcb=휴진, poff=1/3주 등 조건부
external_id: DSWHOSP-{docid}
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime

import httpx

from app.crawlers._schedule_rules import find_exclude_keyword, has_biweekly_mark

logger = logging.getLogger(__name__)

BASE_URL = "http://www.dswhosp.co.kr"

# medical01~30 순회. 각 페이지에서 doctor_code 파라미터로 한글 과명 추출.
DSWHOSP_DEPT_CODES = [f"{n:02d}" for n in range(1, 31)]

DAY_INDEX = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5}
TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}


class DswhospCrawler:
    def __init__(self):
        self.hospital_code = "DSWHOSP"
        self.hospital_name = "동수원병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }
        self._cached_data: list[dict] | None = None

    async def get_departments(self) -> list[dict]:
        # 진료과명은 페이지 파싱으로만 알 수 있어 정적 목록 반환 시 코드만
        return [{"code": code, "name": f"medical{code}"} for code in DSWHOSP_DEPT_CODES]

    def _parse_dept_name(self, html: str) -> str:
        m = re.search(r"doctor_code=([^\"'&]+)", html)
        return m.group(1).strip() if m else ""

    def _parse_dept_page(self, html: str, dept_code: str) -> list[dict]:
        dept_name = self._parse_dept_name(html) or f"medical{dept_code}"

        # docid 별로 블록을 수집. 의사 카드는 <h3>이름</h3> 과 <div class="docSchedule"> 가 쌍
        # 페이지에 docid=N 가 복수 위치(상세링크) 에 있어 중복. nameLi/docid 별 block 수집 전략:
        # 각 docid 고유값에 대해 docid=N 첫 번째 출현 위치 근처의 h3/schedule 을 파싱.
        docids = re.findall(r"docid=(\d+)", html)
        seen: set[str] = set()
        doctors: list[dict] = []

        # 의사 블록 패턴: <li class="nameLi"><h3>…</h3></li> … <div class="docSchedule">…</table>
        block_pattern = re.compile(
            r'<li class="nameLi">\s*<h3>([^<]+)</h3>\s*</li>(.*?)(?=<li class="nameLi">|$)',
            re.DOTALL,
        )
        for m in block_pattern.finditer(html):
            name = m.group(1).strip()
            body = m.group(2)
            doc_m = re.search(r"docid=(\d+)&doctor_code=([^\"'&]+)", body)
            if not doc_m:
                continue
            docid = doc_m.group(1)
            if docid in seen:
                continue
            seen.add(docid)

            specialty = ""
            spec_m = re.search(
                r"<span>전문진료분야</span>\s*<p[^>]*>([^<]+)</p>",
                body,
            )
            if spec_m:
                specialty = spec_m.group(1).strip()

            position = ""
            # 병원장/과장 등 — <h3> 이후 같은 블록의 <p class="docTitle"> 류
            title_m = re.search(r'<p class="docTitle"[^>]*>([^<]+)</p>', body)
            if title_m:
                position = title_m.group(1).strip()

            schedules = self._parse_schedule(body)

            notes = ""
            if any(has_biweekly_mark(s.get("location") or "") for s in schedules):
                notes = "격주 근무"

            doctors.append({
                "staff_id": f"DSWHOSP-{docid}",
                "external_id": f"DSWHOSP-{docid}",
                "name": name,
                "department": dept_name,
                "position": position,
                "specialty": specialty,
                "profile_url": f"{BASE_URL}/medical/medical{dept_code}.php?ptype=view&docid={docid}&doctor_code={dept_name}",
                "notes": notes,
                "schedules": schedules,
                "date_schedules": [],
            })
        return doctors

    def _parse_schedule(self, block: str) -> list[dict]:
        sched_m = re.search(r'class="docSchedule"[^>]*>\s*<table>(.*?)</table>', block, re.DOTALL)
        if not sched_m:
            return []
        tbody_m = re.search(r"<tbody>(.*?)</tbody>", sched_m.group(1), re.DOTALL)
        if not tbody_m:
            return []
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", tbody_m.group(1), re.DOTALL)

        day_order = ["월", "화", "수", "목", "금", "토"]
        slot_order = ["morning", "afternoon"]
        schedules: list[dict] = []

        data_rows = [r for r in rows if "only_m" not in r][:2]
        for idx, row in enumerate(data_rows):
            slot = slot_order[idx]
            tds = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
            if not tds:
                continue
            # 첫 td 는 "오전"/"오후" 라벨, 나머지 6개가 월-토
            day_tds = tds[1:7]
            for i, td in enumerate(day_tds):
                clean = re.sub(r"<[^>]+>", "", td).strip()
                has_pca = "pca" in td
                has_pcc = "pcc" in td  # 검사 — MR 방문 대상 아님, 제외
                has_poff = "poff" in td and clean
                if has_pcc:
                    continue
                if has_pca or has_poff:
                    if find_exclude_keyword(clean):
                        continue
                    s, e = TIME_RANGES[slot]
                    if has_pca:
                        location = ""
                    else:
                        location = clean
                    schedules.append({
                        "day_of_week": DAY_INDEX[day_order[i]],
                        "time_slot": slot,
                        "start_time": s,
                        "end_time": e,
                        "location": location,
                    })
        return schedules

    async def _fetch_dept(self, client: httpx.AsyncClient, dept_code: str) -> list[dict]:
        url = f"{BASE_URL}/medical/medical{dept_code}.php"
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[DSWHOSP] medical{dept_code} 실패: {e}")
            return []
        return self._parse_dept_page(resp.text, dept_code)

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        all_doctors: dict[str, dict] = {}
        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True
        ) as client:
            for dept_code in DSWHOSP_DEPT_CODES:
                doctors = await self._fetch_dept(client, dept_code)
                for d in doctors:
                    all_doctors.setdefault(d["external_id"], d)
                await asyncio.sleep(0.2)

        result = list(all_doctors.values())
        logger.info(f"[DSWHOSP] 총 {len(result)}명 수집")
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

        # docid 만으로는 어느 medical{NN} 페이지에 있는지 알 수 없어 순회. 찾으면 조기 종료.
        docid = staff_id.replace("DSWHOSP-", "") if staff_id.startswith("DSWHOSP-") else staff_id
        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True
        ) as client:
            for dept_code in DSWHOSP_DEPT_CODES:
                doctors = await self._fetch_dept(client, dept_code)
                for d in doctors:
                    if d["external_id"] == f"DSWHOSP-{docid}":
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
