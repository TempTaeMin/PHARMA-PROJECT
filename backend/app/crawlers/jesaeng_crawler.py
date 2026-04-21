"""분당제생병원(JESAENG) 크롤러

도메인: https://www.dmc.or.kr
구조:
- 진료과 목록: /dept/deptList.do (41개, 일반 진료과 + 특화센터 S0*)
- 진료과별 의료진 + 주간 진료시간표: /dept/deptView.do?deptCd={CD}&deptNo={NO}
- 의사 카드: <li profEmpCd="1008331"> … 진료시간 table
- 예약: /reserve/verifyMe.do?deptCd={CD}&profEmpCd={EMP}
external_id: JESAENG-{profEmpCd}
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime

import httpx

from app.crawlers._schedule_rules import find_exclude_keyword, has_biweekly_mark

logger = logging.getLogger(__name__)

BASE_URL = "https://www.dmc.or.kr"

# (deptCd, deptNo, Korean name)
JESAENG_DEPTS: list[tuple[str, str, str]] = [
    ("FM", "43", "가정의학과"),
    ("IMI", "51", "감염내과"),
    ("IME", "23", "내분비내과"),
    ("IMR", "25", "류마티스내과"),
    ("AN", "50", "마취통증의학과"),
    ("RO", "53", "방사선종양학과"),
    ("DP", "49", "병리과"),
    ("UR", "36", "비뇨의학과"),
    ("OG", "31", "산부인과"),
    ("PS", "30", "성형외과"),
    ("PED", "32", "소아청소년과"),
    ("IMG", "55", "소화기내과"),
    ("NR", "37", "신경과"),
    ("NS", "28", "신경외과"),
    ("IMN", "56", "신장내과"),
    ("IMC", "1", "심장혈관내과"),
    ("CS", "29", "심장혈관흉부외과"),
    ("OT", "33", "안과"),
    ("DR", "47", "영상의학과"),
    ("GS", "26", "외과"),
    ("EM", "46", "응급의학과"),
    ("OL", "34", "이비인후과"),
    ("SP", "61", "중환자의학과"),
    ("CP", "48", "진단검사의학과"),
    ("RM", "41", "재활의학과"),
    ("NP", "4", "정신건강의학과"),
    ("OS", "27", "정형외과"),
    ("DT", "44", "치과"),
    ("DM", "35", "피부과"),
    ("NM", "52", "핵의학과"),
    ("IMO", "24", "혈액종양내과"),
    ("IMP", "57", "호흡기-알레르기내과"),
]

DAY_INDEX = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5}
TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}


class JesaengCrawler:
    def __init__(self):
        self.hospital_code = "JESAENG"
        self.hospital_name = "분당제생병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        self._cached_data: list[dict] | None = None

    async def get_departments(self) -> list[dict]:
        return [{"code": cd, "name": name} for cd, _, name in JESAENG_DEPTS]

    def _parse_dept_page(self, html: str, dept_cd: str, dept_name: str) -> list[dict]:
        doctors: list[dict] = []
        # 각 의사 block: <li profEmpCd="..." … </li> 의 li 블록을 정확히 매치
        # </li> 가 중첩되므로 profEmpCd 시작점부터 다음 profEmpCd 또는 ul 끝까지 수집
        positions = [m.start() for m in re.finditer(r'<li\s+profEmpCd="(\d+)"', html)]
        positions.append(len(html))
        for i, start in enumerate(positions[:-1]):
            block = html[start:positions[i + 1]]
            emp_m = re.search(r'profEmpCd="(\d+)"', block)
            if not emp_m:
                continue
            emp_cd = emp_m.group(1)
            doc = self._parse_doctor_block(block, emp_cd, dept_cd, dept_name)
            if doc:
                doctors.append(doc)
        return doctors

    def _parse_doctor_block(self, block: str, emp_cd: str, dept_cd: str, dept_name: str) -> dict | None:
        name_m = re.search(r'<p class="doctor_info_top">\s*([^<\n]+?)\s*</p>', block)
        if not name_m:
            return None
        name = name_m.group(1).strip()

        specialty = ""
        spec_m = re.search(r"<span>전문분야</span>\s*<em>([^<]+)</em>", block)
        if spec_m:
            specialty = spec_m.group(1).strip()

        # 비고 (notes)
        notes = ""
        note_m = re.search(r'<div class="doctor_table_etc">(.*?)</div>', block, re.DOTALL)
        if note_m:
            clean = re.sub(r"<[^>]+>", "", note_m.group(1))
            notes = clean.strip()

        profile_idx = ""
        pv_m = re.search(r"openDoctorView\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)", block)
        if pv_m:
            profile_idx = pv_m.group(2)

        schedules = self._parse_schedule_block(block)

        if any(has_biweekly_mark(s.get("location") or "") for s in schedules):
            if not has_biweekly_mark(notes):
                notes = (notes + " 격주 근무").strip() if notes else "격주 근무"

        return {
            "staff_id": f"JESAENG-{emp_cd}",
            "external_id": f"JESAENG-{emp_cd}",
            "name": name,
            "department": dept_name,
            "position": "",
            "specialty": specialty,
            "profile_url": f"{BASE_URL}/reserve/verifyMe.do?deptCd={dept_cd}&profEmpCd={emp_cd}",
            "notes": notes,
            "schedules": schedules,
            "date_schedules": [],
            "_dept_cd": dept_cd,
            "_profile_idx": profile_idx,
        }

    def _parse_schedule_block(self, block: str) -> list[dict]:
        table_m = re.search(
            r'<div class="doctor_table">\s*<table>(.*?)</table>', block, re.DOTALL
        )
        if not table_m:
            return []
        tbody_m = re.search(r"<tbody>(.*?)</tbody>", table_m.group(1), re.DOTALL)
        if not tbody_m:
            return []
        rows = re.findall(r"<tr>(.*?)</tr>", tbody_m.group(1), re.DOTALL)

        day_order = ["월", "화", "수", "목", "금", "토"]
        slot_order = ["morning", "afternoon"]
        schedules: list[dict] = []
        # 첫 두 행(오전/오후)만
        for idx, row in enumerate(rows[:2]):
            slot = slot_order[idx]
            tds = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
            for i, td in enumerate(tds[:6]):
                # <td></td> 는 빈 칸, <td><span>외래</span></td> 또는 <td>4주</td> 등은 진료 가능
                clean = re.sub(r"<[^>]+>", "", td).strip()
                if clean:
                    if find_exclude_keyword(clean):
                        continue
                    s, e = TIME_RANGES[slot]
                    schedules.append({
                        "day_of_week": DAY_INDEX[day_order[i]],
                        "time_slot": slot,
                        "start_time": s,
                        "end_time": e,
                        "location": clean if clean not in ("외래", "\xa0") else "",
                    })
        return schedules

    async def _fetch_dept(self, client: httpx.AsyncClient, dept_cd: str, dept_no: str, dept_name: str) -> list[dict]:
        url = f"{BASE_URL}/dept/deptView.do"
        try:
            resp = await client.get(url, params={"deptCd": dept_cd, "deptNo": dept_no})
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[JESAENG] {dept_cd}({dept_name}) 실패: {e}")
            return []
        return self._parse_dept_page(resp.text, dept_cd, dept_name)

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        all_doctors: dict[str, dict] = {}
        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True
        ) as client:
            for dept_cd, dept_no, dept_name in JESAENG_DEPTS:
                doctors = await self._fetch_dept(client, dept_cd, dept_no, dept_name)
                for d in doctors:
                    all_doctors.setdefault(d["external_id"], d)
                await asyncio.sleep(0.2)

        result = list(all_doctors.values())
        logger.info(f"[JESAENG] 총 {len(result)}명 수집")
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

        # staff_id 에 dept_cd 정보가 없으므로 모든 진료과 순회하며 찾아야 함
        # → emp_cd 하나만 찾으면 되니 첫 hit 에서 종료
        emp_cd = staff_id.replace("JESAENG-", "") if staff_id.startswith("JESAENG-") else staff_id

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True
        ) as client:
            for dept_cd, dept_no, dept_name in JESAENG_DEPTS:
                doctors = await self._fetch_dept(client, dept_cd, dept_no, dept_name)
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
