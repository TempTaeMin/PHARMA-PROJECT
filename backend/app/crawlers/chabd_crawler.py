"""분당차병원(CHABD) 크롤러

도메인: https://bundang.chamc.co.kr
구조:
- 진료과 목록: /medical/department.cha → /medical/department/{Slug}/medicalStaff.cha
- 각 진료과 staff 페이지에 의료진 카드 + 주간 진료일정표가 이미 렌더링됨
- 예약/프로필: meddr 파라미터 = 의사 고유 ID (예: AA43071)
external_id: CHABD-{slug}_{meddr}
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://bundang.chamc.co.kr"

# 진료과 slug → 한글명 매핑 (일부 페이지는 title 이 비어있어 하드코딩)
CHABD_DEPT_MAP: dict[str, str] = {
    "Cardiology": "심장내과",
    "CardiovascularSurgery": "심장혈관흉부외과",
    "ClinicalPharmacology": "임상약리학과",
    "Dentistry": "치과",
    "Dermatology": "피부과",
    "EmergencyMedicine": "응급의학과",
    "Endocrinology": "내분비내과",
    "FamilyMedicine": "가정의학과",
    "Gastroenterology": "소화기내과",
    "GeneralSurgery": "외과",
    "HematologyDepartment": "혈액내과",
    "InfectiousDiseases": "감염내과",
    "Internal": "내과",
    "LaboratoryMedicine": "진단검사의학과",
    "Nephrology": "신장내과",
    "Neurology": "신경과",
    "Neurosurgery": "신경외과",
    "NuclearMedicine": "핵의학과",
    "OncologyDepartment": "종양내과",
    "Ophthalmology": "안과",
    "OrientalGynecology": "한방부인과",
    "OrientalMedicine": "한의학과",
    "OrthopedicSurgery": "정형외과",
    "Otorhinolaryngology": "이비인후과-두경부외과",
    "PainMedicine": "마취통증의학과",
    "Pathology": "병리과",
    "PlasticSurgery": "성형외과",
    "Psychiatry": "정신건강의학과",
    "PulmonologyAllergy": "호흡기알레르기내과",
    "RadiationOncology": "방사선종양학과",
    "Radiology": "영상의학과",
    "RehabilitationMedicine": "재활의학과",
    "Rheumatology": "류마티스내과",
    "Urology": "비뇨의학과",
}
CHABD_DEPT_SLUGS: list[str] = list(CHABD_DEPT_MAP.keys())

DAY_INDEX = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5}
TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}


class ChabdCrawler:
    def __init__(self):
        self.hospital_code = "CHABD"
        self.hospital_name = "분당차병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        self._cached_data: list[dict] | None = None

    async def get_departments(self) -> list[dict]:
        return [{"code": slug, "name": CHABD_DEPT_MAP[slug]} for slug in CHABD_DEPT_SLUGS]

    def _parse_staff_page(self, html: str, slug: str) -> tuple[str, list[dict]]:
        """staff 페이지 HTML → (korean_dept_name, [의사 dict…])"""
        dept_name = CHABD_DEPT_MAP.get(slug, slug)

        doctors: list[dict] = []
        # 각 의사 카드는 class="medical_schedule_list..."
        for block_m in re.finditer(
            r'<div class="medical_schedule_list[^"]*">(.*?)</div>\s*</div>\s*<!-- //list -->',
            html,
            re.DOTALL,
        ):
            block = block_m.group(1)
            doc = self._parse_doctor_block(block, slug, dept_name)
            if doc:
                doctors.append(doc)

        # fallback: 끝 마커가 없을 수 있으니 완화 패턴
        if not doctors:
            for block_m in re.finditer(
                r'<div class="medical_schedule_list[^"]*">(.*?)(?=<div class="medical_schedule_list|</div>\s*</div>\s*</div>\s*</div>)',
                html,
                re.DOTALL,
            ):
                block = block_m.group(1)
                doc = self._parse_doctor_block(block, slug, dept_name)
                if doc:
                    doctors.append(doc)

        return dept_name, doctors

    def _parse_doctor_block(self, block: str, slug: str, dept_name: str) -> dict | None:
        meddr_m = re.search(r"meddr=([A-Z0-9]+)", block)
        if not meddr_m:
            return None
        meddr = meddr_m.group(1)

        name_m = re.search(r'class="doctor_name"[^>]*>\s*([^<\n]+?)\s*</p>', block)
        if not name_m:
            return None
        raw_name = name_m.group(1).strip()
        tokens = raw_name.split()
        name = tokens[0] if tokens else raw_name
        position = " ".join(tokens[1:]) if len(tokens) > 1 else ""

        specialty = ""
        spec_m = re.search(
            r"<dt>전문분야</dt>\s*<dd>\s*<span>([^<]*)</span>", block
        )
        if spec_m:
            specialty = spec_m.group(1).strip()

        idx_m = re.search(r"/professor/profile\.cha\?idx=(\d+)", block)
        profile_url = (
            f"{BASE_URL}/professor/profile.cha?idx={idx_m.group(1)}"
            if idx_m
            else f"{BASE_URL}/medical/department/{slug}/medicalStaff.cha"
        )

        schedules = self._parse_schedule_block(block)
        return {
            "staff_id": f"CHABD-{slug}_{meddr}",
            "external_id": f"CHABD-{slug}_{meddr}",
            "name": name,
            "department": dept_name,
            "position": position,
            "specialty": specialty,
            "profile_url": profile_url,
            "notes": "",
            "schedules": schedules,
            "date_schedules": [],
        }

    def _parse_schedule_block(self, block: str) -> list[dict]:
        """의사 카드 내부의 진료시간표 table 에서 오전/오후 × 6요일 체크"""
        table_m = re.search(
            r'<table class="table_type_schedule">(.*?)</table>', block, re.DOTALL
        )
        if not table_m:
            return []
        tbody_m = re.search(r"<tbody>(.*?)</tbody>", table_m.group(1), re.DOTALL)
        if not tbody_m:
            return []
        rows = re.findall(r"<tr>(.*?)</tr>", tbody_m.group(1), re.DOTALL)

        schedules: list[dict] = []
        slot_names = ["morning", "afternoon"]
        day_order = ["월", "화", "수", "목", "금", "토"]
        for idx, row in enumerate(rows[:2]):
            slot = slot_names[idx]
            tds = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
            for i, td in enumerate(tds[:6]):
                if "icon_schedule_mark" in td or "<img" in td:
                    s, e = TIME_RANGES[slot]
                    schedules.append({
                        "day_of_week": DAY_INDEX[day_order[i]],
                        "time_slot": slot,
                        "start_time": s,
                        "end_time": e,
                        "location": "",
                    })
        return schedules

    async def _fetch_dept(self, client: httpx.AsyncClient, slug: str) -> list[dict]:
        url = f"{BASE_URL}/medical/department/{slug}/medicalStaff.cha"
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[CHABD] {slug} staff 페이지 실패: {e}")
            return []
        _, doctors = self._parse_staff_page(resp.text, slug)
        return doctors

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        all_doctors: dict[str, dict] = {}
        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True
        ) as client:
            for slug in CHABD_DEPT_SLUGS:
                doctors = await self._fetch_dept(client, slug)
                for d in doctors:
                    all_doctors.setdefault(d["external_id"], d)
                await asyncio.sleep(0.2)

        result = list(all_doctors.values())
        logger.info(f"[CHABD] 총 {len(result)}명 수집")
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

        # external_id: CHABD-{slug}_{meddr}
        raw = staff_id.replace("CHABD-", "") if staff_id.startswith("CHABD-") else staff_id
        if "_" not in raw:
            logger.warning(f"[CHABD] 잘못된 staff_id 형식: {staff_id}")
            return empty
        slug, meddr = raw.split("_", 1)

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True
        ) as client:
            doctors = await self._fetch_dept(client, slug)
            match = next((d for d in doctors if d["external_id"] == staff_id), None)
            if not match:
                return empty

        return {
            "staff_id": match["staff_id"],
            "name": match["name"],
            "department": match["department"],
            "position": match["position"],
            "specialty": match["specialty"],
            "profile_url": match["profile_url"],
            "notes": match["notes"],
            "schedules": match["schedules"],
            "date_schedules": match["date_schedules"],
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
