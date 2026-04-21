"""윌스기념병원(WILLS) 크롤러 — 수원 인계동 척추전문 종합병원

도메인: https://www.allspine.com
- 전체 의료진: /doctor/doctor.html?ct_type=Z (카드 리스트 — name/position/specialty/dr_idx)
- 진료과별 목록: /doctor/doctor.html?ct_type={code} → 해당 센터의 의사만
- 개별 의사 스케줄: /doctor/doctor.html?ct_type=&dr_idx={N}&cls=doctor → 주간 진료시간표
external_id: WILLS-{dr_idx}
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime

import httpx

from app.crawlers._schedule_rules import find_exclude_keyword, has_biweekly_mark

logger = logging.getLogger(__name__)

BASE_URL = "https://www.allspine.com"

WILLS_DEPTS: list[tuple[str, str]] = [
    ("A", "척추센터"),
    ("AA", "비뇨의학과"),
    ("AB", "치매센터"),
    ("AC", "수술센터"),
    ("AE", "혈관센터"),
    ("AF", "호흡기내과"),
    ("AG", "척추변형센터"),
    ("B", "관절센터"),
    ("C", "비수술센터"),
    ("D", "뇌신경센터"),
    ("E", "소화기센터"),
    ("F", "영상진단센터"),
    ("G", "재활치료센터"),
    ("H", "인공관절센터"),
    ("I", "산부인과"),
    ("K", "수면센터"),
    ("L", "응급의학과"),
    ("M", "소아청소년과"),
    ("N", "외과"),
    ("O", "진단검사의학과"),
    ("P", "건강증진센터"),
    ("Q", "인공신장센터"),
    ("R", "심혈관센터"),
    ("S", "뇌혈관센터"),
    ("T", "혈관중재시술센터"),
    ("U", "파킨슨센터"),
    ("Y", "중환자의학과"),
]

DAY_INDEX = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5}
TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}


class WillsCrawler:
    def __init__(self):
        self.hospital_code = "WILLS"
        self.hospital_name = "윌스기념병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }
        self._cached_data: list[dict] | None = None

    async def get_departments(self) -> list[dict]:
        return [{"code": code, "name": name} for code, name in WILLS_DEPTS]

    def _parse_list_card(self, card: str, dept_name: str) -> dict | None:
        idx_m = re.search(r"dr_idx=(\d+)", card)
        if not idx_m:
            return None
        dr_idx = idx_m.group(1)

        name_m = re.search(r'<span class="name"[^>]*>\s*<strong>([^<]+)</strong>', card)
        if not name_m:
            return None
        name = name_m.group(1).strip()

        # 직위: <b>센터장 / 원장</b>
        pos_m = re.search(r"<span class=\"name\"[^>]*>.*?<b[^>]*>(.*?)</b>", card, re.DOTALL)
        position = ""
        if pos_m:
            position = re.sub(r"\s+", " ", pos_m.group(1)).strip()

        # 전공: <span class="position">정형외과 전문의 / 의학박사</span>
        spec_m = re.search(r'<span class="position">(.*?)</span>', card, re.DOTALL)
        specialty = ""
        if spec_m:
            specialty = re.sub(r"\s+", " ", spec_m.group(1)).strip()

        # 전문분야
        history_m = re.search(r'<span class="docHistory">.*?<br\s*/?>\s*(.*?)</span>', card, re.DOTALL)
        detail_spec = ""
        if history_m:
            detail_spec = re.sub(r"\s+", " ", history_m.group(1)).strip()
        if detail_spec:
            specialty = f"{specialty} — {detail_spec}" if specialty else detail_spec

        return {
            "dr_idx": dr_idx,
            "name": name,
            "department": dept_name,
            "position": position,
            "specialty": specialty,
        }

    def _parse_dept_list(self, html: str, dept_name: str) -> list[dict]:
        doctors: list[dict] = []
        for m in re.finditer(
            r'<li>\s*<div>\s*<span class="picture".*?</li>',
            html,
            re.DOTALL,
        ):
            doc = self._parse_list_card(m.group(), dept_name)
            if doc:
                doctors.append(doc)
        return doctors

    def _parse_schedule(self, html: str) -> list[dict]:
        table_m = re.search(r'<div class="typeList">\s*<table>(.*?)</table>', html, re.DOTALL)
        if not table_m:
            return []
        tbody_m = re.search(r"<tbody[^>]*>(.*?)</tbody>", table_m.group(1), re.DOTALL)
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
                if "sc1" in td or (clean and clean not in ("-", "")):
                    if find_exclude_keyword(clean):
                        continue
                    s, e = TIME_RANGES[slot]
                    schedules.append({
                        "day_of_week": DAY_INDEX[day_order[i]],
                        "time_slot": slot,
                        "start_time": s,
                        "end_time": e,
                        "location": clean if clean not in ("진료", "") else "",
                    })
        return schedules

    async def _fetch_dept(self, client: httpx.AsyncClient, code: str, dept_name: str) -> list[dict]:
        url = f"{BASE_URL}/doctor/doctor.html"
        try:
            resp = await client.get(url, params={"ct_type": code})
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[WILLS] {code}({dept_name}) 실패: {e}")
            return []
        return self._parse_dept_list(resp.text, dept_name)

    async def _fetch_detail_schedule(self, client: httpx.AsyncClient, dr_idx: str) -> list[dict]:
        url = f"{BASE_URL}/doctor/doctor.html"
        try:
            resp = await client.get(url, params={"ct_type": "", "dr_idx": dr_idx, "cls": "doctor"})
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[WILLS] 상세 {dr_idx} 실패: {e}")
            return []
        return self._parse_schedule(resp.text)

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        all_doctors: dict[str, dict] = {}
        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False
        ) as client:
            for code, dept_name in WILLS_DEPTS:
                doctors = await self._fetch_dept(client, code, dept_name)
                for d in doctors:
                    if d["dr_idx"] in all_doctors:
                        continue
                    schedules = await self._fetch_detail_schedule(client, d["dr_idx"])
                    ext_id = f"WILLS-{d['dr_idx']}"
                    notes = ""
                    if any(has_biweekly_mark(s.get("location") or "") for s in schedules):
                        notes = "격주 근무"
                    all_doctors[d["dr_idx"]] = {
                        "staff_id": ext_id,
                        "external_id": ext_id,
                        "name": d["name"],
                        "department": d["department"],
                        "position": d["position"],
                        "specialty": d["specialty"],
                        "profile_url": f"{BASE_URL}/doctor/doctor.html?ct_type=&dr_idx={d['dr_idx']}&cls=doctor",
                        "notes": notes,
                        "schedules": schedules,
                        "date_schedules": [],
                    }
                    await asyncio.sleep(0.1)

        result = list(all_doctors.values())
        logger.info(f"[WILLS] 총 {len(result)}명 수집")
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

        dr_idx = staff_id.replace("WILLS-", "") if staff_id.startswith("WILLS-") else staff_id

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False
        ) as client:
            url = f"{BASE_URL}/doctor/doctor.html"
            try:
                resp = await client.get(url, params={"ct_type": "", "dr_idx": dr_idx, "cls": "doctor"})
                resp.raise_for_status()
                html = resp.text
            except Exception as e:
                logger.warning(f"[WILLS] 개별 조회 실패 {staff_id}: {e}")
                return empty

            name_m = re.search(r'<p class="docName[^"]*"[^>]*>\s*([^<\n]+?)\s*</p>', html)
            if not name_m:
                name_m = re.search(r'<h\d[^>]*class="docName[^"]*"[^>]*>\s*([^<\n]+?)\s*</h', html)
            name = name_m.group(1).strip() if name_m else ""

            pos_m = re.search(r'class="docPosition"[^>]*>(.*?)</p>', html, re.DOTALL)
            specialty = re.sub(r"\s+", " ", pos_m.group(1)).strip() if pos_m else ""

            desc_m = re.search(r'class="docDesc"[^>]*>(.*?)</p>', html, re.DOTALL)
            detail_spec = re.sub(r"\s+", " ", desc_m.group(1)).strip() if desc_m else ""
            if detail_spec:
                specialty = f"{specialty} — {detail_spec}" if specialty else detail_spec

            schedules = self._parse_schedule(html)
            notes = ""
            if any(has_biweekly_mark(s.get("location") or "") for s in schedules):
                notes = "격주 근무"
            return {
                "staff_id": staff_id,
                "name": name,
                "department": "",
                "position": "",
                "specialty": specialty,
                "profile_url": f"{BASE_URL}/doctor/doctor.html?ct_type=&dr_idx={dr_idx}&cls=doctor",
                "notes": notes,
                "schedules": schedules,
                "date_schedules": [],
            }

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
