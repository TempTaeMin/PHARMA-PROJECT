"""서울의료원(Seoul Medical Center) 크롤러

병원 공식명: 서울의료원
홈페이지: www.seoulmc.or.kr
백엔드 API: care.seoulmc.or.kr:8305 (JSON)

API 구조:
  1) 진료과 목록: GET /homepage/api/hospital/department
     → [{departmentCode, departmentName, isSpecializedCenter, isBookable}]
  2) 진료과별 의료진: GET /homepage/api/hospital/doctor/{departmentCode}
     → [{doctorCode, doctorName, intro, speciality, isBookable, imgSrc, ...}]
  3) 의사 진료일정: GET /homepage/api/hospital/doctor/{deptCode}/{doctorCode}/{startDate}/{endDate}
     → [{hourType:"AM"|"PM", appointmentDate:"YYYY-MM-DD", todayReceptionStatus}]

external_id: SMC2-{doctorCode}
"""
import asyncio
import logging
import httpx
from datetime import datetime, date, timedelta

logger = logging.getLogger(__name__)

HOME_URL = "https://www.seoulmc.or.kr"
API_BASE = "https://care.seoulmc.or.kr:8305/homepage/api/hospital"
DEPT_API = f"{API_BASE}/department"
DOCTOR_LIST_API = f"{API_BASE}/doctor"  # + /{deptCode}
SCHEDULE_API = f"{API_BASE}/doctor"  # + /{deptCode}/{doctorCode}/{start}/{end}

DOCTOR_VIEW_URL = (
    f"{HOME_URL}/site/medicalguide/department/medicalGuideDoctorDetail.do"
    "?departmentCode={dept}&doctorCode={doc}&menucdv=01010201&sitecdv=S0000100&decorator=pmsweb"
)

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:30", "17:00")}


class Smc2Crawler:
    """서울의료원 크롤러 — JSON API 3종 조합, 3개월치 date_schedules 제공"""

    def __init__(self):
        self.hospital_code = "SMC2"
        self.hospital_name = "서울의료원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Referer": f"{HOME_URL}/",
            "Origin": HOME_URL,
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
            resp = await client.get(DEPT_API)
            resp.raise_for_status()
            js = resp.json()
        except Exception as e:
            logger.error(f"[SMC2] 진료과 목록 실패: {e}")
            return []
        depts = [
            {"code": d["departmentCode"], "name": (d.get("departmentName") or "").strip()}
            for d in js or []
            if d.get("departmentCode") and d.get("departmentName")
        ]
        self._cached_depts = depts
        return depts

    async def _fetch_dept_doctors(
        self, client: httpx.AsyncClient, dept_code: str,
    ) -> list[dict]:
        try:
            resp = await client.get(f"{DOCTOR_LIST_API}/{dept_code}")
            resp.raise_for_status()
            js = resp.json()
        except Exception as e:
            logger.warning(f"[SMC2] {dept_code} 의료진 실패: {e}")
            return []
        return js or []

    async def _fetch_schedule_raw(
        self,
        client: httpx.AsyncClient,
        dept_code: str,
        doctor_code: str,
        start: date,
        end: date,
    ) -> list[dict]:
        url = f"{SCHEDULE_API}/{dept_code}/{doctor_code}/{start.isoformat()}/{end.isoformat()}"
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            js = resp.json()
        except Exception as e:
            logger.warning(f"[SMC2] 시간표 실패 ({dept_code}/{doctor_code}): {e}")
            return []
        return js or []

    def _parse_schedules(
        self, raw: list[dict],
    ) -> tuple[list[dict], list[dict]]:
        """date_schedules + 주간 패턴(schedules) 생성"""
        date_schedules: list[dict] = []
        pattern_set: set[tuple[int, str]] = set()
        for item in raw:
            hour = (item.get("hourType") or "").upper()
            ap_date = item.get("appointmentDate")
            if not ap_date or hour not in ("AM", "PM"):
                continue
            try:
                dt = datetime.strptime(ap_date, "%Y-%m-%d").date()
            except ValueError:
                continue
            slot = "morning" if hour == "AM" else "afternoon"
            start_time, end_time = TIME_RANGES[slot]
            date_schedules.append({
                "schedule_date": ap_date,
                "time_slot": slot,
                "start_time": start_time,
                "end_time": end_time,
                "location": "",
                "status": "진료",
            })
            pattern_set.add((dt.weekday(), slot))

        schedules: list[dict] = []
        for dow, slot in sorted(pattern_set):
            start_time, end_time = TIME_RANGES[slot]
            schedules.append({
                "day_of_week": dow,
                "time_slot": slot,
                "start_time": start_time,
                "end_time": end_time,
                "location": "",
            })
        return schedules, date_schedules

    def _build_doctor(
        self, info: dict, dept_code: str, dept_name: str, raw_sched: list[dict],
    ) -> dict:
        doctor_code = str(info.get("doctorCode") or "").strip()
        name = (info.get("doctorName") or "").strip()
        intro = (info.get("intro") or "").strip()
        specialty = (info.get("speciality") or "").strip()
        img_src = info.get("imgSrc") or ""
        profile_url = DOCTOR_VIEW_URL.format(dept=dept_code, doc=doctor_code)
        # 개별 조회 시 진료과 스캔을 피하려고 external_id에 dept 인코딩
        ext_id = f"SMC2-{dept_code}-{doctor_code}"

        # intro 예: "외과 주임과장 ", "건강증진센터, 대사증후군 주임과장"
        position = ""
        if intro:
            for sep in (",", "/"):
                intro_norm = intro.replace(sep, " ")
            # 가장 마지막 토큰을 직급으로 간주 (주임과장/과장/전문의 등)
            tokens = intro.replace(",", " ").split()
            for tok in reversed(tokens):
                if any(k in tok for k in ("과장", "전문의", "부장", "원장", "교수", "전임의")):
                    position = tok
                    break

        schedules, date_schedules = self._parse_schedules(raw_sched)
        return {
            "staff_id": ext_id,
            "external_id": ext_id,
            "doctor_code": doctor_code,
            "dept_code": dept_code,
            "name": name,
            "department": dept_name,
            "position": position,
            "specialty": specialty,
            "profile_url": profile_url,
            "photo_url": img_src,
            "notes": intro,
            "schedules": schedules,
            "date_schedules": date_schedules,
        }

    def _date_range(self, months: int = 3) -> tuple[date, date]:
        today = date.today()
        return today, today + timedelta(days=months * 30)

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        start, end = self._date_range(months=3)

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

            # doctorCode 첫 등장 기준으로 진료과 귀속 (여러 진료과 중복 노출 방지)
            by_doctor: dict[str, tuple[dict, str, str]] = {}
            for r in dept_results:
                if isinstance(r, Exception):
                    continue
                dept, infos = r
                for info in infos:
                    did = str(info.get("doctorCode") or "").strip()
                    if not did or did in by_doctor:
                        continue
                    by_doctor[did] = (info, dept["code"], dept["name"])

            sem_sched = asyncio.Semaphore(10)

            async def fetch_sched(did, info, dept_code, dept_name):
                async with sem_sched:
                    raw = await self._fetch_schedule_raw(
                        client, dept_code, did, start, end,
                    )
                    return info, dept_code, dept_name, raw

            sched_tasks = [
                asyncio.create_task(fetch_sched(did, info, dc, dn))
                for did, (info, dc, dn) in by_doctor.items()
            ]
            sched_results = await asyncio.gather(*sched_tasks, return_exceptions=True)

            all_doctors: list[dict] = []
            for r in sched_results:
                if isinstance(r, Exception):
                    continue
                info, dept_code, dept_name, raw = r
                all_doctors.append(self._build_doctor(info, dept_code, dept_name, raw))

        logger.info(f"[SMC2] 총 {len(all_doctors)}명")
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
        """개별 교수 조회 — 해당 교수 1명만 네트워크 요청"""
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "",
            "schedules": [], "date_schedules": [],
        }

        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return {k: d.get(k, []) if k in ("schedules", "date_schedules") else d.get(k, "")
                            for k in ("staff_id", "name", "department", "position",
                                     "specialty", "profile_url", "notes",
                                     "schedules", "date_schedules")}
            return empty

        prefix = "SMC2-"
        raw_id = staff_id[len(prefix):] if staff_id.startswith(prefix) else staff_id
        if not raw_id:
            return empty

        # external_id 포맷: SMC2-{deptCode}-{doctorCode} (구버전: SMC2-{doctorCode})
        hinted_dept = ""
        if "-" in raw_id:
            hinted_dept, doctor_code = raw_id.split("-", 1)
        else:
            doctor_code = raw_id

        start, end = self._date_range(months=3)
        async with self._make_client() as client:
            depts = await self._fetch_dept_list(client)
            # 힌트된 진료과를 최우선으로 확인
            if hinted_dept:
                depts = sorted(depts, key=lambda d: 0 if d["code"] == hinted_dept else 1)

            found_info: dict | None = None
            found_dept_code = ""
            found_dept_name = ""
            for d in depts:
                infos = await self._fetch_dept_doctors(client, d["code"])
                for info in infos:
                    if str(info.get("doctorCode") or "").strip() == doctor_code:
                        found_info = info
                        found_dept_code = d["code"]
                        found_dept_name = d["name"]
                        break
                if found_info:
                    break
            if not found_info:
                return empty
            raw = await self._fetch_schedule_raw(
                client, found_dept_code, doctor_code, start, end,
            )

        doc = self._build_doctor(found_info, found_dept_code, found_dept_name, raw)
        return {k: doc.get(k, []) if k in ("schedules", "date_schedules") else doc.get(k, "")
                for k in ("staff_id", "name", "department", "position",
                         "specialty", "profile_url", "notes",
                         "schedules", "date_schedules")}

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
                date_schedules=d.get("date_schedules", []),
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
