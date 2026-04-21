"""현대병원(HDGH) 크롤러 — 남양주 다산동 (중앙대 교육협력)

도메인: https://www.hdgh.co.kr
- 진료과 의료진 페이지: /medical/deptDoctor.php?m_seq=2&s_seq={N}&md_seq={N}
- 각 카드: <div class="doctorProfile"> — 이름/직위/진료과목/전문진료분야
- 상세 링크: deptDoctor_detail.php?...&staff_seq={N}
- ※ 홈페이지에 주간 진료시간표가 공개되지 않음 — schedules 는 빈 배열,
  notes 에 안내 문구 기록
external_id: HDGH-{staff_seq}
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://www.hdgh.co.kr"
DEPT_SEQS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20,
             37, 38, 39, 43, 44, 45, 46, 47, 48, 49]
NOTE_TEXT = (
    "※ 현대병원(남양주)은 홈페이지에 주간 진료시간표를 공개하지 않습니다. "
    "진료 가능 시간은 대표번호 031-574-9119 또는 홈페이지 예약 시스템에서 확인해 주세요."
)


class HdghCrawler:
    def __init__(self):
        self.hospital_code = "HDGH"
        self.hospital_name = "현대병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }
        self._cached_data: list[dict] | None = None

    async def get_departments(self) -> list[dict]:
        data = await self._fetch_all()
        names = {d["department"] for d in data}
        return [{"code": n, "name": n} for n in sorted(names)]

    def _parse_dept_name(self, html: str) -> str:
        m = re.search(r'<header>\s*<h4>([^<]+)</h4>', html)
        if m:
            return m.group(1).strip()
        m = re.search(r"<h4>([^<]+)</h4>", html)
        return m.group(1).strip() if m else ""

    def _parse_dept_page(self, html: str, s_seq: int) -> list[dict]:
        dept_name = self._parse_dept_name(html) or f"dept{s_seq}"

        doctors: list[dict] = []
        for m in re.finditer(
            r'<div class="doctorProfile">(.*?)</li>',
            html,
            re.DOTALL,
        ):
            body = m.group(1)
            staff_m = re.search(r"staff_seq=(\d+)", body)
            if not staff_m:
                continue
            staff_seq = staff_m.group(1)

            name_m = re.search(
                r'<strong class="name">\s*([^<]+?)\s*(?:<em>([^<]*)</em>)?\s*</strong>',
                body,
                re.DOTALL,
            )
            if not name_m:
                continue
            name = name_m.group(1).strip()
            position = (name_m.group(2) or "").strip()

            sub_m = re.search(r"<dt>진료과목</dt>\s*<dd>([^<]+)</dd>", body)
            sub_dept = sub_m.group(1).strip() if sub_m else ""

            spec_m = re.search(r"<dt>전문진료분야</dt>\s*<dd>(.*?)</dd>", body, re.DOTALL)
            specialty = ""
            if spec_m:
                specialty = re.sub(r"<[^>]+>", " ", spec_m.group(1))
                specialty = re.sub(r"\s+", " ", specialty).strip()

            notes_parts = [NOTE_TEXT]
            if sub_dept and sub_dept != dept_name:
                notes_parts.insert(0, f"진료과목: {sub_dept}")

            doctors.append({
                "staff_id": f"HDGH-{staff_seq}",
                "external_id": f"HDGH-{staff_seq}",
                "name": name,
                "department": dept_name,
                "position": position,
                "specialty": specialty,
                "profile_url": f"{BASE_URL}/medical/deptDoctor_detail.php?m_seq=2&s_seq={s_seq}&md_seq={s_seq}&staff_seq={staff_seq}",
                "notes": "\n".join(notes_parts),
                "schedules": [],
                "date_schedules": [],
            })
        return doctors

    async def _fetch_dept(self, client: httpx.AsyncClient, s_seq: int) -> list[dict]:
        url = f"{BASE_URL}/medical/deptDoctor.php"
        try:
            resp = await client.get(url, params={"m_seq": 2, "s_seq": s_seq, "md_seq": s_seq})
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[HDGH] s_seq={s_seq} 실패: {e}")
            return []
        return self._parse_dept_page(resp.text, s_seq)

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        all_doctors: dict[str, dict] = {}
        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False
        ) as client:
            for s_seq in DEPT_SEQS:
                doctors = await self._fetch_dept(client, s_seq)
                for d in doctors:
                    all_doctors.setdefault(d["external_id"], d)
                await asyncio.sleep(0.15)

        result = list(all_doctors.values())
        logger.info(f"[HDGH] 총 {len(result)}명 수집 (스케줄 미공개)")
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

        # staff_seq 만으로 어느 s_seq 페이지에 있는지 알 수 없어 순회.
        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False
        ) as client:
            for s_seq in DEPT_SEQS:
                doctors = await self._fetch_dept(client, s_seq)
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
