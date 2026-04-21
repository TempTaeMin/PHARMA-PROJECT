"""동국대학교 일산병원 크롤러

전체 진료시간표: HTML /medical/info/schlist.jsp (단일 페이지에 전체 데이터)
의사 목록: HTML /medical/department/departmentDetail.jsp?act=doctorInfo&deptCode={code}
주의: EUC-KR 인코딩 사이트
"""
import re
import logging
import httpx
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "http://www.dumc.or.kr"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

DUIH_DEPARTMENTS = {
    "FM": "가정의학과", "IMI": "감염내과", "IME": "내분비내과",
    "IMJ": "류마티스내과", "AN": "마취통증의학과", "RO": "방사선종양학과",
    "PA": "병리과", "UR": "비뇨의학과", "OG": "산부인과",
    "PS": "성형외과", "PED": "소아청소년과", "GIC": "소화기내과",
    "NR": "신경과", "NS": "신경외과", "IMN": "신장내과",
    "CCVSC": "심장내과", "TS": "심장혈관흉부외과", "IMA": "알레르기내과",
    "OT": "안과", "DR": "영상의학과", "GS": "외과",
    "EM": "응급의학과", "OL": "이비인후과", "RH": "재활의학과",
    "NP": "정신건강의학과", "OS": "정형외과", "LM": "진단검사의학과",
    "DS": "치과", "DM": "피부과", "NM": "핵의학과",
    "IMR": "호흡기내과", "IMH": "혈액종양내과",
}


class DuihCrawler:
    """동국대학교 일산병원 크롤러"""

    def __init__(self):
        self.hospital_code = "DUIH"
        self.hospital_name = "동국대학교일산병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        self._cached_data = None

    async def get_departments(self) -> list[dict]:
        return [{"code": code, "name": name} for code, name in DUIH_DEPARTMENTS.items()]

    async def _fetch_timetable(self) -> str:
        """전체 진료시간표 HTML 가져오기 (EUC-KR)"""
        async with httpx.AsyncClient(headers=self.headers, timeout=30, follow_redirects=True) as client:
            resp = await client.get(
                f"{BASE_URL}/medical/info/schlist.jsp",
                params={"nowPageInfo": "ILSH", "nowMenuId": "00000059"},
            )
            resp.raise_for_status()
            # EUC-KR 인코딩
            return resp.content.decode("euc-kr", errors="replace")

    def _parse_timetable(self, html: str) -> list[dict]:
        """전체 진료시간표 HTML 파싱

        구조:
        <caption>{진료과} 진료시간표</caption>
        <tr>
          <td rowspan="2"><a href="javascript:fnDocPopup('{deptCode}','{docCode}');">{name}</a></td>
          <td rowspan="2" class="text_al">{specialty}</td>
          <td>오전</td>
          <td>●</td><td></td><td>●</td><td></td><td></td><td></td>
          <td rowspan="2">...</td>
        </tr>
        <tr>
          <td>오후</td>
          <td></td><td>●</td><td></td><td></td><td>●</td><td></td>
        </tr>
        """
        doctors = []
        current_dept = ""

        # 진료과 캡션 추출
        caption_pattern = re.compile(r'<caption>\s*([^<]+?)\s*진료시간표')

        # 의사 행 추출: fnDocPopup 또는 fnForward로 시작
        doc_row_pattern = re.compile(
            r"fnDocPopup\s*\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)[^>]*>\s*([^<]+)</a>\s*</td>\s*"
            r'<td[^>]*>([^<]*)</td>\s*'   # specialty
            r'<td[^>]*>오전</td>\s*'
            r'<td[^>]*>(.*?)</td>\s*'     # 월 AM
            r'<td[^>]*>(.*?)</td>\s*'     # 화 AM
            r'<td[^>]*>(.*?)</td>\s*'     # 수 AM
            r'<td[^>]*>(.*?)</td>\s*'     # 목 AM
            r'<td[^>]*>(.*?)</td>\s*'     # 금 AM
            r'<td[^>]*>(.*?)</td>\s*'     # 토 AM
            r'(?:<td[^>]*>.*?</td>\s*)?'  # 예약 버튼 (rowspan)
            r'</tr>\s*<tr>\s*'
            r'<td[^>]*>오후</td>\s*'
            r'<td[^>]*>(.*?)</td>\s*'     # 월 PM
            r'<td[^>]*>(.*?)</td>\s*'     # 화 PM
            r'<td[^>]*>(.*?)</td>\s*'     # 수 PM
            r'<td[^>]*>(.*?)</td>\s*'     # 목 PM
            r'<td[^>]*>(.*?)</td>\s*'     # 금 PM
            r'<td[^>]*>(.*?)</td>',       # 토 PM
            re.DOTALL,
        )

        # 진료과별로 매핑
        dept_positions = []
        for m in caption_pattern.finditer(html):
            dept_name = m.group(1).strip()
            dept_positions.append((m.start(), dept_name))

        def get_dept_for_pos(pos):
            dept = ""
            for dp, dn in dept_positions:
                if dp <= pos:
                    dept = dn
                else:
                    break
            return dept

        seen: dict[str, dict] = {}  # doc_code → doctor dict (dedup)

        for m in doc_row_pattern.finditer(html):
            dept_code = m.group(1)
            doc_code = m.group(2)
            name = m.group(3).strip()
            specialty = m.group(4).strip()

            dept_nm = get_dept_for_pos(m.start())
            if not dept_nm:
                dept_nm = DUIH_DEPARTMENTS.get(dept_code, "")

            schedules = []
            for dow in range(6):
                cell = m.group(5 + dow).strip()
                if '●' in cell or '○' in cell:
                    start, end = TIME_RANGES["morning"]
                    schedules.append({
                        "day_of_week": dow, "time_slot": "morning",
                        "start_time": start, "end_time": end, "location": "외래",
                    })
            for dow in range(6):
                cell = m.group(11 + dow).strip()
                if '●' in cell or '○' in cell:
                    start, end = TIME_RANGES["afternoon"]
                    schedules.append({
                        "day_of_week": dow, "time_slot": "afternoon",
                        "start_time": start, "end_time": end, "location": "외래",
                    })

            if doc_code in seen:
                existing = seen[doc_code]
                if dept_nm and dept_nm != existing["department"] and dept_nm not in existing["_extra_depts"]:
                    existing["_extra_depts"].append(dept_nm)
                # 추가 진료과의 스케줄도 누락 없이 합치기
                for s in schedules:
                    if s not in existing["schedules"]:
                        existing["schedules"].append(s)
                continue

            ext_id = f"DUIH-{doc_code}"
            seen[doc_code] = {
                "staff_id": ext_id, "external_id": ext_id,
                "name": name, "department": dept_nm,
                "position": "", "specialty": specialty,
                "profile_url": f"{BASE_URL}/medical/department/deptDocPopDetail.do?act=deptDocInfo&nowPageInfo=ILSH&deptCode={dept_code}&docCode={doc_code}",
                "notes": "", "schedules": schedules,
                "_dept_code": dept_code, "_doc_code": doc_code,
                "_extra_depts": [],
            }

        for d in seen.values():
            extras = d.pop("_extra_depts")
            if extras:
                tag = f"복수 진료과: {', '.join(extras)}"
                d["notes"] = (d["notes"] + "\n" + tag) if d["notes"] else tag
            doctors.append(d)

        logger.info(f"[DUIH] 파싱 완료: {len(doctors)}명 (dedup)")
        return doctors

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data
        html = await self._fetch_timetable()
        self._cached_data = self._parse_timetable(html)
        return self._cached_data

    async def crawl_doctor_list(self, department: str = None) -> list[dict]:
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]
        return [{k: d[k] for k in ("staff_id", "external_id", "name", "department", "position", "specialty", "profile_url", "notes")} for d in data]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 교수 진료시간 조회"""
        empty = {"staff_id": staff_id, "name": "", "department": "", "position": "",
                 "specialty": "", "profile_url": "", "notes": "", "schedules": []}

        # 단일 페이지에서 전체 파싱 → 캐시 활용
        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return {k: d.get(k, "") for k in ("staff_id", "name", "department", "position", "specialty", "profile_url", "notes", "schedules")}
            return empty

        # 캐시 없으면 전체 파싱
        prefix = "DUIH-"
        doc_code = staff_id.replace(prefix, "") if staff_id.startswith(prefix) else staff_id

        html = await self._fetch_timetable()
        doctors = self._parse_timetable(html)
        self._cached_data = doctors

        for d in doctors:
            if d["staff_id"] == staff_id or d["external_id"] == staff_id or d.get("_doc_code") == doc_code:
                return {k: d.get(k, "") for k in ("staff_id", "name", "department", "position", "specialty", "profile_url", "notes", "schedules")}

        return empty

    async def crawl_doctors(self, department: str = None):
        from app.schemas.schemas import CrawlResult, CrawledDoctor
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]
        doctors = [
            CrawledDoctor(name=d["name"], department=d["department"], position=d["position"],
                          specialty=d["specialty"], profile_url=d["profile_url"],
                          external_id=d["external_id"], notes=d.get("notes", ""), schedules=d["schedules"])
            for d in data
        ]
        return CrawlResult(hospital_code=self.hospital_code, hospital_name=self.hospital_name,
                           status="success" if doctors else "partial", doctors=doctors, crawled_at=datetime.utcnow())
