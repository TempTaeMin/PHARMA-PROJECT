"""삼육서울병원(Sahmyook Seoul Medical Center) 크롤러

병원 공식명: 삼육서울병원 (Sahmyook Medical Center Seoul)
도메인: www.symcs.co.kr
기술: Angular SPA + JSON API (form/JSON POST)

API 구조:
  1) 진료과 목록: POST /select/department/active  FormData: schWrd=""
     → {returnCode, data:[{code, name, reserveYn, ...}]}
  2) 진료과별 의료진: POST /select/doctor/list  FormData: departmentCode=XXX
     → data:[{doctorId, name, departmentCode, departmentName, positionTitle,
              major, imgPath, career, academy, education, thesis, ...}]
  3) 의사 진료시간표: POST /doctor/timetable  JSON: {departmentCode, doctorId}
     → data:[{ monAmClnGb..sunPmClnGb }]  (값이 "진료" 이면 해당 슬롯 진료)

external_id: SYMC-{doctorId}
"""
import asyncio
import logging
import httpx
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://www.symcs.co.kr"
DEPT_API = f"{BASE_URL}/select/department/active"
DOCTOR_LIST_API = f"{BASE_URL}/select/doctor/list"
TIMETABLE_API = f"{BASE_URL}/doctor/timetable"
DOCTOR_VIEW_URL = f"{BASE_URL}/medical/doctor/view.do?id={{doctor_id}}"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:30", "17:00")}

# 요일 접두사: DOW index → (AM key, PM key)
DOW_KEYS = [
    ("monAmClnGb", "monPmClnGb"),   # 0 Mon
    ("tuesAmClnGb", "tuesPmClnGb"), # 1 Tue
    ("wedAmClnGb", "wedPmClnGb"),   # 2 Wed
    ("thusAmClnGb", "thusPmClnGb"), # 3 Thu
    ("friAmClnGb", "friPmClnGb"),   # 4 Fri
    ("satAmClnGb", "satPmClnGb"),   # 5 Sat
    ("sunAmClnGb", "sunPmClnGb"),   # 6 Sun
]


class SymcCrawler:
    """삼육서울병원 크롤러 — JSON API 3종 조합"""

    def __init__(self):
        self.hospital_code = "SYMC"
        self.hospital_name = "삼육서울병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Referer": BASE_URL,
        }
        self._cached_data: list[dict] | None = None
        self._cached_depts: list[dict] | None = None

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        )

    async def _fetch_dept_list(self, client: httpx.AsyncClient) -> list[dict]:
        if self._cached_depts is not None:
            return self._cached_depts
        try:
            resp = await client.post(DEPT_API, files={"schWrd": (None, "")})
            resp.raise_for_status()
            js = resp.json()
        except Exception as e:
            logger.error(f"[SYMC] 진료과 목록 실패: {e}")
            return []
        depts = [
            {"code": d["code"], "name": d["name"]}
            for d in js.get("data", [])
            if d.get("deleteYn") != "Y" and d.get("code") and d.get("name")
        ]
        self._cached_depts = depts
        return depts

    async def _fetch_dept_doctors(
        self, client: httpx.AsyncClient, dept_code: str,
    ) -> list[dict]:
        try:
            resp = await client.post(
                DOCTOR_LIST_API, files={"departmentCode": (None, dept_code)},
            )
            resp.raise_for_status()
            js = resp.json()
        except Exception as e:
            logger.warning(f"[SYMC] {dept_code} 의료진 실패: {e}")
            return []
        return js.get("data", [])

    async def _fetch_timetable(
        self, client: httpx.AsyncClient, dept_code: str, doctor_id: str,
    ) -> dict | None:
        try:
            resp = await client.post(
                TIMETABLE_API,
                json={"departmentCode": dept_code, "doctorId": doctor_id},
                headers={**self.headers, "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            js = resp.json()
        except Exception as e:
            logger.warning(f"[SYMC] 시간표 실패 ({dept_code}/{doctor_id}): {e}")
            return None
        data = js.get("data") or []
        return data[0] if data else None

    def _build_schedules(self, tt: dict | None) -> list[dict]:
        if not tt:
            return []
        schedules: list[dict] = []
        for dow, (am_key, pm_key) in enumerate(DOW_KEYS):
            for slot_name, key in (("morning", am_key), ("afternoon", pm_key)):
                val = tt.get(key)
                if not val or not isinstance(val, str):
                    continue
                if val.strip() in ("", "-", "휴진"):
                    continue
                start, end = TIME_RANGES[slot_name]
                schedules.append({
                    "day_of_week": dow,
                    "time_slot": slot_name,
                    "start_time": start,
                    "end_time": end,
                    "location": "",
                })
        return schedules

    def _build_doctor(self, info: dict, tt: dict | None) -> dict:
        doctor_id = str(info.get("doctorId") or "")
        name = info.get("name", "") or info.get("mddrNm", "")
        dept_name = info.get("departmentName", "")
        position = info.get("positionTitle", "") or ""
        specialty = info.get("major", "") or ""
        img_path = info.get("imgPath") or ""
        photo_url = ""
        if img_path:
            photo_url = img_path if img_path.startswith("http") else f"{BASE_URL}{img_path}"
        profile_url = DOCTOR_VIEW_URL.format(doctor_id=doctor_id)
        ext_id = f"SYMC-{doctor_id}"
        return {
            "staff_id": ext_id,
            "external_id": ext_id,
            "doctor_id": doctor_id,
            "name": name,
            "department": dept_name,
            "department_code": info.get("departmentCode", ""),
            "position": position,
            "specialty": specialty,
            "profile_url": profile_url,
            "photo_url": photo_url,
            "notes": "",
            "schedules": self._build_schedules(tt),
        }

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with self._make_client() as client:
            depts = await self._fetch_dept_list(client)
            if not depts:
                self._cached_data = []
                return []

            sem_dept = asyncio.Semaphore(5)

            async def fetch_dept(d):
                async with sem_dept:
                    return d, await self._fetch_dept_doctors(client, d["code"])

            dept_tasks = [asyncio.create_task(fetch_dept(d)) for d in depts]
            dept_results = await asyncio.gather(*dept_tasks, return_exceptions=True)

            # (departmentCode, doctorId) → info (진료과 동시 소속 시 첫 번째 우선)
            doc_by_id: dict[str, tuple[dict, str]] = {}
            for r in dept_results:
                if isinstance(r, Exception):
                    continue
                dept, infos = r
                for info in infos:
                    did = str(info.get("doctorId") or "")
                    if not did or did in doc_by_id:
                        continue
                    doc_by_id[did] = (info, dept["code"])

            sem_tt = asyncio.Semaphore(10)

            async def fetch_tt(did, info, dept_code):
                async with sem_tt:
                    tt = await self._fetch_timetable(client, dept_code, did)
                    return info, tt

            tt_tasks = [
                asyncio.create_task(fetch_tt(did, info, dept_code))
                for did, (info, dept_code) in doc_by_id.items()
            ]
            tt_results = await asyncio.gather(*tt_tasks, return_exceptions=True)

            all_doctors: list[dict] = []
            for r in tt_results:
                if isinstance(r, Exception):
                    continue
                info, tt = r
                all_doctors.append(self._build_doctor(info, tt))

        logger.info(f"[SYMC] 총 {len(all_doctors)}명")
        self._cached_data = all_doctors
        return all_doctors

    # ─── 공개 인터페이스 ───

    async def get_departments(self) -> list[dict]:
        async with self._make_client() as client:
            return await self._fetch_dept_list(client)

    async def crawl_doctor_list(self, department: str = None) -> list[dict]:
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]
        return [
            {k: d[k] for k in ("staff_id", "external_id", "name", "department",
                                "position", "specialty", "profile_url", "notes")}
            for d in data
        ]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 교수 조회 — 타임테이블 API 1~2회 호출"""
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "", "schedules": [],
        }

        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return {k: d.get(k, "") for k in
                            ("staff_id", "name", "department", "position",
                             "specialty", "profile_url", "notes", "schedules")}
            return empty

        prefix = "SYMC-"
        doctor_id = staff_id[len(prefix):] if staff_id.startswith(prefix) else staff_id
        if not doctor_id:
            return empty

        # 의사 소속 진료과를 찾기 위해 진료과 목록 순회 (소규모 병원이라 허용)
        async with self._make_client() as client:
            depts = await self._fetch_dept_list(client)
            found_info: dict | None = None
            found_dept: str = ""
            # 빠른 경로: 진료과별 의료진 목록에서 매칭
            for d in depts:
                infos = await self._fetch_dept_doctors(client, d["code"])
                for info in infos:
                    if str(info.get("doctorId") or "") == doctor_id:
                        found_info = info
                        found_dept = d["code"]
                        break
                if found_info:
                    break
            if not found_info:
                return empty
            tt = await self._fetch_timetable(client, found_dept, doctor_id)

        doc = self._build_doctor(found_info, tt)
        return {k: doc.get(k, "") for k in
                ("staff_id", "name", "department", "position",
                 "specialty", "profile_url", "notes", "schedules")}

    async def crawl_doctors(self, department: str = None):
        from app.schemas.schemas import CrawlResult, CrawledDoctor

        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]

        doctors = [
            CrawledDoctor(
                name=d["name"],
                department=d["department"],
                position=d.get("position", ""),
                specialty=d.get("specialty", ""),
                profile_url=d.get("profile_url", ""),
                external_id=d["external_id"],
                notes=d.get("notes", ""),
                schedules=d["schedules"],
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
