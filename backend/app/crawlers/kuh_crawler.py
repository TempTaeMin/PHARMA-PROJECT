"""건국대학교병원 크롤러

진료과 목록: HTML /medical/dept/deptList.do
의사 목록: HTML /medical/dept/deptDoctor.do?dept_cd={code}
스케줄: JSON /doctor/docMonthlyScheduleAjax.do?sdoctcd={dr_sid}&sdate={YYYYMM01}&nextMonth=0
"""
import re
import logging
import httpx
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

BASE_URL = "https://www.kuh.ac.kr"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

# 하드코딩된 진료과 코드 (사이트에서 추출)
KUH_DEPARTMENTS = {
    "000516": "가정의학과", "000255": "감염내과", "000564": "건강의학과",
    "000240": "내분비대사내과", "000250": "류마티스내과", "000397": "마취통증의학과",
    "000448": "방사선종양학과", "000495": "병리과", "000363": "비뇨의학과",
    "000330": "산부인과", "000320": "성형외과", "000260": "소아청소년과",
    "000192": "소화기내과", "000275": "신경과", "000277": "신경외과",
    "000235": "신장내과", "000204": "심장혈관내과", "000340": "안과",
    "000404": "영상의학과", "000300": "외과", "000522": "응급의학과",
    "000353": "이비인후-두경부외과", "201312": "임상약리학과", "202302": "입원의학과",
    "000374": "재활의학과", "000268": "정신건강의학과", "000312": "정형외과",
    "000245": "종양혈액내과", "000467": "진단검사의학과", "000563": "치과",
    "000290": "피부과", "000539": "핵의학과", "000224": "호흡기-알레르기내과",
    "000309": "심장혈관흉부외과",
}


class KuhCrawler:
    """건국대학교병원 크롤러"""

    def __init__(self):
        self.hospital_code = "KUH"
        self.hospital_name = "건국대학교병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        self._cached_data = None

    async def get_departments(self) -> list[dict]:
        return [{"code": code, "name": name} for code, name in KUH_DEPARTMENTS.items()]

    async def _fetch_dept_doctors(self, client: httpx.AsyncClient, dept_cd: str, dept_nm: str) -> list[dict]:
        """진료과별 의사 목록 HTML 파싱"""
        try:
            resp = await client.get(
                f"{BASE_URL}/medical/dept/deptDoctor.do",
                params={"dept_cd": dept_cd},
            )
            resp.raise_for_status()
            html = resp.text
        except Exception as e:
            logger.error(f"[KUH] {dept_nm} 의사 목록 실패: {e}")
            return []

        doctors = []
        seen = set()

        # doctorReservationDeptDoc('진료과', '이름', 'dr_sid') 패턴
        resv_pattern = re.compile(
            r"doctorReservationDeptDoc\s*\(\s*'([^']*)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'"
        )
        for m in resv_pattern.finditer(html):
            name = m.group(2).strip()
            dr_sid = m.group(3)
            if dr_sid in seen or not name:
                continue
            seen.add(dr_sid)
            doctors.append({
                "dr_sid": dr_sid, "dept_cd": dept_cd, "dept_nm": dept_nm,
                "name": name, "specialty": "",
            })

        # drProfile 패턴도 확인 (예약 버튼 없는 의사)
        dr_pattern = re.compile(r"drProfile\s*\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)")
        for m in dr_pattern.finditer(html):
            dr_sid = m.group(1)
            if dr_sid in seen:
                continue
            seen.add(dr_sid)
            # 이름: alt 태그에서 찾기 (이미지)
            alt_idx = html.rfind(f"alt=", 0, m.start())
            name = ""
            if alt_idx > 0:
                am = re.search(r'alt="([^"]+)"', html[alt_idx:alt_idx+50])
                if am:
                    name = am.group(1).strip()
            if name:
                doctors.append({
                    "dr_sid": dr_sid, "dept_cd": dept_cd, "dept_nm": dept_nm,
                    "name": name, "specialty": "",
                })

        # 전문분야: <P>전문: {specialty}</P> 패턴 (각 의사 카드 내)
        for doc in doctors:
            dr_sid = doc["dr_sid"]
            # dr_sid가 포함된 블록 주변에서 <P> 태그 찾기
            sid_idx = html.find(dr_sid)
            if sid_idx > 0:
                # 해당 블록의 시작 (inner) 찾기
                block_start = html.rfind('<div class="inner">', 0, sid_idx)
                if block_start > 0:
                    block = html[block_start:sid_idx]
                    # <P> 태그에서 전문분야
                    pm = re.search(r'<P>([^<]+)</P>', block)
                    if pm:
                        spec = pm.group(1).strip()
                        # "전문: " 접두사 제거
                        if spec.startswith("전문:"):
                            spec = spec[3:].strip()
                        doc["specialty"] = spec

        return [d for d in doctors if d.get("name")]

    def _parse_monthly_json(self, data: dict) -> tuple[dict, list[dict]]:
        """월간 JSON 파싱 → (day_slots, date_schedules)

        day_slots: (day_of_week, time_slot) → location
        date_schedules: 날짜별 진료 일정
        """
        monthly = data.get("monthlyList", [])
        day_slots = {}
        date_schedules = []

        for entry in monthly:
            date_str = entry.get("orddd", "")
            if not date_str:
                continue
            try:
                dt = datetime.strptime(date_str, "%Y%m%d")
                dow = dt.weekday()
            except ValueError:
                continue

            endflag = entry.get("endflag_cd", "")
            if endflag in ("02", "05"):
                continue  # 학회/휴가 제외

            ap = entry.get("apflag_cd", "")
            dept_nm = entry.get("dept_nm", "외래")
            # 특수클리닉 구분: dept_nm에 "클리닉" 포함 시 location으로 사용
            location = dept_nm if dept_nm else "외래"

            if ap == "A":
                slot = "morning"
            elif ap == "P":
                slot = "afternoon"
            else:
                continue

            day_slots[(dow, slot)] = location

            formatted = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
            start, end = TIME_RANGES[slot]
            date_schedules.append({
                "schedule_date": formatted,
                "time_slot": slot,
                "start_time": start,
                "end_time": end,
                "location": location,
                "status": "마감" if endflag == "01" else "진료",
            })

        return day_slots, date_schedules

    async def _fetch_schedule(self, client: httpx.AsyncClient, dr_sid: str) -> list[dict]:
        """월간 스케줄 JSON → 요일 기반 정기 스케줄로 변환"""
        now = datetime.now()
        sdate = now.strftime("%Y%m01")

        try:
            resp = await client.get(
                f"{BASE_URL}/doctor/docMonthlyScheduleAjax.do",
                params={"sdoctcd": dr_sid, "sdate": sdate, "nextMonth": "0"},
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            return []

        day_slots, _ = self._parse_monthly_json(data)
        schedules = []
        for (dow, slot), loc in sorted(day_slots.items()):
            start, end = TIME_RANGES[slot]
            schedules.append({
                "day_of_week": dow, "time_slot": slot,
                "start_time": start, "end_time": end, "location": loc,
            })
        return schedules

    async def _fetch_monthly_schedule(self, client: httpx.AsyncClient, dr_sid: str, months: int = 3) -> list[dict]:
        """3개월치 날짜별 스케줄 수집"""
        all_date_schedules = []
        now = datetime.now()
        for i in range(months):
            target = now + timedelta(days=i * 30)
            sdate = target.strftime("%Y%m01")
            try:
                resp = await client.get(
                    f"{BASE_URL}/doctor/docMonthlyScheduleAjax.do",
                    params={"sdoctcd": dr_sid, "sdate": sdate, "nextMonth": "0"},
                )
                resp.raise_for_status()
                data = resp.json()
                _, date_scheds = self._parse_monthly_json(data)
                all_date_schedules.extend(date_scheds)
            except Exception as e:
                logger.warning(f"[KUH] 월별 스케줄 실패 ({sdate}, {dr_sid}): {e}")
        return all_date_schedules

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        all_doctors = {}

        async with httpx.AsyncClient(headers=self.headers, timeout=60, follow_redirects=True) as client:
            for dept_cd, dept_nm in KUH_DEPARTMENTS.items():
                docs = await self._fetch_dept_doctors(client, dept_cd, dept_nm)
                for doc in docs:
                    dr_sid = doc["dr_sid"]
                    if dr_sid in all_doctors:
                        continue

                    schedules = await self._fetch_schedule(client, dr_sid)
                    date_schedules = await self._fetch_monthly_schedule(client, dr_sid)
                    ext_id = f"KUH-{dr_sid}"
                    all_doctors[dr_sid] = {
                        "staff_id": ext_id, "external_id": ext_id,
                        "name": doc["name"], "department": doc["dept_nm"],
                        "position": "", "specialty": doc.get("specialty", ""),
                        "profile_url": f"{BASE_URL}/doctor/basicInfo.do?dr_sid={dr_sid}&dept_cd={dept_cd}",
                        "notes": "", "schedules": schedules,
                        "date_schedules": date_schedules,
                        "_dr_sid": dr_sid,
                    }

        result = list(all_doctors.values())
        logger.info(f"[KUH] 총 {len(result)}명")
        self._cached_data = result
        return result

    async def crawl_doctor_list(self, department: str = None) -> list[dict]:
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]
        return [{k: d[k] for k in ("staff_id", "external_id", "name", "department", "position", "specialty", "profile_url", "notes")} for d in data]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 교수 진료시간 + 날짜별 스케줄 조회"""
        _keys = ("staff_id", "name", "department", "position", "specialty", "profile_url", "notes", "schedules", "date_schedules")
        empty = {"staff_id": staff_id, "name": "", "department": "", "position": "",
                 "specialty": "", "profile_url": "", "notes": "", "schedules": [], "date_schedules": []}

        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return {k: d.get(k, "" if k not in ("schedules", "date_schedules") else []) for k in _keys}
            return empty

        prefix = "KUH-"
        dr_sid = staff_id.replace(prefix, "") if staff_id.startswith(prefix) else staff_id

        async with httpx.AsyncClient(headers=self.headers, timeout=60, follow_redirects=True) as client:
            schedules = await self._fetch_schedule(client, dr_sid)
            date_schedules = await self._fetch_monthly_schedule(client, dr_sid)

            name = ""
            dept_nm = ""
            specialty = ""
            try:
                resp = await client.get(
                    f"{BASE_URL}/doctor/basicInfo.do",
                    params={"dr_sid": dr_sid},
                )
                resp.raise_for_status()
                html = resp.text
                nm = re.search(r'<strong>([^<]+)', html)
                if nm:
                    name = nm.group(1).strip()
                am = re.search(r'alt="([가-힣]+)"', html)
                if am and not name:
                    name = am.group(1).strip()
                pm = re.search(r'<P>([^<]+)</P>', html)
                if pm:
                    specialty = pm.group(1).strip()
            except Exception:
                pass

            ext_id = f"KUH-{dr_sid}"
            return {
                "staff_id": ext_id, "name": name, "department": dept_nm,
                "position": "", "specialty": specialty,
                "profile_url": f"{BASE_URL}/doctor/basicInfo.do?dr_sid={dr_sid}",
                "notes": "", "schedules": schedules,
                "date_schedules": date_schedules,
            }

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
