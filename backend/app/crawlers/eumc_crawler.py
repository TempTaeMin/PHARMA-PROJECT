"""이대 계열 병원 공통 크롤러 (이대목동, 이대서울)

API:
  진료과 목록: POST /common/gnbDeptListAjax.do → JSON
  진료시간표: POST /medical/dept/deptSchdoctorList.do → HTML + 인라인 JavaScript

스케줄 파싱:
  HTML 내 JavaScript에서 패턴 추출:
    if('{value}' == "01") { $('#amMon_{dr_sid}').html(...) }
    "01"=외래진료, "03"=특수클리닉 → 진료 있음
    "02"=휴진, ""=없음 → 진료 없음
"""
import re
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

# JavaScript 셀 ID → (day_of_week, time_slot)
SLOT_MAP = {
    "amMon": (0, "morning"), "pmMon": (0, "afternoon"),
    "amTue": (1, "morning"), "pmTue": (1, "afternoon"),
    "amWed": (2, "morning"), "pmWed": (2, "afternoon"),
    "amThu": (3, "morning"), "pmThu": (3, "afternoon"),
    "amFri": (4, "morning"), "pmFri": (4, "afternoon"),
    "amSat": (5, "morning"), "pmSat": (5, "afternoon"),
}

# 스케줄 코드: "01"=외래, "03"=클리닉 → 진료 있음
ACTIVE_CODES = {"01", "03"}


class EumcBaseCrawler:
    """이대 계열 병원 공통 크롤러"""

    def __init__(self, base_url: str, hospital_code: str, hospital_name: str):
        self.base_url = base_url
        self.hospital_code = hospital_code
        self.hospital_name = hospital_name
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "X-Requested-With": "XMLHttpRequest",
        }
        self._cached_data = None
        self._cached_depts = None

    async def _fetch_departments(self) -> list[dict]:
        if self._cached_depts is not None:
            return self._cached_depts
        async with httpx.AsyncClient(headers=self.headers, timeout=30, follow_redirects=True) as client:
            try:
                resp = await client.post(f"{self.base_url}/common/gnbDeptListAjax.do")
                resp.raise_for_status()
                data = resp.json()
                dept_list = data.get("deptList", [])
                logger.info(f"[{self.hospital_code}] 진료과 {len(dept_list)}개")
                self._cached_depts = dept_list
                return dept_list
            except Exception as e:
                logger.error(f"[{self.hospital_code}] 진료과 목록 실패: {e}")
                self._cached_depts = []
                return []

    async def _fetch_monthly_schedule(self, client: httpx.AsyncClient, dr_sid: str, months: int = 3) -> list[dict]:
        """월별 달력 스케줄 가져오기 (docMonthlyScheduleAjax.do)"""
        date_schedules = []
        now = datetime.now()
        for i in range(months):
            target = now + timedelta(days=i * 30)
            ym = target.strftime("%Y-%m")
            try:
                resp = await client.post(
                    f"{self.base_url}/doctor/docMonthlyScheduleAjax.do",
                    data={"dat": ym, "dr_sid": dr_sid},
                )
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")

                for cell in soup.select("div[data-day]"):
                    date_str = cell.get("data-day", "").strip()
                    if not date_str:
                        continue
                    labels = cell.select("span.label")
                    cls_set = set()
                    for l in labels:
                        cls_set.update(l.get("class", []))
                    has_am = "label-morning" in cls_set or "label-morning-clinic" in cls_set
                    has_pm = "label-afternoon" in cls_set

                    if has_am:
                        date_schedules.append({
                            "schedule_date": date_str, "time_slot": "morning",
                            "start_time": "09:00", "end_time": "12:00",
                            "location": "외래", "status": "진료",
                        })
                    if has_pm:
                        date_schedules.append({
                            "schedule_date": date_str, "time_slot": "afternoon",
                            "start_time": "13:00", "end_time": "17:00",
                            "location": "외래", "status": "진료",
                        })
            except Exception as e:
                logger.warning(f"[{self.hospital_code}] 월별 스케줄 실패 ({ym}, dr_sid={dr_sid}): {e}")

        return date_schedules

    async def _fetch_dept_schedule(self, client: httpx.AsyncClient, dept_cd: str, dept_nm: str, grp_yn: str = "N") -> list[dict]:
        """진료과별 의료진 + 스케줄 HTML 파싱"""
        try:
            resp = await client.post(
                f"{self.base_url}/medical/dept/deptSchdoctorList.do",
                data={"dept_cd": dept_cd, "grp_yn": grp_yn, "gubun": "all"},
            )
            resp.raise_for_status()
            html = resp.text
        except Exception as e:
            logger.error(f"[{self.hospital_code}] {dept_nm} 스케줄 실패: {e}")
            return []

        return self._parse_schedule_html(html, dept_nm)

    def _parse_schedule_html(self, html: str, dept_nm: str) -> list[dict]:
        """HTML + 인라인 JavaScript에서 의사 정보와 스케줄 추출"""
        doctors = {}  # dr_sid → doctor dict

        # 1. doctorReservation onclick에서 이름 + dr_sid 추출
        # onclick="doctorReservation('가정의학과', 'FM','이상화', '1001146', '0','');"
        resv_pattern = re.compile(
            r"doctorReservation\s*\(\s*'([^']*)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'"
        )
        for m in resv_pattern.finditer(html):
            name = m.group(3).strip()
            dr_sid = m.group(4)
            if dr_sid and name:
                if dr_sid not in doctors:
                    doctors[dr_sid] = {
                        "dr_sid": dr_sid, "name": name, "department": dept_nm,
                        "position": "", "specialty": "", "schedules": {},
                    }
                elif not doctors[dr_sid]["name"]:
                    doctors[dr_sid]["name"] = name

        # drProfile onclick에서 추가 dr_sid 수집
        profile_pattern = re.compile(r"drProfile\s*\(\s*'([^']+)'\s*,\s*'([^']*)'\s*\)")
        for m in profile_pattern.finditer(html):
            dr_sid = m.group(1)
            if dr_sid not in doctors:
                doctors[dr_sid] = {
                    "dr_sid": dr_sid, "name": "", "department": dept_nm,
                    "position": "", "specialty": "", "schedules": {},
                }

        # cell ID에서도 dr_sid 수집 (위에서 못 잡은 경우)
        sid_pattern = re.compile(r'id="(?:am|pm)(?:Mon|Tue|Wed|Thu|Fri|Sat)_([^"]+)"')
        for m in sid_pattern.finditer(html):
            dr_sid = m.group(1)
            if dr_sid not in doctors:
                doctors[dr_sid] = {
                    "dr_sid": dr_sid, "name": "", "department": dept_nm,
                    "position": "", "specialty": "", "schedules": {},
                }

        # 이름이 없는 의사: <div class="name"> 근처에서 drProfile dr_sid와 매칭
        for dr_sid, doc in doctors.items():
            if doc["name"]:
                continue
            # name-view 블록 내에서 dr_sid와 이름이 같은 <tr> 안에 있음
            # alt 텍스트에서 이름 추출: alt="{name}" ... id="amMon_{dr_sid}"
            block_pattern = re.compile(
                rf'alt="([^"]+)"[^<]*(?:<[^>]*>)*?[^<]*id="amMon_{re.escape(dr_sid)}"',
                re.DOTALL,
            )
            block_m = block_pattern.search(html)
            if block_m:
                doc["name"] = block_m.group(1).strip()

        # 직위 추출: <div class="name">{name}<span class="rank1">{position}</span></div>
        pos_pattern = re.compile(r'class="name"[^>]*>([^<]+)<span[^>]*class="rank1"[^>]*>([^<]*)</span>')
        for m in pos_pattern.finditer(html):
            name = m.group(1).strip()
            position = m.group(2).strip()
            for doc in doctors.values():
                if doc["name"] == name and not doc["position"]:
                    doc["position"] = position

        # 전문분야: alt="{name}" 이후 두 번째 <div class="txt">
        spec_pattern = re.compile(
            r'alt="([^"]+)".*?class="txt"[^>]*>[^<]*</div>\s*<div\s+class="txt"[^>]*>([^<]+)</div>',
            re.DOTALL,
        )
        for m in spec_pattern.finditer(html):
            alt_name = m.group(1).strip()
            specialty = m.group(2).strip()
            for doc in doctors.values():
                if doc["name"] == alt_name and not doc["specialty"]:
                    doc["specialty"] = specialty

        # 2. JavaScript에서 스케줄 코드 추출
        # 패턴: if('01' == "01") { $('#amMon_' + '1001146').html(...)
        js_pattern = re.compile(
            r"if\s*\(\s*'([^']*)'\s*==\s*\"(\d+)\"\s*\)\s*\{\s*\$\s*\(\s*'#(\w+)_'\s*\+\s*'([^']+)'\s*\)"
        )
        for m in js_pattern.finditer(html):
            code_val = m.group(1)  # actual value
            expected = m.group(2)  # "01", "02", "03", "04"
            slot_key = m.group(3)  # "amMon", "pmTue", etc.
            dr_sid = m.group(4)

            if code_val == expected and code_val in ACTIVE_CODES:
                if slot_key in SLOT_MAP and dr_sid in doctors:
                    dow, time_slot = SLOT_MAP[slot_key]
                    loc = "외래" if code_val == "01" else "클리닉"
                    doctors[dr_sid]["schedules"][(dow, time_slot)] = loc

        # dict → list 변환
        result = []
        for doc in doctors.values():
            if not doc["name"]:
                continue
            ext_id = f"{self.hospital_code}-{doc['dr_sid']}"
            schedules = []
            for (dow, slot), loc in sorted(doc["schedules"].items()):
                start, end = TIME_RANGES[slot]
                schedules.append({
                    "day_of_week": dow, "time_slot": slot,
                    "start_time": start, "end_time": end, "location": loc,
                })
            result.append({
                "staff_id": ext_id, "external_id": ext_id,
                "name": doc["name"], "department": doc["department"],
                "position": doc["position"], "specialty": doc["specialty"],
                "profile_url": f"{self.base_url}/doctor/basicInfo.do?dr_sid={doc['dr_sid']}",
                "notes": "", "schedules": schedules,
            })

        logger.info(f"[{self.hospital_code}] {dept_nm}: {len(result)}명")
        return result

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        depts = await self._fetch_departments()
        all_doctors = {}

        async with httpx.AsyncClient(headers=self.headers, timeout=60, follow_redirects=True) as client:
            for dept in depts:
                dept_cd = dept.get("dept_cd", "")
                dept_nm = dept.get("dept_nm", "")
                grp_yn = dept.get("grp_yn", "N")
                if not dept_cd:
                    continue
                docs = await self._fetch_dept_schedule(client, dept_cd, dept_nm, grp_yn)
                for doc in docs:
                    ext_id = doc["external_id"]
                    if ext_id in all_doctors:
                        existing = all_doctors[ext_id]
                        existing_keys = {(s["day_of_week"], s["time_slot"]) for s in existing["schedules"]}
                        for s in doc["schedules"]:
                            if (s["day_of_week"], s["time_slot"]) not in existing_keys:
                                existing["schedules"].append(s)
                        if doc["specialty"] and doc["specialty"] not in existing["specialty"]:
                            existing["specialty"] = f"{existing['specialty']}, {doc['specialty']}" if existing["specialty"] else doc["specialty"]
                    else:
                        all_doctors[ext_id] = doc

            # 월별 날짜 스케줄 수집
            for doc in all_doctors.values():
                dr_sid = doc["external_id"].replace(f"{self.hospital_code}-", "")
                date_scheds = await self._fetch_monthly_schedule(client, dr_sid)
                doc["date_schedules"] = date_scheds

        result = list(all_doctors.values())
        logger.info(f"[{self.hospital_code}] 총 {len(result)}명")
        self._cached_data = result
        return result

    async def get_departments(self) -> list[dict]:
        depts = await self._fetch_departments()
        return [{"code": d.get("dept_cd", ""), "name": d.get("dept_nm", "")} for d in depts if d.get("dept_cd")]

    async def crawl_doctor_list(self, department: str = None) -> list[dict]:
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]
        return [{k: d[k] for k in ("staff_id", "external_id", "name", "department", "position", "specialty", "profile_url", "notes")} for d in data]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 교수 진료시간 조회 + 월별 날짜 스케줄"""
        _keys = ("staff_id", "name", "department", "position", "specialty", "profile_url", "notes", "schedules", "date_schedules")
        empty = {"staff_id": staff_id, "name": "", "department": "", "position": "",
                 "specialty": "", "profile_url": "", "notes": "", "schedules": [], "date_schedules": []}

        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return {k: d.get(k, "" if k not in ("schedules", "date_schedules") else []) for k in _keys}
            return empty

        # 개별 조회: 진료과 순회하며 해당 교수 찾으면 월별 스케줄도 수집
        prefix = f"{self.hospital_code}-"
        dr_sid = staff_id.replace(prefix, "") if staff_id.startswith(prefix) else staff_id
        depts = await self._fetch_departments()

        async with httpx.AsyncClient(headers=self.headers, timeout=60, follow_redirects=True) as client:
            for dept in depts:
                dept_cd = dept.get("dept_cd", "")
                dept_nm = dept.get("dept_nm", "")
                grp_yn = dept.get("grp_yn", "N")
                if not dept_cd:
                    continue
                docs = await self._fetch_dept_schedule(client, dept_cd, dept_nm, grp_yn)
                for doc in docs:
                    matched = (doc.get("external_id") == staff_id or
                               doc.get("staff_id") == staff_id or
                               f"{prefix}{dr_sid}" == doc.get("external_id"))
                    if matched:
                        # 날짜별 스케줄 추가 수집
                        date_scheds = await self._fetch_monthly_schedule(client, dr_sid)
                        doc["date_schedules"] = date_scheds
                        return {k: doc.get(k, "" if k not in ("schedules", "date_schedules") else []) for k in _keys}

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
