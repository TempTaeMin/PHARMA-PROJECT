"""성남시의료원(SNMCC) 크롤러

도메인: https://www.scmc.kr
구조:
- 진료과 목록: /treatmentguide/TreatmentDep/ (29개)
- 진료과별 의료진: /treatmentguide/TreatmentDepStaff/?treat_cd={CODE}
- 진료과별 진료시간표: /treatmentguide/TreatmentDepSchedule/?treat_cd={CODE}
- 의사 상세: introduce_click('{doc_no}','{treat_cd}','') → /treatmentguide/DoctorIntroduce/
external_id: SNMCC-{treat_cd}_{doc_no}
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://www.scmc.kr"

SNMCC_DEPARTMENTS: dict[str, str] = {
    "FM": "가정의학과",
    "IMI": "감염내과",
    "IME": "내분비내과",
    "IMJ": "류마티스내과",
    "AN": "마취통증의학과",
    "PA": "병리과",
    "UR": "비뇨의학과",
    "OG": "산부인과",
    "PED": "소아청소년과",
    "IMG": "소화기내과",
    "IMC": "순환기내과",
    "NR": "신경과",
    "NS": "신경외과",
    "IMN": "신장내과",
    "OT": "안과",
    "DR": "영상의학과",
    "GS": "외과",
    "EM": "응급의학과",
    "OL": "이비인후과",
    "RH": "재활의학과",
    "NP": "정신건강의학과",
    "OS": "정형외과",
    "CC": "종합건강검진센터",
    "CP": "진단검사의학과",
    "DS": "치과",
    "DM": "피부과",
    "KM": "한의학과",
    "IMH": "혈액종양내과",
    "IMR": "호흡기알레르기 내과",
}

DAY_INDEX = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5}
TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}


class SnmccCrawler:
    def __init__(self):
        self.hospital_code = "SNMCC"
        self.hospital_name = "성남시의료원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        self._cached_data: list[dict] | None = None

    async def get_departments(self) -> list[dict]:
        return [{"code": code, "name": name} for code, name in SNMCC_DEPARTMENTS.items()]

    async def _fetch_staff_for_dept(self, client: httpx.AsyncClient, treat_cd: str) -> list[dict]:
        """진료과 한 곳의 의료진 기본 정보 수집"""
        url = f"{BASE_URL}/treatmentguide/TreatmentDepStaff/"
        try:
            resp = await client.get(url, params={"treat_cd": treat_cd})
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[SNMCC] staff 조회 실패 {treat_cd}: {e}")
            return []

        text = resp.text
        doctors: list[dict] = []
        for m in re.finditer(r"<li>\s*<div class=\"docPho\">(.*?)</li>", text, re.DOTALL):
            block = m.group()
            click = re.search(r"introduce_click\('([^']+)','([^']+)'", block)
            if not click:
                continue
            doc_no, dept_cd = click.group(1), click.group(2)
            name_m = re.search(r'<div class="docInfo">\s*<p>([^<]+)</p>', block)
            name = name_m.group(1).strip() if name_m else ""
            if not name:
                continue
            specialty = ""
            spec_m = re.search(r"<dt>전문분야</dt>\s*<dd>([^<]*)</dd>", block)
            if spec_m:
                specialty = spec_m.group(1).strip()
            position = ""
            pos_m = re.search(r"<dt>직위</dt>\s*<dd>([^<]*)</dd>", block)
            if pos_m:
                position = pos_m.group(1).strip()
            doctors.append({
                "doc_no": doc_no,
                "treat_cd": dept_cd,
                "name": name,
                "specialty": specialty,
                "position": position,
            })
        return doctors

    async def _fetch_schedule_for_dept(self, client: httpx.AsyncClient, treat_cd: str) -> dict[str, list[dict]]:
        """진료과 한 곳의 주간 진료시간표 (이름 → schedules 리스트)"""
        url = f"{BASE_URL}/treatmentguide/TreatmentDepSchedule/"
        try:
            resp = await client.get(url, params={"treat_cd": treat_cd})
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[SNMCC] schedule 조회 실패 {treat_cd}: {e}")
            return {}

        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table")
        if not table:
            return {}
        tbody = table.find("tbody")
        if not tbody:
            return {}

        day_order = ["월", "화", "수", "목", "금", "토"]
        slot_order = ["morning", "afternoon"]
        result: dict[str, list[dict]] = {}
        for tr in tbody.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) < 13:
                continue
            name = tds[0].get_text(strip=True)
            if not name:
                continue
            schedules: list[dict] = []
            for i, day in enumerate(day_order):
                for j, slot in enumerate(slot_order):
                    cell = tds[1 + i * 2 + j]
                    cls = cell.get("class") or []
                    if "sur" in cls:
                        s, e = TIME_RANGES[slot]
                        schedules.append({
                            "day_of_week": DAY_INDEX[day],
                            "time_slot": slot,
                            "start_time": s,
                            "end_time": e,
                            "location": "",
                        })
            result[name] = schedules
        return result

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        all_doctors: dict[str, dict] = {}
        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True
        ) as client:
            for treat_cd, dept_name in SNMCC_DEPARTMENTS.items():
                staff = await self._fetch_staff_for_dept(client, treat_cd)
                if not staff:
                    await asyncio.sleep(0.2)
                    continue
                schedules = await self._fetch_schedule_for_dept(client, treat_cd)

                for doc in staff:
                    ext_id = f"SNMCC-{treat_cd}_{doc['doc_no']}"
                    if ext_id in all_doctors:
                        continue
                    all_doctors[ext_id] = {
                        "staff_id": ext_id,
                        "external_id": ext_id,
                        "name": doc["name"],
                        "department": dept_name,
                        "position": doc["position"],
                        "specialty": doc["specialty"],
                        "profile_url": f"{BASE_URL}/treatmentguide/DoctorIntroduce/?doc_no={doc['doc_no']}&treat_cd={treat_cd}",
                        "notes": "",
                        "schedules": schedules.get(doc["name"], []),
                        "date_schedules": [],
                    }
                await asyncio.sleep(0.2)

        result = list(all_doctors.values())
        logger.info(f"[SNMCC] 총 {len(result)}명 수집")
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
                    return {
                        "staff_id": d["staff_id"], "name": d["name"],
                        "department": d["department"], "position": d["position"],
                        "specialty": d["specialty"], "profile_url": d["profile_url"],
                        "notes": d["notes"], "schedules": d["schedules"],
                        "date_schedules": d["date_schedules"],
                    }

        # external_id: SNMCC-{treat_cd}_{doc_no}
        raw = staff_id.replace("SNMCC-", "") if staff_id.startswith("SNMCC-") else staff_id
        if "_" not in raw:
            logger.warning(f"[SNMCC] 잘못된 staff_id 형식: {staff_id}")
            return empty
        treat_cd, doc_no = raw.split("_", 1)
        dept_name = SNMCC_DEPARTMENTS.get(treat_cd, "")

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True
        ) as client:
            staff = await self._fetch_staff_for_dept(client, treat_cd)
            match = next((d for d in staff if d["doc_no"] == doc_no), None)
            if not match:
                return empty
            schedules = await self._fetch_schedule_for_dept(client, treat_cd)

        return {
            "staff_id": staff_id,
            "name": match["name"],
            "department": dept_name,
            "position": match["position"],
            "specialty": match["specialty"],
            "profile_url": f"{BASE_URL}/treatmentguide/DoctorIntroduce/?doc_no={doc_no}&treat_cd={treat_cd}",
            "notes": "",
            "schedules": schedules.get(match["name"], []),
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
