"""한국원자력의학원(원자력병원) 크롤러

/hospital/timeTable.do 단일 페이지에 전체 의료진 진료시간표가 포함됨.
HTML 테이블 파싱: 진료과 섹션별 <tr> → 의사명, 전문분야, 오전/오후 요일
"""
import re
import logging
import httpx
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

BASE_URL = "https://www.kcch.re.kr"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

# 한글 요일 → day_of_week
DAY_MAP = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5}


class KcchCrawler:
    """한국원자력의학원 크롤러"""

    def __init__(self):
        self.hospital_code = "KCCH"
        self.hospital_name = "한국원자력의학원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        self._cached_data = None
        self._cached_depts = None

    async def _fetch_timetable(self) -> str:
        """전체 진료시간표 HTML 가져오기"""
        async with httpx.AsyncClient(headers=self.headers, timeout=30, follow_redirects=True) as client:
            resp = await client.get(f"{BASE_URL}/hospital/timeTable.do")
            resp.raise_for_status()
            return resp.text

    def _parse_timetable(self, html: str) -> tuple[list[dict], list[dict]]:
        """진료시간표 HTML 파싱 → (departments, doctors)"""
        departments = []
        doctors = []

        # 진료과 탭: viewDept('deptNo') 또는 탭 영역에서 진료과 정보
        dept_tab_pattern = re.compile(
            r"viewDept\s*\(\s*'?(\d+)'?\s*\).*?>([^<]+)<", re.DOTALL
        )
        seen_depts = set()
        for m in dept_tab_pattern.finditer(html):
            dept_no = m.group(1)
            dept_nm = m.group(2).strip()
            if dept_no not in seen_depts and dept_nm:
                seen_depts.add(dept_no)
                departments.append({"code": dept_no, "name": dept_nm})

        # 의사 행 파싱: openDoctorView(deptNo, profNo) → 이름, 전문분야, 오전/오후
        # 각 진료과 섹션은 dept_no로 구분됨
        # 패턴: <tr> 안에 openDoctorView({deptNo}, {profNo}) > {name} </a>
        #        <td>{specialty}</td>
        #        <td>{am_days}</td>
        #        <td>{pm_days}</td>
        current_dept = ""

        # 진료과 헤더 패턴: class="bg_c_lb01" 등 + 진료과명
        # 또는 섹션 시작: deptNo_XXX
        section_pattern = re.compile(
            r'(?:id="deptNo_(\d+)"[^>]*>|class="tit_dep[^"]*"[^>]*>([^<]+)<)',
            re.DOTALL,
        )

        # 의사 행: openDoctorView(deptNo, profNo) > name
        doctor_pattern = re.compile(
            r'openDoctorView\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)[^>]*>\s*([^<]+?)\s*(?:</font>)?\s*</a>\s*</th>\s*'
            r'<td[^>]*>([^<]*)</td>\s*'   # specialty
            r'<td[^>]*>([^<]*)</td>\s*'    # AM days
            r'<td[^>]*>([^<]*)</td>',      # PM days
            re.DOTALL,
        )

        # 진료과 매핑: deptNo → dept_name
        dept_map = {d["code"]: d["name"] for d in departments}

        for m in doctor_pattern.finditer(html):
            dept_no = m.group(1)
            prof_no = m.group(2)
            name = m.group(3).strip()
            specialty = m.group(4).strip()
            am_days_str = m.group(5).strip()
            pm_days_str = m.group(6).strip()

            if not name:
                continue

            dept_nm = dept_map.get(dept_no, "")
            schedules = []

            # 오전 요일 파싱
            if am_days_str:
                for day_char in re.findall(r'[월화수목금토]', am_days_str):
                    if day_char in DAY_MAP:
                        dow = DAY_MAP[day_char]
                        start, end = TIME_RANGES["morning"]
                        schedules.append({
                            "day_of_week": dow, "time_slot": "morning",
                            "start_time": start, "end_time": end, "location": "외래",
                        })

            # 오후 요일 파싱
            if pm_days_str:
                for day_char in re.findall(r'[월화수목금토]', pm_days_str):
                    if day_char in DAY_MAP:
                        dow = DAY_MAP[day_char]
                        start, end = TIME_RANGES["afternoon"]
                        schedules.append({
                            "day_of_week": dow, "time_slot": "afternoon",
                            "start_time": start, "end_time": end, "location": "외래",
                        })

            ext_id = f"KCCH-{prof_no}"
            doctors.append({
                "staff_id": ext_id, "external_id": ext_id,
                "name": name, "department": dept_nm,
                "position": "", "specialty": specialty,
                "profile_url": f"{BASE_URL}/hospital/profDetail.do?profNo={prof_no}&deptNo={dept_no}",
                "notes": "", "schedules": schedules,
                "_dept_no": dept_no, "_prof_no": prof_no,
            })

        logger.info(f"[KCCH] 파싱 완료: {len(departments)}개 진료과, {len(doctors)}명")
        return departments, doctors

    async def _fetch_monthly_schedule(self, client: httpx.AsyncClient, dept_cd: str, prof_emp_no: str, months: int = 3) -> list[dict]:
        """POST /doctor/getMonthSchedule.do → 날짜별 스케줄 수집"""
        date_schedules = []
        now = datetime.now()
        for i in range(months):
            target = now + timedelta(days=i * 30)
            yyyy = target.strftime("%Y")
            mm = target.strftime("%m")
            try:
                resp = await client.post(
                    f"{BASE_URL}/doctor/getMonthSchedule.do",
                    data={"deptCd": dept_cd, "profEmpNo": prof_emp_no, "yyyy": yyyy, "mm": mm},
                )
                resp.raise_for_status()
                data = resp.json()
                # {"20260401":"ALL","20260408":"ALL","20260406":"PM",...}
                for date_key, val in data.items():
                    if not date_key.isdigit() or len(date_key) != 8:
                        continue
                    formatted = f"{date_key[:4]}-{date_key[4:6]}-{date_key[6:8]}"
                    if val in ("AM", "ALL"):
                        date_schedules.append({
                            "schedule_date": formatted, "time_slot": "morning",
                            "start_time": "09:00", "end_time": "12:00",
                            "location": "외래", "status": "진료",
                        })
                    if val in ("PM", "ALL"):
                        date_schedules.append({
                            "schedule_date": formatted, "time_slot": "afternoon",
                            "start_time": "13:00", "end_time": "17:00",
                            "location": "외래", "status": "진료",
                        })
            except Exception as e:
                logger.warning(f"[KCCH] 월별 스케줄 실패 ({yyyy}-{mm}, {prof_emp_no}): {e}")
        return date_schedules

    async def _fetch_doctor_ids(self, client: httpx.AsyncClient, dept_no: str, prof_no: str) -> tuple[str, str]:
        """profViewPop.do에서 deptCd, profEmpNo 추출"""
        try:
            resp = await client.get(
                f"{BASE_URL}/doctor/profViewPop.do",
                params={"deptNo": dept_no, "profNo": prof_no},
            )
            resp.raise_for_status()
            html = resp.text
            dept_cd_m = re.search(r'var\s+deptCd\s*=\s*"([^"]+)"', html)
            emp_no_m = re.search(r'var\s+profEmpNo\s*=\s*"([^"]+)"', html)
            dept_cd = dept_cd_m.group(1) if dept_cd_m else ""
            emp_no = emp_no_m.group(1) if emp_no_m else ""
            return dept_cd, emp_no
        except Exception as e:
            logger.warning(f"[KCCH] profViewPop 실패 (profNo={prof_no}): {e}")
            return "", ""

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data
        html = await self._fetch_timetable()
        depts, doctors = self._parse_timetable(html)
        self._cached_depts = depts

        # 월별 날짜 스케줄 수집
        async with httpx.AsyncClient(headers=self.headers, timeout=60, follow_redirects=True) as client:
            for doc in doctors:
                dept_no = doc.get("_dept_no", "")
                prof_no = doc.get("_prof_no", "")
                if not dept_no or not prof_no:
                    doc["date_schedules"] = []
                    continue
                dept_cd, emp_no = await self._fetch_doctor_ids(client, dept_no, prof_no)
                if dept_cd and emp_no:
                    doc["_dept_cd"] = dept_cd
                    doc["_prof_emp_no"] = emp_no
                    date_scheds = await self._fetch_monthly_schedule(client, dept_cd, emp_no)
                    doc["date_schedules"] = date_scheds
                else:
                    doc["date_schedules"] = []

        self._cached_data = doctors
        return doctors

    async def get_departments(self) -> list[dict]:
        if self._cached_depts is not None:
            return self._cached_depts
        await self._fetch_all()
        return self._cached_depts or []

    async def crawl_doctor_list(self, department: str = None) -> list[dict]:
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]
        return [{k: d[k] for k in ("staff_id", "external_id", "name", "department", "position", "specialty", "profile_url", "notes")} for d in data]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 교수 진료시간 + 월별 날짜 스케줄 조회"""
        _keys = ("staff_id", "name", "department", "position", "specialty", "profile_url", "notes", "schedules", "date_schedules")
        empty = {"staff_id": staff_id, "name": "", "department": "", "position": "",
                 "specialty": "", "profile_url": "", "notes": "", "schedules": [], "date_schedules": []}

        def _extract(d):
            return {k: d.get(k, "" if k not in ("schedules", "date_schedules") else []) for k in _keys}

        # 캐시에서 먼저 검색
        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return _extract(d)
            return empty

        # 전체 크롤링 (날짜 스케줄 포함)
        await self._fetch_all()
        for d in (self._cached_data or []):
            if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                return _extract(d)

        return empty

    async def crawl_doctors(self, department: str = None):
        from app.schemas.schemas import CrawlResult, CrawledDoctor
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]
        doctors = [
            CrawledDoctor(name=d["name"], department=d["department"], position=d["position"],
                          specialty=d["specialty"], profile_url=d["profile_url"],
                          external_id=d["external_id"], notes=d.get("notes", ""),
                          schedules=d["schedules"], date_schedules=d.get("date_schedules", []))
            for d in data
        ]
        return CrawlResult(hospital_code=self.hospital_code, hospital_name=self.hospital_name,
                           status="success" if doctors else "partial", doctors=doctors, crawled_at=datetime.utcnow())
