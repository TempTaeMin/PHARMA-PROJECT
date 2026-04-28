"""아주대병원 크롤러

HTML 파싱 기반 크롤러 (JSON API 없음).
페이지:
  진료과 목록: GET /dept/deptList.do → deptCd, deptNo 파싱
  의사 목록: GET /doctor/profDeptList.do?deptNo={no} → 의사 카드 파싱
  진료시간표: GET /hospital/timeDeptTable.do?deptNo={no} → 스케줄 테이블 파싱
  의사 프로필: GET /doctor/profViewPop.do?deptNo={no}&profNo={profNo}

의사 카드 구조:
  openDoctorView('deptNo', 'profEmpCd') 함수 호출
  fastReserve({deptCd:'XX', profEmpCd:'YYYY'}) 함수 호출
  전문분야 텍스트

스케줄 테이블 구조:
  의사별 2행 (오전/오후)
  열: 월~토
  셀: "진료과", "특수진료", "휴진", "연수", "파견" 등
"""
import re
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://hosp.ajoumc.or.kr"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

DAY_CHAR_MAP = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5}


class AjoumcCrawler:
    """아주대병원 크롤러"""

    def __init__(self):
        self.hospital_code = "AJOUMC"
        self.hospital_name = "아주대병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Referer": BASE_URL,
        }
        self._cached_data = None
        self._cached_depts = None

    # ─── 진료과 목록 ───

    async def _fetch_departments(self) -> list[dict]:
        """진료과 목록 (deptList.do HTML 파싱)"""
        if self._cached_depts is not None:
            return self._cached_depts

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True,
        ) as client:
            try:
                resp = await client.get(f"{BASE_URL}/dept/deptList.do")
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")

                depts = []
                seen = set()

                # deptView.do?deptNo=X&deptCd=Y 링크에서 파싱
                for a_tag in soup.select("a[href*='deptView']"):
                    href = a_tag.get("href", "")
                    name_el = a_tag.select_one("span.tit span") or a_tag.select_one("span")
                    name = name_el.get_text(strip=True) if name_el else a_tag.get_text(strip=True)

                    m_no = re.search(r'deptNo=(\d+)', href)
                    m_cd = re.search(r'deptCd=([A-Z]+)', href)

                    if m_no and name:
                        dept_no = m_no.group(1)
                        dept_cd = m_cd.group(1) if m_cd else ""
                        if dept_no not in seen:
                            seen.add(dept_no)
                            clean_name = re.sub(r'\s+', ' ', name).strip()
                            if clean_name:
                                depts.append({
                                    "code": dept_no,
                                    "dept_cd": dept_cd,
                                    "name": clean_name,
                                })

                # deptJsonStr 자바스크립트 변수에서도 파싱 시도
                if not depts:
                    html_text = str(soup)
                    json_match = re.search(r'deptJsonStr\s*=\s*\'(\[.*?\])\'', html_text, re.DOTALL)
                    if json_match:
                        import json
                        try:
                            dept_list = json.loads(json_match.group(1))
                            for item in dept_list:
                                dept_no = str(item.get("DEPT_NO", "")).strip()
                                dept_cd = str(item.get("DEPT_CD", "")).strip()
                                name = str(item.get("DEPT_KOR_NM", "")).strip()
                                if dept_no and name and dept_no not in seen:
                                    seen.add(dept_no)
                                    depts.append({
                                        "code": dept_no,
                                        "dept_cd": dept_cd,
                                        "name": name,
                                    })
                        except (json.JSONDecodeError, Exception):
                            pass

                # 폴백: 알려진 진료과 목록 (2026년 기준)
                if not depts:
                    known_depts = [
                        ("1", "FM", "가정의학과"), ("2", "IDMD", "감염내과"),
                        ("3", "EDMD", "내분비대사내과"), ("4", "RHMD", "류마티스내과"),
                        ("5", "URO", "비뇨의학과"), ("6", "TR", "방사선종양학과"),
                        ("7", "OBGY", "산부인과"), ("8", "PS", "성형외과"),
                        ("9", "NEMD", "신장내과"), ("10", "NEUR", "신경과"),
                        ("11", "PED", "소아청소년과"), ("12", "CAMD", "순환기내과"),
                        ("13", "GIMD", "소화기내과"), ("14", "OPTH", "안과"),
                        ("15", "ALMD", "알레르기면역내과"), ("16", "DR", "영상의학과"),
                        ("17", "ENT", "이비인후과"), ("19", "ERMD", "응급의학과"),
                        ("20", "OEM", "직업환경의학과"), ("21", "RM", "재활의학과"),
                        ("22", "PSY", "정신건강의학과"), ("23", "OS", "정형외과"),
                        ("24", "HOMD", "종양혈액내과"), ("26", "DERM", "피부과"),
                        ("27", "NM", "핵의학과"), ("28", "CS", "심장혈관흉부외과"),
                        ("29", "PIMD", "호흡기내과"), ("49", "NS", "신경외과"),
                        ("68", "AP", "병리과"), ("70", "ANES", "마취통증의학과"),
                        ("80", "TS", "외상의학과"), ("81", "CP", "진단검사의학과"),
                        ("100", "GIS", "위장관외과"), ("101", "CRS", "대장항문외과"),
                        ("103", "PDS", "소아외과"), ("104", "BS", "유방외과"),
                        ("105", "TEDS", "갑상선내분비외과"), ("106", "KTS", "이식혈관외과"),
                        ("197", "HBPS", "간담췌외과"),
                    ]
                    depts = [{"code": c, "dept_cd": d, "name": n} for c, d, n in known_depts]

                logger.info(f"[AJOUMC] 진료과 {len(depts)}개")
                self._cached_depts = depts
                return depts
            except Exception as e:
                logger.error(f"[AJOUMC] 진료과 목록 실패: {e}")
                self._cached_depts = []
                return []

    # ─── 진료과별 의사 목록 ───

    async def _fetch_dept_doctors(
        self, client: httpx.AsyncClient, dept_no: str, dept_cd: str, dept_name: str
    ) -> list[dict]:
        """진료과별 의사 목록 (profDeptList.do 페이지 파싱)"""
        try:
            resp = await client.get(
                f"{BASE_URL}/doctor/profDeptList.do",
                params={"deptNo": dept_no},
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            logger.error(f"[AJOUMC] {dept_name} 의사 목록 실패: {e}")
            return []

        doctors = []
        seen = set()
        html_text = str(soup)

        # openDoctorView('deptNo', 'profEmpCd') 패턴 추출
        view_pattern = re.compile(r"openDoctorView\s*\(\s*'(\d+)'\s*,\s*'(\d+)'\s*\)")
        # fastReserve({deptCd:'XX', profEmpCd:'YYYY'}) 패턴 추출
        reserve_pattern = re.compile(r"fastReserve\s*\(\s*\{[^}]*profEmpCd\s*:\s*'(\d+)'[^}]*\}")

        # openDoctorView 호출 모두 수집
        for m in view_pattern.finditer(html_text):
            d_no = m.group(1)
            prof_emp_cd = m.group(2)
            if prof_emp_cd not in seen:
                seen.add(prof_emp_cd)
                doctors.append({
                    "prof_emp_cd": prof_emp_cd,
                    "dept_no": d_no,
                    "dept_cd": dept_cd,
                    "name": "",
                    "department": dept_name,
                    "position": "",
                    "specialty": "",
                })

        # fastReserve에서도 추출
        if not doctors:
            for m in reserve_pattern.finditer(html_text):
                prof_emp_cd = m.group(1)
                if prof_emp_cd not in seen:
                    seen.add(prof_emp_cd)
                    doctors.append({
                        "prof_emp_cd": prof_emp_cd,
                        "dept_no": dept_no,
                        "dept_cd": dept_cd,
                        "name": "",
                        "department": dept_name,
                        "position": "",
                        "specialty": "",
                    })

        # 의사 카드에서 이름, 전문분야 추출
        # <a> 태그 안에는 "자세히 보기" 텍스트만 있으므로, 부모 컨테이너에서 이름 추출
        for link in soup.select("a[href*='openDoctorView']"):
            onclick = link.get("href", "")
            m = view_pattern.search(onclick)
            if not m:
                continue
            prof_emp_cd = m.group(2)

            # 부모 컨테이너 (li 또는 div) 찾기
            card = link.find_parent("li") or link.find_parent("div")
            if not card:
                card = link.parent

            # 이름 추출: 컨테이너 내 strong, h4, h3, p.name 등
            name = ""
            if card:
                for sel in ("strong", "h4", "h3", "span.name", "p.name", ".doctor-name"):
                    name_el = card.select_one(sel)
                    if name_el:
                        candidate = name_el.get_text(strip=True)
                        if candidate and candidate not in ("자세히 보기", "자세히보기", "상세보기", "진료예약") and len(candidate) <= 10:
                            name = candidate
                            break

            # 이름 폴백: img alt 속성
            if not name and card:
                img = card.select_one("img")
                if img:
                    alt = img.get("alt", "").strip()
                    alt_name = re.sub(r'\s*(교수|전문의|과장|원장|의사)\s*$', '', alt).strip()
                    if alt_name and len(alt_name) <= 10 and re.search(r'[가-힣]', alt_name):
                        name = alt_name

            # 전문분야: 카드 내 p 태그
            specialty = ""
            if card:
                for p in card.select("p, dd"):
                    t = p.get_text(strip=True)
                    if "전문분야" in t:
                        specialty = t.replace("전문분야:", "").replace("전문분야", "").strip()
                        break
                    elif len(t) > 5 and t != name and t not in ("자세히 보기", "자세히보기", "진료예약"):
                        specialty = t

            # 해당 의사 데이터 업데이트
            for doc in doctors:
                if doc["prof_emp_cd"] == prof_emp_cd:
                    if name:
                        doc["name"] = name
                    if specialty:
                        doc["specialty"] = specialty
                    break

        logger.info(f"[AJOUMC] {dept_name}: {len(doctors)}명")
        return doctors

    # ─── 스케줄 파싱 ───

    async def _fetch_dept_schedule(
        self, client: httpx.AsyncClient, dept_no: str
    ) -> dict[str, list[dict]]:
        """진료시간표 페이지에서 진료과 전체 의사 스케줄 파싱.
        반환: {doctor_id_or_name: [schedule_entries]}
        """
        try:
            resp = await client.get(
                f"{BASE_URL}/hospital/timeDeptTable.do",
                params={"deptNo": dept_no},
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            logger.error(f"[AJOUMC] 스케줄 조회 실패 (deptNo={dept_no}): {e}")
            return {}

        schedules_by_doctor = {}  # name → list[schedule]
        html_text = str(soup)

        # 테이블에서 의사별 스케줄 파싱
        tables = soup.select("table")
        for table in tables:
            # 헤더에서 요일 칼럼 매핑
            col_to_dow = {}
            header_row = table.select_one("thead tr") or table.select_one("tr")
            if not header_row:
                continue

            header_cells = header_row.select("th, td")
            for ci, cell in enumerate(header_cells):
                text = cell.get_text(strip=True)
                for char, dow in DAY_CHAR_MAP.items():
                    if char in text:
                        col_to_dow[ci] = dow
                        break

            if not col_to_dow:
                continue

            # 의사별 오전/오후 행 파싱
            rows = table.select("tbody tr") or table.select("tr")[1:]
            current_doctor = ""
            current_doc_id = ""

            for row in rows:
                cells = row.select("th, td")
                if not cells:
                    continue

                # 의사 이름 감지 (rowspan 사용 또는 첫 셀에 이름)
                first_cell = cells[0]

                # 의사 이름이 포함된 셀 찾기 (openDoctorView 링크 또는 이미지+이름)
                name_link = first_cell.select_one("a[href*='openDoctorView']")
                if name_link:
                    m = re.search(r"openDoctorView\s*\(\s*'(\d+)'\s*,\s*'(\d+)'\s*\)", name_link.get("href", ""))
                    if m:
                        current_doc_id = m.group(2)
                    name_text = name_link.get_text(strip=True)
                    if name_text:
                        current_doctor = name_text
                elif first_cell.get("rowspan"):
                    # rowspan이 있는 셀은 의사 이름 셀
                    name_text = first_cell.get_text(strip=True)
                    if name_text and len(name_text) <= 10:
                        current_doctor = name_text

                if not current_doctor:
                    continue

                # 오전/오후 슬롯 결정
                slot = None
                for cell in cells:
                    # 오전/오후 아이콘 또는 텍스트
                    imgs = cell.select("img")
                    for img in imgs:
                        src = img.get("src", "")
                        alt = img.get("alt", "")
                        if "day01" in src or "오전" in alt:
                            slot = "morning"
                        elif "day02" in src or "오후" in alt:
                            slot = "afternoon"
                    cell_text = cell.get_text(strip=True)
                    if "오전" in cell_text and not slot:
                        slot = "morning"
                    elif "오후" in cell_text and not slot:
                        slot = "afternoon"

                if not slot:
                    continue

                doctor_key = current_doc_id or current_doctor
                if doctor_key not in schedules_by_doctor:
                    schedules_by_doctor[doctor_key] = []

                seen = set((s["day_of_week"], s["time_slot"]) for s in schedules_by_doctor[doctor_key])

                for ci, cell in enumerate(cells):
                    if ci not in col_to_dow:
                        continue
                    dow = col_to_dow[ci]

                    cell_text = cell.get_text(strip=True)
                    # 진료 여부: "진료과", "특수진료" → 진료 있음
                    # "휴진", "연수", "파견" → 진료 없음
                    has_schedule = False
                    if "진료" in cell_text and "휴진" not in cell_text:
                        has_schedule = True
                    elif cell.select("img[src*='icon_01']"):
                        has_schedule = True
                    elif cell_text and cell_text not in ("", "-", "X", "x", "휴진", "연수", "파견"):
                        # 기타 텍스트가 있으면 진료로 간주 (보수적)
                        has_schedule = "진료" in cell_text

                    if has_schedule:
                        key = (dow, slot)
                        if key not in seen:
                            seen.add(key)
                            start, end = TIME_RANGES[slot]
                            schedules_by_doctor[doctor_key].append({
                                "day_of_week": dow,
                                "time_slot": slot,
                                "start_time": start,
                                "end_time": end,
                                "location": "",
                            })

        return schedules_by_doctor

    # ─── 전체 크롤링 ───

    async def _fetch_all(self) -> list[dict]:
        """전체 진료과별 의료진 크롤링 후 캐시"""
        if self._cached_data is not None:
            return self._cached_data

        depts = await self._fetch_departments()
        all_doctors = {}  # prof_emp_cd → doctor dict

        async with httpx.AsyncClient(
            headers=self.headers, timeout=60, follow_redirects=True,
        ) as client:
            for dept in depts:
                dept_no = dept["code"]
                dept_cd = dept.get("dept_cd", "")
                dept_name = dept["name"]

                # 의사 목록 가져오기
                docs = await self._fetch_dept_doctors(client, dept_no, dept_cd, dept_name)

                # 스케줄 테이블 가져오기
                schedules_map = await self._fetch_dept_schedule(client, dept_no)

                for doc in docs:
                    prof_emp_cd = doc["prof_emp_cd"]
                    if prof_emp_cd in all_doctors:
                        # 이미 있는 교수 → 전문분야 병합
                        existing = all_doctors[prof_emp_cd]
                        if doc["specialty"] and doc["specialty"] not in existing["specialty"]:
                            existing["specialty"] = (
                                f"{existing['specialty']}, {doc['specialty']}"
                                if existing["specialty"] else doc["specialty"]
                            )
                        continue

                    # 스케줄 매칭: prof_emp_cd 또는 이름으로 매칭
                    schedules = schedules_map.get(prof_emp_cd, [])
                    if not schedules and doc["name"]:
                        schedules = schedules_map.get(doc["name"], [])

                    ext_id = f"AJOUMC-{prof_emp_cd}"
                    all_doctors[prof_emp_cd] = {
                        "staff_id": ext_id,
                        "external_id": ext_id,
                        "name": doc["name"],
                        "department": doc["department"],
                        "position": doc["position"],
                        "specialty": doc["specialty"],
                        "profile_url": f"{BASE_URL}/doctor/profDeptList.do?deptNo={dept_no}",
                        "notes": "",
                        "schedules": schedules,
                    }

        result = list(all_doctors.values())
        logger.info(f"[AJOUMC] 총 {len(result)}명")
        self._cached_data = result
        return result

    # ─── 공개 인터페이스 ───

    async def get_departments(self) -> list[dict]:
        """진료과 목록 반환"""
        depts = await self._fetch_departments()
        return [{"code": d["code"], "name": d["name"]} for d in depts]

    async def crawl_doctor_list(self, department: str = None) -> list[dict]:
        """교수 목록 (스케줄 제외)"""
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]
        return [
            {k: d[k] for k in ("staff_id", "external_id", "name", "department", "position", "specialty", "profile_url", "notes")}
            for d in data
        ]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 교수 진료시간 조회"""
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "", "schedules": [], "date_schedules": [],
        }

        # 캐시가 이미 있으면 캐시에서 조회
        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    result = {k: d.get(k, "") for k in ("staff_id", "name", "department", "position", "specialty", "profile_url", "notes", "schedules")}
                    result["date_schedules"] = d.get("date_schedules", [])
                    return result
            return empty

        # 전체 크롤링 후 캐시에서 조회
        prefix = f"{self.hospital_code}-"
        prof_emp_cd = staff_id.replace(prefix, "", 1) if staff_id.startswith(prefix) else staff_id

        depts = await self._fetch_departments()
        async with httpx.AsyncClient(
            headers=self.headers, timeout=60, follow_redirects=True,
        ) as client:
            for dept in depts:
                dept_no = dept["code"]
                dept_cd = dept.get("dept_cd", "")
                dept_name = dept["name"]

                docs = await self._fetch_dept_doctors(client, dept_no, dept_cd, dept_name)
                target = next((d for d in docs if d.get("prof_emp_cd") == prof_emp_cd), None)
                if not target:
                    continue

                schedules_map = await self._fetch_dept_schedule(client, dept_no)
                schedules = schedules_map.get(prof_emp_cd, [])
                if not schedules and target.get("name"):
                    schedules = schedules_map.get(target["name"], [])

                ext_id = f"{self.hospital_code}-{prof_emp_cd}"
                return {
                    "staff_id": ext_id,
                    "name": target.get("name", ""),
                    "department": target.get("department", dept_name),
                    "position": target.get("position", ""),
                    "specialty": target.get("specialty", ""),
                    "profile_url": f"{BASE_URL}/doctor/profDeptList.do?deptNo={dept_no}",
                    "notes": "",
                    "schedules": schedules,
                    "date_schedules": [],
                }

        return empty

    async def crawl_doctors(self, department: str = None):
        """전체 크롤링 (CrawlResult 반환)"""
        from app.schemas.schemas import CrawlResult, CrawledDoctor

        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]

        doctors = [
            CrawledDoctor(
                name=d["name"],
                department=d["department"],
                position=d["position"],
                specialty=d["specialty"],
                profile_url=d["profile_url"],
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
